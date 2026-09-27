"""Compact Indian city gazetteer for Phase 1.

Purpose: any (lat, lon) snaps to the nearest of a handful of well-instrumented
demo cities, so every request resolves to a coherent, high-quality context.
Phase 3's mobile 8k-town gazetteer (TASK-025/026) is a different thing: that
one lives on-device for search UX; this one is the backend's fixture-routing
table, kept deliberately tiny and dependency-free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    key: str            # fixture stem, e.g. "delhi" -> weather_context_delhi.json
    name: str
    state: str
    lat: float
    lon: float
    marine: bool = False  # INCOIS context relevant?


CITIES: tuple[City, ...] = (
    City("delhi", "New Delhi", "Delhi", 28.6139, 77.2090),
    City("mumbai", "Mumbai", "Maharashtra", 19.0760, 72.8777, marine=True),
    City("kochi", "Kochi", "Kerala", 9.9312, 76.2673, marine=True),
    City("vidarbha", "Nagpur (Vidarbha)", "Maharashtra", 21.1458, 79.0882),
    City("shimla", "Shimla", "Himachal Pradesh", 31.1048, 77.1734),
)  # NOTE: keep this table in lockstep with mock_fixtures/weather_context_*.json

_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest_city(lat: float, lon: float) -> City:
    """Return the closest known demo city to the given coordinates."""
    return min(CITIES, key=lambda c: _haversine_km(lat, lon, c.lat, c.lon))


def city_distance_km(lat: float, lon: float, city: City) -> float:
    return _haversine_km(lat, lon, city.lat, city.lon)
