"""CPCB CAAQMS adapter (TASK-009) — live AQI via data.gov.in.

Verified resource: "Real time Air Quality Index from various locations"
    resource id : 3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69
    row shape   : {"state": "Delhi", "city": "Delhi", "station": "Anand Vihar, Delhi",
                   "pollutant_id": "PM2.5", "pollutant_min": "…", "pollutant_max": "…",
                   "pollutant_avg": "…", "last_update": "…"}

One row = one pollutant at one station. We group rows by station, compute
the official NAQI composite (aqi_math), and pick the station with the
richest pollutant coverage for the requested city.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.adapters.base import BaseAdapter
from app.core.config import settings
from app.services.aqi_math import POLLUTANT_ALIASES, composite_aqi

logger = logging.getLogger(__name__)

_DATA_GOV_BASE = "https://api.data.gov.in/resource"
AQI_RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"


def aggregate_city(rows: list[dict[str, Any]], city_name: str) -> dict[str, Any] | None:
    """Pure normalization: group pollutant rows by station, score, pick best.

    Returns AirQualityIndex-compatible fields (+ 'station') or None when no
    usable station exists for the city. Extracted for unit testing.
    """
    # station -> {canonical_pollutant: avg concentration}
    stations: dict[str, dict[str, float]] = defaultdict(dict)
    last_update: str | None = None
    wanted = city_name.split(" (")[0].lower()

    for row in rows:
        city = str(row.get("city") or "")
        if wanted not in city.lower():
            continue
        pollutant = POLLUTANT_ALIASES.get(
            str(row.get("pollutant_id") or "").lower().replace(" ", "_")
        )
        if pollutant is None:
            continue
        try:
            value = float(str(row.get("pollutant_avg")).strip())
        except (TypeError, ValueError, AttributeError):
            continue
        station = str(row.get("station") or "unknown")
        stations[station][pollutant] = value
        last_update = row.get("last_update") or last_update

    if not stations:
        return None

    # Station with the most pollutant coverage wins; composite NAQI decides.
    best_station, best_readings, best_aqi, best_dominant = "", {}, -1, None
    for station, readings in stations.items():
        aqi, dominant = composite_aqi(readings)
        score = (len(readings), aqi)
        if score > (len(best_readings), best_aqi):
            best_station, best_readings = station, readings
            best_aqi, best_dominant = aqi, dominant

    if best_aqi <= 0:
        return None

    return {
        "aqi": best_aqi,
        "dominating_pollutant": best_dominant,
        "station": best_station,
        **{f"{k}_ugm3": v for k, v in best_readings.items() if k != "co"},
        **({"co_mgm3": best_readings["co"]} if "co" in best_readings else {}),
        "last_update": last_update,
    }


class CpcbAdapter(BaseAdapter):
    name = "CPCB"

    async def fetch_aqi(self, city_name: str, state: str) -> dict[str, Any] | None:
        """Live AQI for a city, normalized to AirQualityIndex fields.

        Returns None (never raises) when no key configured, HTTP failure,
        or no usable stations.
        """
        if not settings.DATA_GOV_API_KEY:
            return None

        params = {
            "api-key": settings.DATA_GOV_API_KEY,
            "format": "json",
            "limit": 2000,
            "filters[state]": state,
        }
        try:
            payload = await self._get_json(f"{_DATA_GOV_BASE}/{AQI_RESOURCE_ID}", params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CPCB] fetch failed: %s: %s", type(exc).__name__, exc)
            return None

        rows = payload.get("records") or []
        if not rows:
            return None

        result = aggregate_city(rows, city_name)
        if result is None:
            logger.info("[CPCB] no stations for city=%s state=%s", city_name, state)
            return None

        observed = datetime.now(UTC)
        if last_update := result.pop("last_update", None):
            try:
                observed = datetime.fromisoformat(str(last_update).replace("Z", "+00:00"))
            except ValueError:
                pass
        result["observed_at"] = observed.isoformat()
        return result
