"""Algorithm Inspector backend (TASK-045) — live bandit debug endpoints.

Read-only introspection of the running LinUCB policy so the jury can watch
the math move: per-arm UCB breakdowns, what-if alpha replay, recent
telemetry events, and stats reset. Debug surface only — not for the
production client; mounted under /v1/debug without auth for the demo.
"""

from __future__ import annotations

import time

import numpy as np
from fastapi import APIRouter, Query

from app.core.config import settings
from app.ml.context import FEATURE_NAMES
from app.services.bandit_ranker import BANDIT_ARMS, BanditRanker, WARM_PRIOR

router = APIRouter(prefix="/v1/debug/bandit", tags=["debug"])


@router.get("/stats")
async def bandit_stats() -> dict:
    """Aggregate per-arm stats — impressions, clicks, CTR, mean reward."""
    ranker = BanditRanker.instance()
    return {
        "alpha": ranker.model.alpha,
        "dim": ranker.model.dim,
        "arms": ranker.arm_stats(),
        "warm_start": {
            "pseudo_impressions": 40,
            "priors": WARM_PRIOR,
        },
    }


@router.get("/last")
async def bandit_last(
    alpha: float | None = Query(
        None, gt=0, description="What-if exploration rate for the replay"
    ),
) -> dict:
    """Full diagnostics of the most recent bandit-ranked request.

    The `alpha` query replays the LAST context through the current model at
    a different exploration rate — live what-if analysis inside the
    inspector (watch exploration bonuses breathe as alpha moves).
    """
    from app.routers import sdui as sdui_router

    diag = getattr(sdui_router, "_last_bandit_diagnostics", None)
    if not diag:
        return {"available": False, "hint": "GET /v1/sdui/home?engine=bandit first"}

    x = np.asarray(diag.get("x") or [], dtype=float)
    candidates = [s["arm"] for s in diag.get("scores") or []]
    out: dict = {
        "available": True,
        "captured_at": diag.get("captured_at"),
        "compute_ms": diag.get("compute_ms"),
        "dim": diag.get("dim"),
        "alpha": diag.get("alpha"),
        "feature_names": FEATURE_NAMES,
        "x": (x.tolist() if x.size else diag.get("x", [])),
    }

    if x.size and candidates:
        _, scores = ranker_select(x, candidates, alpha)
        out["scores"] = scores
        out["replayed_alpha"] = alpha

    return out


def ranker_select(x: np.ndarray, candidates: list[str], alpha: float | None):
    """Replay selection without recording impressions."""
    ranker = BanditRanker.instance()
    return ranker.model.select(x, candidates, policy="ucb", alpha=alpha)


@router.get("/events")
async def bandit_events(limit: int = Query(50, ge=1, le=500)) -> dict:
    """Recent telemetry events (bounded ring buffer, newest first)."""
    from app.routers import telemetry as telemetry_router

    events = list(telemetry_router.EVENT_LOG)[-limit:][::-1]
    return {"count": len(events), "events": events}


@router.post("/reset")
async def bandit_reset() -> dict:
    """Reset all arm statistics back to warm-start priors (demo hook)."""
    BanditRanker.instance().reset()
    return {"reset": True, "at": time.time()}


@router.get("/arms")
async def bandit_arms() -> dict:
    """Arm vocabulary + which widget types are bandit-eligible."""
    return {
        "arms": BANDIT_ARMS,
        "warm_priors": WARM_PRIOR,
        "alpha": settings.BANDIT_ALPHA,
    }
