"""NDMA SACHET CAP poller (TASK-048) — 60 s heartbeat for the alert pipeline.

Loop per tick:
    1. Fetch the CAP feed (live URL when configured; fixture in SEED/absent).
    2. Diff against the store: new identifiers → ingest; gone identifiers →
       remove (unless injected by the demo admin tool).
    3. For each NEW alert, resolve geofence targets and dispatch FCM pushes.

Runs as an asyncio task started in the FastAPI lifespan. All failures are
logged and swallowed — a dead feed must never crash the app; the store keeps
serving the last known alerts until expiry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from app.adapters.cap import CapAdapter, parse_cap_xml
from app.core.config import settings
from app.services.alert_store import alert_store

logger = logging.getLogger(__name__)


class CapPoller:
    """Periodic CAP feed poller driving ingest + push fan-out."""

    def __init__(self, interval_s: int | None = None) -> None:
        self.interval_s = interval_s or settings.CAP_POLL_INTERVAL_S
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._adapter = CapAdapter()
        self.last_poll_ts: float | None = None
        self.last_error: str | None = None
        self.poll_count = 0
        # Injector hook (tests/admin tool replace this to bypass network).
        self.fetch_alerts = self._fetch

    async def _fetch(self) -> list[dict]:
        """Live-or-fixture fetch. SEED mode / no URL → bundled fixture."""
        if settings.CAP_FEED_URL and settings.API_MODE != "SEED":
            try:
                from app.adapters.base import get_http_client

                client = await get_http_client()
                resp = await client.get(settings.CAP_FEED_URL)
                resp.raise_for_status()
                return parse_cap_xml(resp.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[cappoller] live poll failed: %s: %s",
                               type(exc).__name__, exc)
        fixture = self._fixture_path()
        if fixture:
            from pathlib import Path

            return parse_cap_xml(
                Path(fixture).read_text(encoding="utf-8"), expired_policy="extend"
            )
        return []

    @staticmethod
    def _fixture_path() -> str | None:
        from pathlib import Path

        p = Path(__file__).resolve().parents[3] / "mock_fixtures" / "cap_alerts.xml"
        return str(p) if p.exists() else None

    def _diff_ingest(self, alerts: list[dict]) -> tuple[list[dict], list[str]]:
        """Returns (new_alerts, removed_ids). Injected alerts survive removal."""
        from app.services.alert_store import alert_store

        fresh: list[dict] = []
        for a in alerts:
            ident = a.get("identifier")
            if ident and not alert_store._alerts.get(ident):
                fresh.append(a)

        current_ids = {a.get("identifier") for a in alerts if a.get("identifier")}
        removed: list[str] = []
        for ident in list(alert_store._alerts):
            if ident not in current_ids and ident not in alert_store._injected:
                removed.append(ident)
        for ident in removed:
            alert_store.remove(ident)
        return fresh, removed

    async def poll_once(self) -> dict:
        """One poll cycle — also the unit-test entrypoint."""
        t0 = time.perf_counter()
        fetch_ok = True
        try:
            alerts = await self.fetch_alerts()
        except Exception as exc:  # noqa: BLE001
            fetch_ok = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("[cappoller] fetch failed: %s", self.last_error)
            alerts = []

        new_alerts, removed = self._diff_ingest(alerts)
        ingested = alert_store.put_many(new_alerts)

        pushed = 0
        if new_alerts:
            from app.services.dispatcher import dispatch_alert

            for a in new_alerts:
                try:
                    result = await dispatch_alert(a)
                    pushed += result.get("sent", 0)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[cappoller] dispatch failed for %s: %s",
                                   a.get("identifier"), exc)

        self.poll_count += 1
        self.last_poll_ts = time.time()
        if fetch_ok:
            self.last_error = None  # only clear on a healthy fetch
        return {
            "fetched": len(alerts),
            "new": ingested,
            "removed": len(removed),
            "pushed": pushed,
            "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

    async def _run(self) -> None:
        logger.info("[cappoller] started (every %ss)", self.interval_s)
        # First tick fires immediately so demo boots with alerts loaded.
        while not self._stop.is_set():
            try:
                stats = await self.poll_once()
                logger.debug("[cappoller] tick: %s", stats)
            except Exception as exc:  # noqa: BLE001 — never die
                logger.warning("[cappoller] tick error: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                continue
        logger.info("[cappoller] stopped")

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        # Re-bind the stop event to the CURRENT running loop: asyncio
        # primitives are loop-bound at first use, and tests boot/stop a
        # lifespan per TestClient (fresh loop each). Reusing an import-time
        # Event makes later lifespans' stop() raise "bound to a different
        # event loop".
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None


poller = CapPoller()
