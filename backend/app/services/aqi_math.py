"""CPCB National Air Quality Index (NAQI) mathematics — India 2014 standard.

Implements the official breakpoint table and linear sub-index interpolation
published by the Central Pollution Control Board. The composite AQI is the
maximum of pollutant sub-indices; the "dominating pollutant" is the argmax.

Adapters must NOT trust upstream category strings — everything client-visible
is derived here (see AD-005).
"""

from __future__ import annotations

from typing import NamedTuple


class Breakpoint(NamedTuple):
    c_lo: float   # concentration lower bound (inclusive)
    c_hi: float   # concentration upper bound
    i_lo: int     # index lower bound
    i_hi: int     # index upper bound


# pollutant -> official CPCB concentration breakpoints
# (µg/m³ except CO which is mg/m³)
BREAKPOINTS: dict[str, tuple[Breakpoint, ...]] = {
    "pm2_5": (
        Breakpoint(0, 30, 0, 50),
        Breakpoint(30, 60, 51, 100),
        Breakpoint(60, 90, 101, 200),
        Breakpoint(90, 120, 201, 300),
        Breakpoint(120, 250, 301, 400),
        Breakpoint(250, 380, 401, 500),
    ),
    "pm10": (
        Breakpoint(0, 50, 0, 50),
        Breakpoint(50, 100, 51, 100),
        Breakpoint(100, 250, 101, 200),
        Breakpoint(250, 350, 201, 300),
        Breakpoint(350, 430, 301, 400),
        Breakpoint(430, 510, 401, 500),
    ),
    "no2": (
        Breakpoint(0, 40, 0, 50),
        Breakpoint(40, 80, 51, 100),
        Breakpoint(80, 180, 101, 200),
        Breakpoint(180, 280, 201, 300),
        Breakpoint(280, 400, 301, 400),
        Breakpoint(400, 520, 401, 500),
    ),
    "so2": (
        Breakpoint(0, 40, 0, 50),
        Breakpoint(40, 80, 51, 100),
        Breakpoint(80, 380, 101, 200),
        Breakpoint(380, 800, 201, 300),
        Breakpoint(800, 1600, 301, 400),
        Breakpoint(1600, 2400, 401, 500),
    ),
    "o3": (
        Breakpoint(0, 50, 0, 50),
        Breakpoint(50, 100, 51, 100),
        Breakpoint(100, 168, 101, 200),
        Breakpoint(168, 208, 201, 300),
        Breakpoint(208, 748, 301, 400),
        Breakpoint(748, 1000, 401, 500),
    ),
    "co": (  # mg/m³
        Breakpoint(0.0, 1.0, 0, 50),
        Breakpoint(1.0, 2.0, 51, 100),
        Breakpoint(2.0, 10.0, 101, 200),
        Breakpoint(10.0, 17.0, 201, 300),
        Breakpoint(17.0, 34.0, 301, 400),
        Breakpoint(34.0, 51.0, 401, 500),
    ),
    "nh3": (
        Breakpoint(0, 200, 0, 50),
        Breakpoint(200, 400, 51, 100),
        Breakpoint(400, 800, 101, 200),
        Breakpoint(800, 1200, 201, 300),
        Breakpoint(1200, 1800, 301, 400),
        Breakpoint(1800, 2400, 401, 500),
    ),
}

# Field-name aliases used by data.gov.in CPCB payloads -> canonical keys here.
POLLUTANT_ALIASES: dict[str, str] = {
    "pm2_5": "pm2_5",
    "pm2.5": "pm2_5",
    "pm25": "pm2_5",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "o3": "o3",
    "ozone": "o3",
    "co": "co",
    "nh3": "nh3",
    "ammonia": "nh3",
}


def sub_index(pollutant: str, concentration: float | None) -> float | None:
    """Linear-interpolated NAQI sub-index for one pollutant, or None if absent/invalid."""
    if concentration is None or concentration < 0:
        return None
    key = POLLUTANT_ALIASES.get(pollutant.lower().replace(" ", "_"))
    if key is None:
        return None
    for bp in BREAKPOINTS[key]:
        if concentration <= bp.c_hi:
            if bp.c_hi == bp.c_lo:  # degenerate guard
                return float(bp.i_hi)
            frac = (bp.i_hi - bp.i_lo) / (bp.c_hi - bp.c_lo)
            return round(bp.i_lo + frac * (concentration - bp.c_lo), 1)
    return 500.0  # above the highest breakpoint saturates the index


def composite_aqi(readings: dict[str, float | None]) -> tuple[int, str | None]:
    """Composite NAQI = max sub-index across pollutants.

    Returns (aqi, dominating_pollutant). Pollutants with missing/invalid
    concentrations are skipped. If nothing is usable, returns (0, None).
    """
    best_val = -1.0
    best_key: str | None = None
    for raw_key, value in readings.items():
        key = POLLUTANT_ALIASES.get(raw_key.lower().replace(" ", "_"))
        if key is None:
            continue
        si = sub_index(key, value)
        if si is not None and si > best_val:
            best_val = si
            best_key = key
    if best_key is None:
        return 0, None
    return int(round(min(best_val, 500.0))), best_key
