"""Geo endpoints (TASK-059/060): boundaries + viewport tiles.

Payload size is a feature here — TASK-059's <60 KB budget is asserted in
tests. Responses compress via the app-wide GZip middleware.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.geo_tiles import build_tile, boundaries_featurecollection

router = APIRouter(prefix="/v1/geo", tags=["geo"])


@router.get("/boundaries")
async def boundaries() -> dict:
    """Simplified state boundaries (TASK-060) — schematic demo rings."""
    return boundaries_featurecollection()


@router.get("/tile/{z}/{x}/{y}")
async def tile(z: int, x: int, y: str) -> dict:
    """One viewport bundle: boundaries + active CAP polygons.

    Accepts a trailing `.json` suffix (slippy-map convention); returns 404
    for out-of-range tiles (z 0..12 kept deliberately small — higher zooms
    are the client's vector-tile ring-buffer's job, TASK-057).
    """
    y = y.removesuffix(".json")
    try:
        y_num = int(y)
    except ValueError:
        raise HTTPException(404, "bad tile coordinate") from None
    if not (0 <= z <= 12):
        raise HTTPException(404, "zoom must be 0..12")
    n = 2**z
    if not (0 <= x < n and 0 <= y_num < n):
        raise HTTPException(404, "tile out of range")
    return build_tile(z, x, y_num)
