"""High-priority FCM push dispatcher (TASK-050).

Red/Severe CAP alerts fan out to per-geohash FCM topics resolved by the
geofence engine. Message shape: Android priority HIGH, TTL 0 (fire-and-
forget — a 20-minute-old cyclone warning is spam, not safety), notification
title/body from the CAP headline/description.

Auth: FCM HTTP v1 needs an OAuth2 access token minted from the Firebase
service account (GOOGLE_APPLICATION_CREDENTIALS). The real mint flow needs
the `google-auth` package and live Google servers; for the demo the
dispatcher runs in DRY-RUN by default (logs + records the exact targets and
payload it WOULD send). Configuring FCM_PROJECT_ID + valid creds switches
it to live sends.

Sub-2.5 s dispatch budget: single topic send with short timeouts; per-topic
failures are logged, never raised.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.services.geofence import TargetSet, alert_target_set

logger = logging.getLogger(__name__)

FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FCM_TOKEN_URL = "https://oauth2.googleapis.com/token"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# Demo-mode switches (admin API can flip these at runtime).
DRY_RUN = True  # default: log-only until FCM credentials are configured


def build_push_payload(alert: dict[str, Any], topic: str, *, dry_run: bool | None = None) -> dict[str, Any]:
    """FCM v1 message body for one topic.

    priority=high + ttl="0s" per TASK-050 acceptance (lockscreen, immediate).
    """
    dry = DRY_RUN if dry_run is None else dry_run
    severity = (alert.get("severity") or "Unknown").upper()
    event = alert.get("event") or "Weather Alert"
    area = alert.get("area_desc") or "your area"
    body = (alert.get("description") or alert.get("headline") or event)[:220]

    return {
        "message": {
            "topic": topic,
            "notification": {
                # Jury-visible: red alert wording mirrors SACHET push style.
                "title": f"{'[DRY-RUN] ' if dry else ''}{severity}: {event}",
                "body": body or f"Official warning for {area}",
            },
            "android": {
                "priority": "HIGH",
                "ttl": "0s",
                "notification": {
                    "channel_id": "mausam_disaster_alerts",
                    "click_action": "MAUSAM_ALERT_TAP",
                },
            },
        }
    }


async def _live_send(project_id: str, message: dict[str, Any]) -> None:
    """Send one message via FCM HTTP v1 with a service-account token.

    Live signing requires `google-auth` (JWT RS256 + OAuth2 exchange). The
    demo runs dry-run by default, so this import is deferred and only needed
    when the operator explicitly enables live sends.
    """
    token = await _access_token()
    url = FCM_SEND_URL.format(project=project_id)
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; UTF-8",
            },
            content=json.dumps(message),
        )
        resp.raise_for_status()


async def _access_token() -> str:
    """Mint an OAuth2 token from the Firebase service account (live mode)."""
    import os

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set — FCM live send unavailable")
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as AuthRequest
    except ImportError as exc:  # pragma: no cover — optional live-path dep
        raise RuntimeError(
            "google-auth not installed — pip install google-auth for live FCM sends"
        ) from exc

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=[FCM_SCOPE]
    )
    creds.refresh(AuthRequest())
    return creds.token


async def dispatch_alert(
    alert: dict[str, Any],
    *,
    targets: TargetSet | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Resolve targets for `alert` and push to each topic.

    Returns bookkeeping: sent count, target count, mode, elapsed ms. Never
    raises for per-topic send failures.
    """
    t0 = time.perf_counter()
    if targets is None:
        targets = alert_target_set(alert)

    topics = targets.topic_names(prefix="mausam_alert")
    payload_topics: list[dict[str, Any]] = []

    project_id = settings.FCM_PROJECT_ID
    live_possible = bool(project_id) and not (DRY_RUN if dry_run is None else dry_run)

    async def send_topic(topic: str) -> bool:
        payload = build_push_payload(alert, topic, dry_run=dry_run)
        payload_topics.append({"topic": topic, "payload": payload})
        if not live_possible:
            logger.debug("[fcm:dr] would push to %s", topic)  # per-topic is spammy
            return True
        try:
            await _live_send(project_id, payload)
            return True
        except Exception as exc:  # noqa: BLE001 — one dead topic never blocks the rest
            logger.warning("[fcm] send failed for %s: %s", topic, exc)
            return False

    # Parallel sends; a red alert with 50 topics must not serialize.
    results = await asyncio.gather(*(send_topic(t) for t in topics))

    elapsed = round((time.perf_counter() - t0) * 1000, 2)
    bookkeeping = {
        "identifier": alert.get("identifier"),
        "event": alert.get("event"),
        "severity": alert.get("severity"),
        "targets": targets.size,
        "area_wide": targets.area_wide,
        "coarse": targets.coarse,
        "topics": len(topics),
        "sent": int(sum(1 for r in results if r)),
        "mode": "live" if live_possible else "dry-run",
        "elapsed_ms": elapsed,
        "under_budget": elapsed < 2500,
    }
    logger.info(
        "[fcm] dispatched %s: %d topics in %.1fms (%s)",
        bookkeeping["identifier"], len(topics), elapsed, bookkeeping["mode"],
    )
    # Inspector event log — the demo shows this trail.
    from app.services.alert_store import alert_store

    alert_store._events.append({"ts": time.time(), "kind": "dispatch", **bookkeeping})
    return bookkeeping
