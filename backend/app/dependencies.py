"""Shared API dependencies."""

from __future__ import annotations

from fastapi import Query

from app.models.weather import snap_geohash5


async def coarse_location(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
) -> tuple[float, float]:
    """Request-scoped coordinates. Snap to coarse grid at the edge (DPDP)."""
    return lat, lon


def geohash_for(lat: float, lon: float) -> str:
    return snap_geohash5(lat, lon)
