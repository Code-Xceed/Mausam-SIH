"""Lifespan-managed Redis cache with graceful no-Redis degradation.

The backend must boot and serve fixtures even when Redis is absent —
cache is a performance layer, never a dependency.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import guard
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None  # type: ignore[assignment]


class Cache:
    """Thin async Redis wrapper; every method no-ops cleanly without Redis."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def connect(self) -> None:
        if aioredis is None:
            logger.warning("redis package not installed — running cacheless")
            return
        try:
            self._client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=1.0,
            )
            await self._client.ping()
            self._available = True
            logger.info("Redis connected at %s", settings.REDIS_URL)
        except Exception as exc:  # noqa: BLE001 — any Redis failure is non-fatal
            self._client = None
            self._available = False
            logger.warning("Redis unavailable (%s) — serving uncached", exc)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
        self._available = False

    async def get_json(self, key: str) -> Any | None:
        if not self._available or self._client is None:
            return None
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception:  # noqa: BLE001
            return None

    async def set_json(self, key: str, value: Any, ttl_s: int) -> None:
        if not self._available or self._client is None:
            return
        try:
            await self._client.set(key, json.dumps(value), ex=ttl_s)
        except Exception:  # noqa: BLE001
            pass


cache = Cache()
