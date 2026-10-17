"""Builds route options, samples weather at checkpoint ETAs, scores them and picks a recommendation."""
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import clients
from .clients import RawRoute
from .errors import ExternalServiceError, PlanningError
from .geo import LatLon, cumulative_miles, haversine_mi, interpolate, sample_along
from .risk import Risk, assess

ROUTE_COUNT = 3
ROUTE_LABELS = "ABC"
MIN_TRIP_MI = 1.0
# OSRM's public server only has a car profile; cap speeds to approximate a loaded truck.
TRUCK_MAX_MPH = 65.0
MAX_DETOUR_RATIO = 1.6
DUPLICATE_OVERLAP = 0.8
DETOUR_OFFSETS = (0.15, -0.15, 0.3, -0.3)
# Open-Meteo forecasts 16 days, counted from 00:00 UTC today.
FORECAST_DAYS = 16
MAX_PAST_DEPARTURE = timedelta(hours=1)
HEATMAP_HOURS = 48
HEATMAP_CELLS_PER_SIDE = 20
HEATMAP_PAD_DEG = 0.5
HEATMAP_CORRIDOR_MI = 40.0
HEATMAP_ANCHOR_SPACING_MI = 10.0
MILES_PER_DEGREE_LAT = 69.0


@dataclass
class Checkpoint:
    mile: float
    point: LatLon
    eta: datetime
    wind_mph: float = 0.0
    rain_in_hr: float = 0.0
    snow_in_hr: float = 0.0
    risk: Risk = Risk.LOW
    factors: tuple[str, ...] = ()


@dataclass
class RouteOption:
    label: str
    summary: str
    points: list[LatLon]
    distance_mi: float
    duration_s: float
    checkpoints: list[Checkpoint]
    miles_by_risk: dict[Risk, float] = field(default_factory=lambda: {level: 0.0 for level in Risk})
    avg_risk: float = 0.0


@dataclass(frozen=True)
class ForecastWindow:
    start: datetime
    end: datetime

    @classmethod
    def from_now(cls, now: datetime) -> "ForecastWindow":
        today = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return cls(today, today + timedelta(days=FORECAST_DAYS) - timedelta(hours=1))


def _format_minutes(minutes: float) -> str:
    minutes = int(minutes)
    return f"{minutes // 60}h {minutes % 60:02d}m"


# Ordered tie-breakers. No Travel miles come first: they are strictly worse than Severe miles.
# Each metric is rounded to the precision shown to the driver, so a stated reason never
# compares two values that display identically.
RANKING_CRITERIA: list[tuple[str, Callable[[RouteOption], float], Callable[[float], str]]] = [
    ("fewest No Travel miles", lambda o: round(o.miles_by_risk[Risk.NO_TRAVEL], 1), lambda v: f"{v:.1f} mi"),
    ("fewest Severe miles", lambda o: round(o.miles_by_risk[Risk.SEVERE], 1), lambda v: f"{v:.1f} mi"),
    ("fewest High miles", lambda o: round(o.miles_by_risk[Risk.HIGH], 1), lambda v: f"{v:.1f} mi"),
    ("lowest average risk", lambda o: round(o.avg_risk, 2), lambda v: f"{v:.2f}"),
    ("shortest travel time", lambda o: round(o.duration_s / 60), _format_minutes),
]


def plan_trip(
    origin: str,
    destination: str,
    departure: datetime,
    load_lb: float,
    interval_mi: int,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    window = ForecastWindow.from_now(now)
    if departure < now - MAX_PAST_DEPARTURE:
        raise PlanningError("Departure time is in the past.")
    if _ceil_hour(departure) > window.end:
        raise PlanningError(f"Departure must be before {window.end:%b %d, %H:%M} UTC, when the weather forecast ends.")
    if origin.strip().casefold() == destination.strip().casefold():
        raise PlanningError("Origin and destination are the same.")

    origin_place = clients.geocode(origin)
    dest_place = clients.geocode(destination)
    raw_routes = find_route_options((origin_place.lat, origin_place.lon), (dest_place.lat, dest_place.lon))

    options = [build_option(ROUTE_LABELS[i], raw, departure, interval_mi) for i, raw in enumerate(raw_routes)]
    latest_eta = max(cp.eta for option in options for cp in option.checkpoints)
    if _ceil_hour(latest_eta) > window.end:
        raise PlanningError("The trip would end after the weather forecast does (16 days out). Choose an earlier departure.")

    heatmap_start = max(_floor_hour(departure), window.start)
    with ThreadPoolExecutor(max_workers=2) as pool:
        weather_job = pool.submit(apply_weather, options, load_lb, window)
        heatmap_job = pool.submit(build_heatmap, options, load_lb, heatmap_start, window)
        weather_job.result()
        heatmap = heatmap_job.result()

    for option in options:
        score_route(option)
    ranked = sorted(options, key=rank_key)
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    warning = None
    if best.miles_by_risk[Risk.NO_TRAVEL] > 0:
        warning = "Every route crosses No Travel conditions at this departure time. Consider delaying the trip."

    return {
        "origin": _place_dict(origin_place),
        "destination": _place_dict(dest_place),
        "departure": departure.isoformat(),
        "load_lb": load_lb,
        "interval_mi": interval_mi,
        "recommended": best.label,
        "recommendation": {"reason": explain(best, runner_up), "warning": warning},
        "routes": [_route_dict(option, ranked.index(option) + 1, departure) for option in options],
        "heatmap": heatmap,
    }


def find_route_options(origin: LatLon, destination: LatLon) -> list[RawRoute]:
    """Up to three distinct routes: OSRM alternatives, topped up with detours via offset waypoints."""
    routes = clients.fetch_routes([origin, destination], alternatives=ROUTE_COUNT - 1)
    if routes[0].distance_mi < MIN_TRIP_MI:
        raise PlanningError("Origin and destination are less than a mile apart.")
    for via in detour_waypoints(origin, destination):
        if len(routes) >= ROUTE_COUNT:
            break
        try:
            candidate = clients.fetch_routes([origin, via, destination])[0]
        except (PlanningError, ExternalServiceError):
            # Detours are optional extras; a failed one shouldn't sink a plan that already has a route.
            continue
        if candidate.distance_mi > MAX_DETOUR_RATIO * routes[0].distance_mi:
            continue
        if any(route_overlap(candidate, existing) > DUPLICATE_OVERLAP for existing in routes):
            continue
        routes.append(candidate)
    return routes[:ROUTE_COUNT]


def detour_waypoints(a: LatLon, b: LatLon) -> list[LatLon]:
    """Points offset perpendicular to the a→b line at its midpoint."""
    mid_lat, mid_lon = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    k = math.cos(math.radians(mid_lat))
    dx, dy = (b[1] - a[1]) * k, b[0] - a[0]
    return [(mid_lat + f * dx, mid_lon - f * dy / k) for f in DETOUR_OFFSETS]


def route_overlap(a: RawRoute, b: RawRoute) -> float:
    cells_a = {(round(lat, 2), round(lon, 2)) for lat, lon in a.points}
    cells_b = {(round(lat, 2), round(lon, 2)) for lat, lon in b.points}
    return len(cells_a & cells_b) / len(cells_a | cells_b)


def truck_timeline(raw: RawRoute) -> tuple[list[float], list[float]]:
    """Cumulative (miles, seconds) along the route, with each segment capped at truck speed."""
    cum_mi, cum_s = [0.0], [0.0]
    for miles, seconds in zip(raw.seg_miles, raw.seg_seconds, strict=True):
        cum_mi.append(cum_mi[-1] + miles)
        cum_s.append(cum_s[-1] + max(seconds, miles / TRUCK_MAX_MPH * 3600))
    return cum_mi, cum_s


def build_option(label: str, raw: RawRoute, departure: datetime, interval_mi: int) -> RouteOption:
    cum_mi, cum_s = truck_timeline(raw)
    distance = cum_mi[-1]
    geometry_mi = cumulative_miles(raw.points)[-1]
    # Geometry and OSRM's annotations measure the same path slightly differently; work in OSRM miles.
    scale = distance / geometry_mi if geometry_mi > 0 else 1.0
    checkpoints = []
    for geo_mile, point in sample_along(raw.points, interval_mi / scale):
        mile = geo_mile * scale
        eta = departure + timedelta(seconds=interpolate(cum_mi, cum_s, mile))
        checkpoints.append(Checkpoint(mile, point, eta))
    return RouteOption(label, raw.summary, raw.points, distance, cum_s[-1], checkpoints)


def apply_weather(options: list[RouteOption], load_lb: float, window: ForecastWindow) -> None:
    checkpoints = [cp for option in options for cp in option.checkpoints]
    start = max(_floor_hour(min(cp.eta for cp in checkpoints)), window.start)
    end = _ceil_hour(max(cp.eta for cp in checkpoints))
    series = clients.fetch_hourly_weather([cp.point for cp in checkpoints], start, end)
    for cp, weather in zip(checkpoints, series, strict=True):
        cp.wind_mph, cp.rain_in_hr, cp.snow_in_hr = weather.conditions_at(cp.eta)
        result = assess(cp.wind_mph, cp.rain_in_hr, cp.snow_in_hr, load_lb)
        cp.risk, cp.factors = result.level, result.factors


def score_route(option: RouteOption) -> None:
    miles = {level: 0.0 for level in Risk}
    cps = option.checkpoints
    for a, b in zip(cps, cps[1:]):
        # A segment takes the worse of its two endpoint risks (conservative).
        miles[max(a.risk, b.risk)] += b.mile - a.mile
    option.miles_by_risk = miles
    total = sum(miles.values())
    if total > 0:
        option.avg_risk = sum(level * m for level, m in miles.items()) / total
    else:
        option.avg_risk = float(max(cp.risk for cp in cps))


def rank_key(option: RouteOption) -> tuple[float, ...]:
    return tuple(metric(option) for _, metric, _ in RANKING_CRITERIA)


def explain(best: RouteOption, runner_up: RouteOption | None) -> str:
    if runner_up is None:
        return f"Route {best.label} is the only route available."
    for phrase, metric, fmt in RANKING_CRITERIA:
        a, b = metric(best), metric(runner_up)
        if a != b:
            return f"Route {best.label} has the {phrase}: {fmt(a)} vs {fmt(b)} on Route {runner_up.label}."
    return f"Routes {best.label} and {runner_up.label} are tied on every criterion."


def build_heatmap(options: list[RouteOption], load_lb: float, start: datetime, window: ForecastWindow) -> dict:
    """Grid of forecast risk for up to 48 hours from `start`, limited to cells near any route."""
    anchors = [p for option in options for _, p in sample_along(option.points, HEATMAP_ANCHOR_SPACING_MI)]
    lat_min = min(p[0] for p in anchors) - HEATMAP_PAD_DEG
    lat_max = max(p[0] for p in anchors) + HEATMAP_PAD_DEG
    lon_min = min(p[1] for p in anchors) - HEATMAP_PAD_DEG
    lon_max = max(p[1] for p in anchors) + HEATMAP_PAD_DEG
    step = max(lat_max - lat_min, lon_max - lon_min) / HEATMAP_CELLS_PER_SIDE
    corridor_mi = max(HEATMAP_CORRIDOR_MI, step * MILES_PER_DEGREE_LAT * 0.75)

    cells: list[LatLon] = []
    for i in range(math.ceil((lat_max - lat_min) / step)):
        for j in range(math.ceil((lon_max - lon_min) / step)):
            center = (lat_min + (i + 0.5) * step, lon_min + (j + 0.5) * step)
            if any(haversine_mi(center, a) <= corridor_mi for a in anchors):
                cells.append(center)

    hours = min(HEATMAP_HOURS, int((window.end - start).total_seconds() // 3600))
    series = clients.fetch_hourly_weather(cells, start, start + timedelta(hours=hours))
    out_cells = []
    for (lat, lon), weather in zip(cells, series, strict=True):
        risk, wind, rain, snow = [], [], [], []
        for hour in range(hours + 1):
            w, r, s = weather.conditions_at(start + timedelta(hours=hour))
            risk.append(int(assess(w, r, s, load_lb).level))
            wind.append(round(w, 1))
            rain.append(round(r, 2))
            snow.append(round(s, 2))
        out_cells.append(
            {"lat": round(lat, 4), "lon": round(lon, 4), "risk": risk, "wind_mph": wind, "rain_in_hr": rain, "snow_in_hr": snow}
        )
    return {"start": start.isoformat(), "hours": hours, "step_deg": round(step, 4), "cells": out_cells}


def _floor_hour(when: datetime) -> datetime:
    return when.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(when: datetime) -> datetime:
    floor = _floor_hour(when)
    return floor if floor == when else floor + timedelta(hours=1)


def _place_dict(place: clients.Place) -> dict:
    return {"name": place.name, "lat": place.lat, "lon": place.lon}


def _route_dict(option: RouteOption, rank: int, departure: datetime) -> dict:
    return {
        "label": option.label,
        "summary": option.summary,
        "rank": rank,
        "distance_mi": round(option.distance_mi, 1),
        "duration_s": round(option.duration_s),
        "arrival": (departure + timedelta(seconds=option.duration_s)).isoformat(),
        "miles_by_risk": {level.label: round(miles, 1) for level, miles in option.miles_by_risk.items()},
        "avg_risk": round(option.avg_risk, 2),
        "max_risk": int(max(cp.risk for cp in option.checkpoints)),
        "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in option.points],
        "checkpoints": [
            {
                "mile": round(cp.mile, 1),
                "lat": round(cp.point[0], 5),
                "lon": round(cp.point[1], 5),
                "eta": cp.eta.isoformat(),
                "wind_mph": round(cp.wind_mph, 1),
                "rain_in_hr": round(cp.rain_in_hr, 2),
                "snow_in_hr": round(cp.snow_in_hr, 2),
                "risk": int(cp.risk),
                "factors": list(cp.factors),
            }
            for cp in option.checkpoints
        ],
    }
