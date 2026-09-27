"""MOSDAC satellite adapter (TASK-011) — Phase 1 stub.

INSAT-3D/DR products (SWIR/MIR fog index, OLR, soil moisture, QPE) are
distributed as HDF5 behind MOSDAC user registration; the download API is
not usable without credentials. Full ingestion lands with Phase 4's
commuter fog widget (TASK-037), where fog risk is derived from IMD
visibility in the interim:

    visibility_m >= 1000  -> nil / light fog
    500..999              -> moderate fog, commute delay possible
    < 500                 -> dense fog, expect major delays

This module stays the single seam where MOSDAC ingestion will attach.
"""

from __future__ import annotations

from typing import Any


def fog_index_from_visibility(visibility_m: int | float | None) -> float:
    """0 (clear) .. 1 (dense fog) — interim proxy until MOSDAC SWIR/MIR lands."""
    if visibility_m is None:
        return 0.0
    v = float(visibility_m)
    if v >= 2000:
        return 0.0
    if v >= 1000:
        return 0.2
    if v >= 500:
        return 0.6
    if v >= 200:
        return 0.85
    return 1.0


class MosdacAdapter:
    """Placeholder — real ingestion arrives with Phase 4 (TASK-037)."""

    name = "MOSDAC"

    async def fetch_fog(self, lat: float, lon: float) -> dict[str, Any] | None:
        return None
