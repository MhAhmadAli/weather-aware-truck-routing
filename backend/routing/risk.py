"""Weather risk classification using the provided threshold and load rules."""
from dataclasses import dataclass
from enum import IntEnum

LOAD_NO_TRAVEL_LB = 30_000
LOAD_SEVERE_LB = 40_000


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


def classify_wind(mph: float) -> Risk:
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def classify_rain(in_per_hr: float) -> Risk:
    if in_per_hr > 1.0:
        return Risk.NO_TRAVEL
    if in_per_hr >= 0.5:
        return Risk.SEVERE
    if in_per_hr >= 0.25:
        return Risk.HIGH
    if in_per_hr >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def classify_snow(in_per_hr: float) -> Risk:
    if in_per_hr > 3.0:
        return Risk.NO_TRAVEL
    if in_per_hr >= 2.0:
        return Risk.SEVERE
    if in_per_hr >= 1.0:
        return Risk.HIGH
    if in_per_hr >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def apply_load_rules(wind_mph: float, load_lb: float, wind_risk: Risk) -> Risk:
    if 45 <= wind_mph < 55 and load_lb > LOAD_NO_TRAVEL_LB:
        return Risk.NO_TRAVEL
    if 35 <= wind_mph < 45 and load_lb > LOAD_SEVERE_LB:
        return max(wind_risk, Risk.SEVERE)
    return wind_risk


@dataclass(frozen=True)
class Assessment:
    level: Risk
    factors: tuple[str, ...]


def assess(wind_mph: float, rain_in_per_hr: float, snow_in_per_hr: float, load_lb: float) -> Assessment:
    base_wind = classify_wind(wind_mph)
    wind = apply_load_rules(wind_mph, load_lb, base_wind)
    levels = {
        "Wind": wind,
        "Rain": classify_rain(rain_in_per_hr),
        "Snow": classify_snow(snow_in_per_hr),
    }
    level = max(levels.values())
    if level == Risk.LOW:
        return Assessment(level, ())
    factors = tuple(
        "Wind + load" if name == "Wind" and wind != base_wind else name
        for name, factor_level in levels.items()
        if factor_level == level
    )
    return Assessment(level, factors)
