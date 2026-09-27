"""Favorites sync endpoints — server mirror for the local-first client.

POST /v1/favorites/sync           — push full favorites list (last-write-wins)
GET  /v1/favorites/sync/{hash}    — pull list (restore on new device)
DELETE /v1/favorites/sync/{hash}  — purge (DPDP "Clear My Footprint" hook)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, field_validator

from app.services import favorites as fav_store

router = APIRouter(prefix="/v1/favorites", tags=["favorites"])


class FavoriteItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    added_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class FavoritesPush(BaseModel):
    device_id_hash: str = Field(..., min_length=8, max_length=128)
    favorites: list[FavoriteItem] = Field(default_factory=list, max_length=50)


@router.post("/sync", status_code=204)
async def push_favorites(push: FavoritesPush) -> Response:
    items = [
        {
            "name": f.name,
            "lat": f.lat,
            "lon": f.lon,
            "added_at": (f.added_at or datetime.now(UTC)).isoformat(),
        }
        for f in push.favorites
    ]
    await fav_store.put_favorites(push.device_id_hash, items)
    return Response(status_code=204)


@router.get("/sync/{device_id_hash}")
async def pull_favorites(device_id_hash: str) -> dict[str, Any]:
    items = await fav_store.get_favorites(device_id_hash)
    return {"favorites": items}


@router.delete("/sync/{device_id_hash}", status_code=204)
async def purge_favorites(device_id_hash: str) -> Response:
    await fav_store.delete_favorites(device_id_hash)
    return Response(status_code=204)
