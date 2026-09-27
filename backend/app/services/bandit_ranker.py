"""Bandit ranking service — Phase 5 glue between LinUCB and the composer.

Arms: every composable widget type that carries persona meaning. Card
ordering within one request comes from `rank()`; per-request context is built
by `app.ml.context.build_context_vector`.

Warm-start (TASK-044): every arm's A starts at ridge*I and b at a synthetic
prior θ_warm scaled by N pseudo-impressions. The prior encodes "typical
Indian user" intuition — a fresh install never sees random widget chaos:
marine card speaks to coastal tags, AQI card to health, agro to farmer, etc.

A/B toggle (TASK-047): `engine` param routes sessions between the Tier A
heuristic composer (control) and the LinUCB bandit (experiment) so the jury
can see both side by side.

Impressions are recorded at serve time; explicit feedback (click/dwell/
dismiss) arrives asynchronously via /v1/telemetry/interaction and is folded
into A/b through the same thread-safe update path.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from app.core.config import settings
from app.ml.context import DIM, build_context_vector
from app.ml.linucb import LinUCB
from app.models.weather import WeatherContext

logger = logging.getLogger(__name__)

# Widget arms — the bandit only orders cards that carry persona meaning.
# current_conditions stays a universal baseline and persona_rank_row is
# diagnostics; both bypass the bandit entirely (mirrors the Tier A engine).
BANDIT_ARMS: list[str] = [
    "aqi_radial_meter",
    "running_window_timeline",
    "marine_tide_gauge",
    "travel_packing_carousel",
    "commute_safety_banner",
    "meghdoot_agro_card",
    "visibility_meter",
    "event_planner_calendar",
    "disaster_lifeline_card",
]

WARM_PRIOR: dict[str, float] = {
    # θ_warm per arm — "typical Indian user" affinity at minute zero.
    "aqi_radial_meter": 0.8,          # health crisis salience
    "running_window_timeline": 0.5,
    "marine_tide_gauge": 0.4,         # only ~9% of population is coastal
    "travel_packing_carousel": 0.55,
    "commute_safety_banner": 0.7,     # urban commute relevance
    "meghdoot_agro_card": 0.5,        # ~45% workforce is agricultural
    "visibility_meter": 0.55,
    "event_planner_calendar": 0.45,
    "disaster_lifeline_card": 0.9,    # safety-first prior (pinning still vetoes)
}

WARM_PSEUDO_IMPRESSIONS = 40  # prior strength — outweighed by ~100 real events

# Reward shaping (settings override): click 1.0, dismiss -1.0, dwell 0.3.
REWARD_CLICK = settings.BANDIT_REWARD_CLICK
REWARD_DISMISS = settings.BANDIT_REWARD_DISMISS
REWARD_DWELL = 0.3
DWELL_THRESHOLD_MS = settings.BANDIT_REWARD_DWELL_MS


def reward_from_event(event: str, dwell_ms: int) -> float:
    """Map a telemetry event to a bandit reward scalar (TASK-043 contract)."""
    if event == "click":
        return REWARD_CLICK
    if event == "dismiss":
        return REWARD_DISMISS
    if event == "dwell":
        return REWARD_DWELL if dwell_ms >= DWELL_THRESHOLD_MS else 0.0
    return 0.0  # bare impressions add no reward


class BanditRanker:
    """Process-wide singleton facade over LinUCB with warm-start priors."""

    _instance: BanditRanker | None = None

    @classmethod
    def instance(cls) -> BanditRanker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.model = LinUCB(DIM, BANDIT_ARMS, alpha=settings.BANDIT_ALPHA)
        self._apply_warm_start()
        self.last_error: str | None = None

    # ------------------------------------------------------------------ #
    # Warm start (TASK-044)
    # ------------------------------------------------------------------ #

    def _apply_warm_start(self) -> None:
        """Seed each arm's b with θ_warm * N pseudo-impressions.

        With A ≈ N*I the ridge solution θ̂ = (A)^-1 b ≈ θ_warm, so cold users
        immediately receive sensible persona-aware rankings instead of
        untrained exploration noise.
        """
        n = WARM_PSEUDO_IMPRESSIONS
        for arm_name, theta_warm in WARM_PRIOR.items():
            if arm_name not in self.model.arms:
                continue
            arm = self.model.arms[arm_name]
            # Identity-dominant covariance: pseudo-observations spread over
            # feature space — keeps A well conditioned without inventing
            # fake structure.
            arm.A = np.eye(DIM) * float(n)
            x_warm = np.zeros(DIM)
            x_warm[0] = 1.0  # bias feature
            # b = Σ r_t x_t ≈ θ_warm * N * x_bias (scaled identity prior)
            arm.b = np.array(
                [theta_warm * n if i == 0 else 0.0 for i in range(DIM)],
                dtype=float,
            )
            arm.impressions = n
            arm.reward_sum = theta_warm * n

    # ------------------------------------------------------------------ #
    # Ranking (composer entrypoint)
    # ------------------------------------------------------------------ #

    def rank(
        self,
        ctx: WeatherContext,
        active_personas: list[str],
        candidates: list[str],
        *,
        alpha: float | None = None,
        reference_hour: float | None = None,
    ) -> tuple[list[str], dict]:
        """Order `candidates` for this context. Returns (ordered, diagnostics).

        Missing-data arms (no marine ctx etc.) are filtered by the composer
        before calling — this function assumes feasible arms only.
        """
        t0 = time.perf_counter()
        built = build_context_vector(ctx, active_personas, reference_hour=reference_hour)
        x: np.ndarray = built["x"]

        try:
            best, scores = self.model.select(
                x, candidates, policy="ucb", alpha=alpha
            )
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 — ranking must never 500 a page
            logger.warning("LinUCB select failed (%s) — Tier A order fallback", exc)
            self.last_error = str(exc)
            return list(candidates), {"error": str(exc), "scores": []}

        ordered = [s.arm for s in sorted(scores, key=lambda s: s.ucb, reverse=True)]
        diagnostics = {
            "x": x.tolist(),
            "feature_names": built["feature_names"],
            "dim": built["dim"],
            "alpha": self.model.alpha if alpha is None else alpha,
            "policy": "ucb",
            "best_arm": best,
            "scores": [s.__dict__ for s in scores],
            "compute_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
        # Context dim guard — never emit a broken vector downstream.
        assert len(x) == DIM, "context vector dim mismatch"
        return ordered, diagnostics

    def record_impression(self, arm: str, x: np.ndarray) -> None:
        if arm in BANDIT_ARMS:
            self.model.record_impression(arm, x)

    def apply_feedback(self, arm: str, x: np.ndarray, reward: float) -> bool:
        """Fold one telemetry event into A/b. Returns False for unknown arms."""
        if arm not in BANDIT_ARMS:
            return False
        self.model.update(arm, x, reward)
        return True

    # ------------------------------------------------------------------ #
    # Inspector support (TASK-045 backend half)
    # ------------------------------------------------------------------ #

    def arm_stats(self) -> list[dict]:
        stats = []
        for name in BANDIT_ARMS:
            arm = self.model.arms.get(name)
            if arm is None:
                continue
            stats.append(
                {
                    "arm": name,
                    "impressions": arm.impressions,
                    "clicks": arm.clicks,
                    "ctr": round(arm.ctr(), 4),
                    "mean_reward": round(arm.mean_reward(), 4),
                }
            )
        return stats

    def reset(self) -> None:
        self.model.reset_all()
        self._apply_warm_start()

    def export_state(self) -> dict:
        return self.model.export_state()

    def import_state(self, state: dict) -> None:
        self.model.import_state(state)
