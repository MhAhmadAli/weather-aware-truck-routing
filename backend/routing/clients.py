"""Clients for free third-party services: Nominatim (geocoding), OSRM (routing), Open-Meteo (weather)."""
import math
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

import requests
from django.conf import settings

from .errors import ExternalServiceError, PlanningError
from .geo import LatLon

TIMEOUT_S = 25
METERS_PER_MILE = 1609.344
MM_PER_INCH = 25.4
CM_PER_INCH = 2.54
WEATHER_BATCH_SIZE = 100
WEATHER_MAX_CONCURRENCY = 4
NOMINATIM_MIN_INTERVAL_S = 1.0

_nominatim_lock = threading.Lock()
_nominatim_next_slot = 0.0

T = TypeVar("T")


def _get_json(url: str, params: dict, service: str) -> tuple[int, object]:
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": settings.HTTP_USER_AGENT}, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        raise ExternalServiceError(f"{service} is unreachable.") from exc
    try:
        return resp.status_code, resp.json()
    except ValueError as exc:
        raise ExternalServiceError(f"{service} returned an invalid response (HTTP {resp.status_code}).") from exc


def _parse(service: str, parser: Callable[[object], T], data: object) -> T:
    """Run `parser`, turning a response of the wrong shape into an ExternalServiceError."""
    try:
        return parser(data)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ExternalServiceError(f"{service} returned an unexpected response.") from exc


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float


def _wait_for_nominatim_slot() -> None:
    """Space requests one second apart (Nominatim's usage policy) without holding the lock during HTTP.

    The limit is per process; multiple server workers would each get their own budget.
    """
    global _nominatim_next_slot
    with _nominatim_lock:
        slot = max(time.monotonic(), _nominatim_next_slot)
        _nominatim_next_slot = slot + NOMINATIM_MIN_INTERVAL_S
    time.sleep(max(0.0, slot - time.monotonic()))


def geocode(query: str) -> Place:
    _wait_for_nominatim_slot()
    status, data = _get_json(settings.NOMINATIM_URL, {"q": query, "format": "jsonv2", "limit": 1}, "Geocoding service")
    if status != 200:
        raise ExternalServiceError(f"Geocoding service returned HTTP {status}.")
    if not data:
        raise PlanningError(f"Could not find a location matching '{query}'.")
    return _parse("Geocoding service", _parse_place, data)


def _parse_place(data: list) -> Place:
    top = data[0]
    return Place(top["display_name"], float(top["lat"]), float(top["lon"]))


@dataclass(frozen=True)
class RawRoute:
    points: list[LatLon]
    seg_miles: list[float]
    seg_seconds: list[float]
    summary: str

    @property
    def distance_mi(self) -> float:
        return sum(self.seg_miles)


def fetch_routes(waypoints: list[LatLon], alternatives: int = 0) -> list[RawRoute]:
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "distance,duration",
        # OSRM only fills in leg summaries (main road names) when steps are requested.
        "steps": "true",
        "alternatives": str(alternatives) if alternatives else "false",
    }
    status, data = _get_json(f"{settings.OSRM_URL}/route/v1/driving/{coords}", params, "Routing service")
    code = data.get("code") if isinstance(data, dict) else None
    if code in ("NoRoute", "NoSegment"):
        raise PlanningError("No drivable route was found between these locations.")
    if status != 200 or code != "Ok":
        raise ExternalServiceError(f"Routing service error: {code or f'HTTP {status}'}.")
    routes = _parse("Routing service", lambda d: [_parse_route(route) for route in d["routes"]], data)
    if not routes:
        raise ExternalServiceError("Routing service returned no routes.")
    return routes


def _parse_route(route: dict) -> RawRoute:
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    seg_m: list[float] = []
    seg_s: list[float] = []
    names: list[str] = []
    for leg in route["legs"]:
        seg_m.extend(leg["annotation"]["distance"])
        seg_s.extend(leg["annotation"]["duration"])
        for name in re.split(r"[,;]\s*", leg.get("summary") or ""):
            if name and name not in names:
                names.append(name)
    return RawRoute(points, [m / METERS_PER_MILE for m in seg_m], seg_s, ", ".join(names))


@dataclass(frozen=True)
class HourlyWeather:
    start: datetime
    wind_mph: list[float]
    rain_in: list[float]
    snow_in: list[float]

    def conditions_at(self, when: datetime) -> tuple[float, float, float]:
        """(wind mph, rain in/hr, snow in/hr) at `when`.

        Wind is instantaneous, so the nearest hour is used. Open-Meteo precipitation is the
        total of the preceding hour, so the hour ending at or after `when` is used.
        """
        hours = (when - self.start).total_seconds() / 3600
        last = len(self.wind_mph) - 1
        wind_i = min(max(math.floor(hours + 0.5), 0), last)
        precip_i = min(max(math.ceil(hours), 0), last)
        return self.wind_mph[wind_i], self.rain_in[precip_i], self.snow_in[precip_i]


def fetch_hourly_weather(points: list[LatLon], start: datetime, end: datetime) -> list[HourlyWeather]:
    """Hourly weather for each point from `start` to `end` (UTC, whole hours), in input order."""
    keys = [(round(lat, 2), round(lon, 2)) for lat, lon in points]
    unique = list(dict.fromkeys(keys))
    batches = [unique[i : i + WEATHER_BATCH_SIZE] for i in range(0, len(unique), WEATHER_BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=WEATHER_MAX_CONCURRENCY) as pool:
        results = list(pool.map(lambda batch: _fetch_batch(batch, start, end), batches))
    by_key: dict[LatLon, HourlyWeather] = {}
    for batch, series in zip(batches, results, strict=True):
        by_key.update(zip(batch, series, strict=True))
    return [by_key[key] for key in keys]


def _fetch_batch(points: list[LatLon], start: datetime, end: datetime) -> list[HourlyWeather]:
    params = {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.2f}" for _, lon in points),
        "hourly": "wind_speed_10m,rain,showers,snowfall",
        "wind_speed_unit": "mph",
        "timezone": "UTC",
        "start_hour": _iso_hour(start),
        "end_hour": _iso_hour(end),
    }
    status, data = _get_json(settings.OPEN_METEO_URL, params, "Weather service")
    if status != 200:
        reason = data.get("reason") if isinstance(data, dict) else None
        raise ExternalServiceError(f"Weather service error: {reason or f'HTTP {status}'}.")
    items = data if isinstance(data, list) else [data]
    series = _parse("Weather service", lambda xs: [_parse_hourly(item["hourly"]) for item in xs], items)
    if len(series) != len(points):
        raise ExternalServiceError("Weather service returned the wrong number of locations.")
    return series


def _parse_hourly(hourly: dict) -> HourlyWeather:
    start = datetime.fromisoformat(hourly["time"][0]).replace(tzinfo=timezone.utc)
    wind = [_num(v) for v in hourly["wind_speed_10m"]]
    rain = [(_num(r) + _num(s)) / MM_PER_INCH for r, s in zip(hourly["rain"], hourly["showers"], strict=True)]
    snow = [_num(v) / CM_PER_INCH for v in hourly["snowfall"]]
    if not (len(hourly["time"]) == len(wind) == len(rain) == len(snow)):
        raise ValueError("hourly series have different lengths")
    return HourlyWeather(start, wind, rain, snow)


def _num(value: float | None) -> float:
    # Open-Meteo returns null for hours a model doesn't cover.
    return float(value) if value is not None else 0.0


def _iso_hour(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
