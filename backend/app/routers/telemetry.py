"""Bandit reward ingestion — the live LinUCB feedback loop (TASK-043).

POST /v1/telemetry/interaction accepts widget impressions, clicks, dwell
times, and dismissals. Every explicit event with a known arm folds straight
into the online update

    A_a ← A_a + x x^T      b_a ← b_a + r_t · x

via BackgroundTasks — the client's request is answered 204 immediately; the
bandit update never blocks the response. Events without a usable context
vector (no `x` embedded) still update aggregates (impressions/clicks), so
the Algorithm Inspector's CTR view stays honest.

A bounded in-memory ring buffer (last 500 events) feeds the inspector's
"live weight shifts" view. DPDP: no raw identifiers — device_id_hash only.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Response
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])
logger = logging.getLogger(__name__)

# Bounded event log for the inspector (poped by /v1/debug/bandit/events).
EVENT_LOG: deque[dict[str, Any]] = deque(maxlen=500)

# Swappable sink — tests inject a spy; prod folds into the bandit.
_feedback_sink: Callable[[str, np.ndarray, float], Awaitable[bool]] | None = None


class InteractionEvent(BaseModel):
    widget_id: str = Field(..., min_length=1, max_length=64)
    arm: str | None = Field(None, max_length=64, description="Bandit arm / widget type")
    event: str = Field(..., pattern="^(impression|click|dwell|dismiss)$")
    dwell_ms: int = Field(0, ge=0, le=3_600_000)
    context: dict[str, float] = Field(default_factory=dict)
    x: list[float] | None = Field(
        None, description="Context vector x_t at impression time (18-20 dims)"
    )
    device_id_hash: str | None = Field(None, max_length=64)


def _event_to_reward(event: str, dwell_ms: int) -> float:
    """Reward shaping mirroring services/bandit_ranker.py."""
    if event == "click":
        return settings.BANDIT_REWARD_CLICK
    if event == "dismiss":
        return settings.BANDIT_REWARD_DISMISS
    if event == "dwell":
        return 0.3 if dwell_ms >= settings.BANDIT_REWARD_DWELL_MS else 0.0
    return 0.0


async def _default_sink(arm: str, x: np.ndarray, reward: float) -> bool:
    from app.services.bandit_ranker import BanditRanker

    return BanditRanker.instance().apply_feedback(arm, x, reward)


async def _persist(event: InteractionEvent) -> None:
    arm = event.arm or event.widget_id
    raw_vec = event.x if event.x else [
        v for v in event.context.values() if isinstance(v, (int, float))
    ]
    try:
        x_vec = np.asarray(raw_vec, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        x_vec = np.empty(0)
    reward = _event_to_reward(event.event, event.dwell_ms)

    applied = False
    if reward != 0.0 and x_vec.size:
        sink = _feedback_sink or _default_sink
        try:
            applied = bool(await sink(arm, x_vec, reward))
        except Exception as exc:  # noqa: BLE001 — telemetry must never raise
            logger.warning("bandit update failed for arm=%s: %s", arm, exc)

    EVENT_LOG.append(
        {
            "ts": time.time(),
            "arm": arm,
            "event": event.event,
            "reward": reward,
            "dwell_ms": event.dwell_ms,
            "widget_id": event.widget_id,
            "applied": applied,
        }
    )
    logger.info("telemetry event: %s", json.dumps(event.model_dump(mode="json"), default=str))


@router.post("/interaction", status_code=204)
async def ingest_interaction(
    event: InteractionEvent, background: BackgroundTasks
) -> Response:
    background.add_task(_persist, event)
    return Response(status_code=204)
