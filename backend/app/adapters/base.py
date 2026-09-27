"""Adapter primitives: BaseAdapter + HybridCircuitBreaker (TASK-014).

Every sovereign data source gets an adapter with the same shape:
    async def fetch(...) -> Model | None

`None` means "no usable data" — adapters never raise upward; they log and
return None so one dead source can never take the whole context down.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Generic, TypeVar

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Shared async client (connection pooling, HTTP/2-ready). Created lazily
# inside a running loop; closed on app shutdown.
_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.LIVE_TIMEOUT_MS / 1000),
            headers={"User-Agent": "mausam-nextgen/0.1 (SIH26076)"},
            follow_redirects=True,
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


class HybridCircuitBreaker:
    """Live-first with a hard timeout budget, then fixture replay.

    States:
      CLOSED   — live calls allowed; successes/failures tracked.
      OPEN     — live calls skipped entirely until `reset_time_s` elapses;
                 every request goes straight to fixtures.
    A demo venue with dead Wi-Fi converges to OPEN within a few requests,
    after which responses are pure local I/O — effectively instant.
    """

    def __init__(
        self,
        timeout_ms: int | None = None,
        failure_threshold: int = 3,
        reset_time_s: float = 60.0,
    ) -> None:
        self.timeout_s = (timeout_ms or settings.LIVE_TIMEOUT_MS) / 1000
        self.failure_threshold = failure_threshold
        self.reset_time_s = reset_time_s
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_time_s:
            # Half-open: give live one more shot.
            self._opened_at = None
            self._consecutive_failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
            logger.warning(
                "circuit OPEN for %ss after %d consecutive failures",
                self.reset_time_s,
                self._consecutive_failures,
            )

    async def call(
        self,
        live: Callable[[], Awaitable[T]],
        fallback: Callable[[], Awaitable[T] | T],
        *,
        label: str,
    ) -> tuple[T, str]:
        """Run `live` with the timeout budget; on any problem run `fallback`.

        Returns (result, source) where source ∈ {"live", "fixture", "error"}.
        Never raises upward for network problems — `fallback` must succeed.
        """
        if self.is_open:
            result = fallback()
            if asyncio.iscoroutine(result):
                result = await result
            return result, "fixture"

        try:
            result = await asyncio.wait_for(live(), timeout=self.timeout_s)
            self.record_success()
            return result, "live"
        except Exception as exc:  # noqa: BLE001 — anything live-side is non-fatal
            self.record_failure()
            logger.warning("[%s] live fetch failed (%s: %s) — using fixture",
                           label, type(exc).__name__, exc)
            fb = fallback()
            if asyncio.iscoroutine(fb):
                fb = await fb
            return fb, "fixture"


class BaseAdapter:
    """Name + shared HTTP plumbing for sovereign data adapters."""

    name: str = "base"

    async def fetch(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    @staticmethod
    async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
        client = await get_http_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
