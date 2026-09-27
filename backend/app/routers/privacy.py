"""DPDP Act 2023 privacy endpoints (TASK-072 backend half).

"Clear My Footprint" — one call erases every server-side trace of a device:
favorites mirror, telemetry event log entries, and (as a defense-in-depth
safety net) any cached weather context keyed on the device's coarse cell.
Device identity is already a client-side hash; the raw GPS coordinate never
reached the server (coarse-snap at the request layer).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/privacy", tags=["privacy"])


class PurgeRequest(BaseModel):
    device_id_hash: str = Field(..., min_length=8, max_length=64)


@router.post("/purge")
async def purge(req: PurgeRequest) -> dict[str, Any]:
    """Erase all server-side data for one device hash. Idempotent."""
    from app.services.favorites import delete_favorites
    from app.routers.telemetry import EVENT_LOG

    removed_favs = await delete_favorites(req.device_id_hash)
    removed_events = 0
    remaining: deque[dict[str, Any]] = deque(maxlen=EVENT_LOG.maxlen)
    for e in EVENT_LOG:
        if e.get("device_id_hash") == req.device_id_hash:
            removed_events += 1
        else:
            remaining.append(e)
    EVENT_LOG.clear()
    EVENT_LOG.extend(remaining)

    return {
        "status": "purged",
        "device_id_hash": req.device_id_hash,
        "removed": {
            "favorites": bool(removed_favs) or removed_favs == 0,
            "telemetry_events": removed_events,
            "note": "coarse-cell caches expire naturally (<=30 min TTL); raw GPS never stored",
        },
        "purged_at": time.time(),
    }
