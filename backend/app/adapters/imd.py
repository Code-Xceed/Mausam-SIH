"""IMD adapter (TASK-008) — live current-weather via data.gov.in.

The IMD Open Data platform exposes resources through api.data.gov.in with a
free API key. Resource IDs are configuration, not code: the team registers a
key (or uses the public sample key) and sets DATA_GOV_IMD_RESOURCE in .env.

Live payload shape (documented "Current Weather Status of Major Cities"):
    {"records": [{"station": "...", "last_updated": "...", "temp": "34.2",
                  "humidity": "58", "wind_speed": "12.4", "wind_dir": "...",
                  "weather": "Haze", ...}, ...]}

Parsing is defensive (multiple key spellings, stringy numbers) because the
platform has drifted its schema over time. Any parse failure -> None, and
the gateway falls back to the city fixture.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.adapters.base import BaseAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

_DATA_GOV_BASE = "https://api.data.gov.in/resource"

# Keyword classifier: IMD weather text -> canonical WeatherCondition value.
_CONDITION_RULES: tuple[tuple[str, str], ...] = (
    ("thunder", "thunderstorm"),
    ("hail", "hail"),
    ("snow", "snow"),
    ("shower", "rain"),
    ("rain", "rain"),
    ("drizzle", "drizzle"),
    ("fog", "fog"),
    ("mist", "fog"),
    ("haze", "haze"),
    ("smoke", "haze"),
    ("dust", "haze"),
    ("partly cloudy", "partly_cloudy"),  # must precede generic "cloudy"
    ("overcast", "cloudy"),
    ("cloudy", "cloudy"),
    ("cloud", "partly_cloudy"),
    ("clear", "clear"),
    ("sunny", "clear"),
)


def classify_condition(text: str | None) -> str:
    """Map free-text IMD weather description to a canonical condition value."""
    t = (text or "").lower()
    for needle, condition in _CONDITION_RULES:
        if needle in t:
            return condition
    return "partly_cloudy"


def _f(record: dict[str, Any], *keys: str) -> float | None:
    """Float from the first present key, tolerating stringy numbers."""
    for k in keys:
        v = record.get(k)
        if v is None:
            continue
        try:
            return float(str(v).strip())
        except (TypeError, ValueError):
            continue
    return None


class ImdAdapter(BaseAdapter):
    name = "IMD"

    async def fetch_current(self, city_name: str, state: str) -> dict[str, Any] | None:
        """Live current weather for a city, normalized to CurrentWeather fields.

        Returns None (never raises) when: no key/resource configured, HTTP
        failure, or the city isn't present in the response.
        """
        if not settings.DATA_GOV_API_KEY or not settings.DATA_GOV_IMD_RESOURCE:
            return None

        params = {
            "api-key": settings.DATA_GOV_API_KEY,
            "format": "json",
            "limit": 1000,
        }
        try:
            payload = await self._get_json(
                f"{_DATA_GOV_BASE}/{settings.DATA_GOV_IMD_RESOURCE}", params
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IMD] fetch failed: %s: %s", type(exc).__name__, exc)
            return None

        records = payload.get("records") or []
        for rec in records:
            station = str(rec.get("station") or rec.get("StationName") or "")
            if city_name.split(" (")[0].lower() not in station.lower():
                continue

            temp = _f(rec, "temp", "Temp", "temperature", "Max Temp")
            if temp is None:
                continue

            condition_text = str(
                rec.get("weather") or rec.get("Weather") or "Not available"
            )
            observed_raw = (
                rec.get("last_updated") or rec.get("LastObservedAtDate") or ""
            )
            try:
                observed = datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
            except ValueError:
                observed = datetime.now(UTC)

            return {
                "temperature_c": temp,
                "feels_like_c": _f(rec, "feels_like", "Feels Like"),
                "humidity_pct": _f(rec, "humidity", "Humidity") or 0.0,
                "wind_kmph": _f(rec, "wind_speed", "WindSpeed", "wind") or 0.0,
                "wind_direction_deg": _f(rec, "wind_dir_deg", "WindDirection"),
                "condition": classify_condition(condition_text),
                "condition_text": condition_text,
                "visibility_m": None,
                "uv_index": None,
                "observed_at": observed.isoformat(),
            }

        logger.info("[IMD] no matching station for %s in %d records", city_name, len(records))
        return None
