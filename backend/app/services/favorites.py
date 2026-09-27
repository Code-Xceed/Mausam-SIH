"""Favorites sync store — server counterpart of the local-first dual write.

Policy (AD: local-first): the CLIENT is the source of truth for favorites.
The server is a dumb, last-write-wins mirror used for multi-device restore.
Clients push their full list; the server replaces and returns it. No
plaintext coordinates survive a purge request (DPDP), and the device id is
already a client-side hash.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.cache import cache

logger = logging.getLogger(__name__)

# In-process fallback when Redis is absent (single-instance demo is fine).
_memory: dict[str, str] = {}

TTL_S = 60 * 60 * 24 * 30  # 30 days since last touch


async def put_favorites(device_hash: str, favorites: list[dict[str, Any]]) -> None:
    payload = json.dumps(favorites, separators=(",", ":"))
    if cache.available:
        await cache.set_json(f"fav:{device_hash}", favorites, ttl_s=TTL_S)
    else:
        _memory[device_hash] = payload


async def get_favorites(device_hash: str) -> list[dict[str, Any]]:
    if cache.available:
        return await cache.get_json(f"fav:{device_hash}") or []
    raw = _memory.get(device_hash)
    return json.loads(raw) if raw else []


async def delete_favorites(device_hash: str) -> None:
    if cache.available:
        from app.core.cache import cache as c

        if c._client is not None:
            try:
                await c._client.delete(f"fav:{device_hash}")
            except Exception:  # noqa: BLE001
                pass
    _memory.pop(device_hash, None)
