"""INCOIS marine adapter (TASK-010).

INCOIS publishes Ocean State Forecasts (INDOFOS) but has no stable public
REST endpoint; access is typically via their portal/products. Live mode is
therefore URL-configurable (INCOIS_OSF_URL) and expects a simple JSON
document. When absent, fixtures + a synthetic astronomical tide model carry
the marine personas.

The tide model (synth_tides) generates a plausible semi-diurnal tide curve
dominated by the M2 constituent — good enough to animate the Phase 4 tide
sine chart honestly (labeled as modeled when used).
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.adapters.base import BaseAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

# M2 principal lunar semi-diurnal constituent: period ≈ 12.42 h
_M2_PERIOD_H = 12.4206012


def synth_tides(
    now: datetime | None = None, amplitude_m: float = 0.9, seed_phase: float = 0.0
) -> dict[str, Any]:
    """Synthetic semi-diurnal tide state anchored to *now*.

    Returns tide height/state, next high/low times, and a 24h curve for the
    Phase 4 sine chart.
    """
    now = now or datetime.now(UTC)
    omega = 2 * math.pi / _M2_PERIOD_H
    phase = (now.timestamp() / 3600.0) * omega + seed_phase
    height = amplitude_m * math.sin(phase)

    # Next extremes: scan the next 13h in 5-minute steps.
    next_high = next_low = None
    h = now
    for _ in range(13 * 12):
        h = h + timedelta(minutes=5)
        hh = amplitude_m * math.sin((h.timestamp() / 3600.0) * omega + seed_phase)
        if next_high is None and hh >= amplitude_m * 0.999:
            next_high = h
        if next_low is None and hh <= -amplitude_m * 0.999:
            next_low = h
        if next_high and next_low:
            break

    tide_state = "rising" if math.cos(phase) > 0 else "falling"
    if height >= amplitude_m * 0.999:
        tide_state = "high"
    elif height <= -amplitude_m * 0.999:
        tide_state = "low"

    curve = []
    for i in range(24 * 4):  # 15-min resolution for 24h
        t = now + timedelta(minutes=15 * i)
        curve.append(
            {
                "time": t.isoformat(),
                "height_m": round(amplitude_m * math.sin((t.timestamp() / 3600.0) * omega + seed_phase), 3),
            }
        )

    return {
        "tide_height_m": round(height, 3),
        "tide_state": tide_state,
        "next_high_tide": next_high.isoformat() if next_high else None,
        "next_low_tide": next_low.isoformat() if next_low else None,
        "tide_curve": curve,
    }


class IncoisAdapter(BaseAdapter):
    name = "INCOIS"

    async def fetch_marine(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Live marine observation if INCOIS_OSF_URL is configured and works.

        Expected (configurable) JSON shape:
            {"significant_wave_height_m": 1.4, "swell_period_s": 11.0, "sst_c": 28.4, ...}
        """
        if not settings.INCOIS_OSF_URL:
            return None
        try:
            return await self._get_json(
                settings.INCOIS_OSF_URL, {"lat": round(lat, 2), "lon": round(lon, 2)}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[INCOIS] fetch failed: %s: %s", type(exc).__name__, exc)
            return None


def enrich_marine_fixture(marine: dict[str, Any]) -> dict[str, Any]:
    """Fill fixture marine blocks with a live-computed tide state + curve."""
    marine.update(synth_tides())
    return marine
