"""Active-alert store with expiry sweep — Phase 6 brain between poller and push.

Keeps the currently-active parsed CAP alerts (fixture, live, or injected by
the demo admin tool), their resolved push targets, and a bounded event log.
Expiry is swept lazily on every access — no background timer needed; the
CAP_POLL_INTERVAL_S poller is the heartbeat.

The store is process-local (Redis later; single-instance demo is the target).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.services.geofence import TargetSet, alert_target_set

logger = logging.getLogger(__name__)


class AlertStore:
    """Process-local active CAP alert registry with lazy expiry sweep."""

    def __init__(self) -> None:
        self._alerts: dict[str, dict[str, Any]] = {}       # identifier → alert
        self._targets: dict[str, TargetSet] = {}
        self._injected: set[str] = set()                    # demo-injected ids
        self._events: deque[dict[str, Any]] = deque(maxlen=200)

    # ------------------------------------------------------------------ #
    # Write path
    # ------------------------------------------------------------------ #

    def put(self, alert: dict[str, Any], *, injected: bool = False) -> None:
        """Insert or replace an alert and (re)resolve its push targets."""
        ident = alert.get("identifier") or f"anon-{int(time.time() * 1000)}"
        alert = dict(alert)
        alert["identifier"] = ident
        # Injected demo alerts expire in 2h unless the source set one.
        if injected and not alert.get("expires"):
            alert["expires"] = (
                datetime.now(UTC).timestamp() + 7200
            )
            alert["expires"] = datetime.fromtimestamp(
                alert["expires"], tz=UTC
            ).isoformat()
        self._alerts[ident] = alert
        try:
            self._targets[ident] = alert_target_set(alert)
        except Exception as exc:  # noqa: BLE001 — geometry must never kill intake
            logger.warning("[alertstore] target resolution failed for %s: %s", ident, exc)
            self._targets[ident] = TargetSet()
        if injected:
            self._injected.add(ident)
        self._events.append(
            {
                "ts": time.time(),
                "kind": "inject" if injected else "ingest",
                "identifier": ident,
                "event": alert.get("event"),
                "severity": alert.get("severity"),
            }
        )
        logger.info(
            "[alertstore] %s %s (%s) targets=%d",
            "injected" if injected else "ingested",
            ident,
            alert.get("severity"),
            self._targets[ident].size,
        )

    def put_many(self, alerts: list[dict[str, Any]], *, injected: bool = False) -> int:
        n = 0
        for a in alerts:
            self.put(a, injected=injected)
            n += 1
        return n

    def remove(self, identifier: str) -> bool:
        existed = self._alerts.pop(identifier, None) is not None
        self._targets.pop(identifier, None)
        self._injected.discard(identifier)
        if existed:
            self._events.append({"ts": time.time(), "kind": "remove", "identifier": identifier})
        return existed

    def clear_injected(self) -> int:
        """Remove all demo-injected alerts (admin: end the staged disaster)."""
        ids = [i for i in self._injected]
        for i in ids:
            self.remove(i)
        return len(ids)

    def clear_all(self) -> None:
        self._alerts.clear()
        self._targets.clear()
        self._injected.clear()

    # ------------------------------------------------------------------ #
    # Read path (lazy expiry sweep on every access)
    # ------------------------------------------------------------------ #

    def _sweep(self) -> None:
        now = datetime.now(UTC)
        grace = settings.CAP_ALERT_GRACE_S
        expired = []
        for ident, alert in self._alerts.items():
            exp = _parse_dt(alert.get("expires"))
            if exp is not None and (now - exp).total_seconds() > grace:
                expired.append(ident)
        for ident in expired:
            logger.info("[alertstore] expired: %s", ident)
            self.remove(ident)

    def active(self, *, include_expired: bool = False) -> list[dict[str, Any]]:
        self._sweep()
        return list(self._alerts.values())

    def active_for_location(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Alerts intersecting a point (polygon containment or area-wide)."""
        self._sweep()
        from app.adapters.cap import alerts_for_location

        return alerts_for_location(list(self._alerts.values()), lat, lon)

    def targets_for(self, identifier: str) -> TargetSet | None:
        self._sweep()
        return self._targets.get(identifier)

    def summary(self) -> dict[str, Any]:
        self._sweep()
        by_sev: dict[str, int] = {}
        for a in self._alerts.values():
            sev = a.get("severity") or "Unknown"
            by_sev[sev] = by_sev.get(sev, 0) + 1
        return {
            "count": len(self._alerts),
            "by_severity": by_sev,
            "injected": len(self._injected),
        }

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._events)[-limit:][::-1]


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


alert_store = AlertStore()
