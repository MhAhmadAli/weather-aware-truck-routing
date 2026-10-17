import math
from bisect import bisect_right

LatLon = tuple[float, float]

EARTH_RADIUS_MI = 3958.8
# A leftover shorter than this fraction of the interval is folded into the destination.
MIN_FINAL_GAP_FRACTION = 0.1


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(points: list[LatLon]) -> list[float]:
    cum = [0.0]
    for prev, cur in zip(points, points[1:]):
        cum.append(cum[-1] + haversine_mi(prev, cur))
    return cum


def interpolate(xs: list[float], ys: list[float], x: float) -> float:
    """Piecewise-linear lookup of y at x; xs must be non-decreasing."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x) - 1
    span = xs[i + 1] - xs[i]
    frac = (x - xs[i]) / span if span > 0 else 0.0
    return ys[i] + frac * (ys[i + 1] - ys[i])


def sample_along(points: list[LatLon], interval_mi: float) -> list[tuple[float, LatLon]]:
    """Points every `interval_mi` along the polyline, always including both ends."""
    cum = cumulative_miles(points)
    total = cum[-1]
    targets = [i * interval_mi for i in range(int(total // interval_mi) + 1)]
    remainder = total - targets[-1]
    if len(targets) > 1 and remainder < interval_mi * MIN_FINAL_GAP_FRACTION:
        targets[-1] = total
    elif remainder > 0:
        targets.append(total)
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return [(t, (interpolate(cum, lats, t), interpolate(cum, lons, t))) for t in targets]
