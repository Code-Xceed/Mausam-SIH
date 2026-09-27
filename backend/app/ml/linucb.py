"""LinUCB disjoint bandit (TASK-041) — online widget ranking core.

Each candidate widget is an arm `a` with its own
  A_a = d x d covariance matrix  (x x^T accumulated per served impression)
  b_a = d-dim reward vector      (r_t * x accumulated per feedback)

Selection follows the standard disjoint LinUCB upper-confidence bound:

    theta_a = A_a^-1 b_a                      (ridge estimate, A initialized I)
    p_a     = theta_a . x  +  alpha * sqrt(x^T A_a^-1 x)

The sqrt term is the exploration bonus: unknown contexts inflate the bound so
unexplored arms get tried (TASK-042, alpha default 0.2). Update is O(d^2) via
Cholesky solve of A_a x = b — exact inverse is never materialized.

Selection policy is pluggable: `ucb` (standard LinUCB), `epsilon` (eps-greedy
fallback), `random` (baseline for the offline evaluator, TASK-046).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from app.core.config import settings

Policy = Literal["ucb", "epsilon", "random"]


@dataclass
class Arm:
    """One widget arm's sufficient statistics."""

    name: str
    A: np.ndarray           # d x d covariance (init: identity -> ridge prior)
    b: np.ndarray           # d-dim reward vector
    impressions: int = 0
    clicks: int = 0
    reward_sum: float = 0.0

    def mean_reward(self) -> float:
        return self.reward_sum / self.impressions if self.impressions else 0.0

    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0


@dataclass
class ArmScore:
    """Inspector-facing per-arm breakdown of the LinUCB score."""

    arm: str
    exploitation: float      # theta_a . x
    exploration: float       # alpha * sqrt(x^T A^-1 x)
    ucb: float               # sum of the two
    theta: list[float]
    confidence_width: float  # sqrt(x^T A^-1 x) without alpha
    impressions: int
    clicks: int


@dataclass
class _State:
    arms: dict[str, Arm] = field(default_factory=dict)


class LinUCB:
    """Thread-safe disjoint LinUCB over a fixed arm vocabulary."""

    def __init__(
        self,
        dim: int,
        arms: list[str],
        alpha: float | None = None,
        epsilon: float = 0.05,
        seed: int | None = None,
    ) -> None:
        self.dim = dim
        self.arms: dict[str, Arm] = {}
        self.alpha = settings.BANDIT_ALPHA if alpha is None else alpha
        self.epsilon = epsilon
        self.lock = threading.Lock()
        self._rng = np.random.default_rng(seed)
        for name in arms:
            self.reset_arm(name)

    # ------------------------------------------------------------------ #
    # Selection
    # ------------------------------------------------------------------ #

    def select(
        self,
        x: np.ndarray,
        candidates: list[str],
        policy: Policy = "ucb",
        alpha: float | None = None,
    ) -> tuple[str, list[ArmScore]]:
        """Rank candidates by LinUCB UCB and return (best_arm, all_scores).

        `alpha` override exists for the inspector's what-if analysis.
        """
        if not candidates:
            raise ValueError("no candidate arms to score")
        x = np.asarray(x, dtype=float).reshape(-1)
        if x.shape[0] != self.dim:
            raise ValueError(f"context dim {x.shape[0]} != model dim {self.dim}")

        eff_alpha = self.alpha if alpha is None else alpha

        with self.lock:
            if policy == "random":
                scores = [self._score(x, a, eff_alpha, exploit=0.0) for a in candidates]
                return self._rng.choice(candidates), scores
            if policy == "epsilon" and self._rng.random() < self.epsilon:
                scores = [self._score(x, a, eff_alpha, exploit=0.0) for a in candidates]
                return self._rng.choice(candidates), scores

            scores = [self._score(x, a, eff_alpha) for a in candidates]
            best = max(scores, key=lambda s: s.ucb)
            return best.arm, scores

    def _score(self, x: np.ndarray, arm_name: str, alpha: float, *, exploit: float | None = None) -> ArmScore:
        arm = self.arms.get(arm_name)
        if arm is None:  # unseen arm (e.g. warm-start skipped it): identity stats
            arm = Arm(arm_name, np.eye(self.dim), np.zeros(self.dim))

        if exploit is not None:
            return ArmScore(
                arm=arm_name, exploitation=exploit, exploration=0.0, ucb=exploit,
                theta=[0.0] * self.dim, confidence_width=0.0,
                impressions=arm.impressions, clicks=arm.clicks,
            )

        A_reg = arm.A + settings.BANDIT_RIDGE * np.eye(self.dim)
        A_inv_x = np.linalg.solve(A_reg, x)
        theta = np.linalg.solve(A_reg, arm.b)
        exploitation = float(theta @ x)
        width = float(math.sqrt(max(0.0, float(x @ A_inv_x))))
        return ArmScore(
            arm=arm_name,
            exploitation=exploitation,
            exploration=alpha * width,
            ucb=exploitation + alpha * width,
            theta=theta.tolist(),
            confidence_width=width,
            impressions=arm.impressions,
            clicks=arm.clicks,
        )

    # ------------------------------------------------------------------ #
    # Online update (TASK-043 feedback loop)
    # ------------------------------------------------------------------ #

    def update(self, arm_name: str, x: np.ndarray, reward: float) -> None:
        """A_a += x x^T ; b_a += r x — the exact LinUCB online step."""
        x = np.asarray(x, dtype=float).reshape(-1)
        if x.shape[0] != self.dim:
            raise ValueError(f"context dim {x.shape[0]} != model dim {self.dim}")
        with self.lock:
            arm = self.arms.setdefault(
                arm_name, Arm(arm_name, np.eye(self.dim), np.zeros(self.dim))
            )
            arm.A += np.outer(x, x)
            arm.b += reward * x
            arm.impressions += 1
            arm.clicks += 1 if reward >= 0.5 else 0
            arm.reward_sum += reward

    def record_impression(self, arm_name: str, x: np.ndarray) -> None:
        """Serve-only bookkeeping: covariance grows, reward does not."""
        x = np.asarray(x, dtype=float).reshape(-1)
        with self.lock:
            arm = self.arms.setdefault(
                arm_name, Arm(arm_name, np.eye(self.dim), np.zeros(self.dim))
            )
            arm.A += np.outer(x, x)
            arm.impressions += 1

    # ------------------------------------------------------------------ #
    # Persistence (in-memory snapshot for tests / future Redis store)
    # ------------------------------------------------------------------ #

    def export_state(self) -> dict:
        with self.lock:
            return {
                "dim": self.dim,
                "alpha": self.alpha,
                "arms": {
                    name: {
                        "A": arm.A.tolist(),
                        "b": arm.b.tolist(),
                        "impressions": arm.impressions,
                        "clicks": arm.clicks,
                        "reward_sum": arm.reward_sum,
                    }
                    for name, arm in self.arms.items()
                },
            }

    def import_state(self, state: dict) -> None:
        with self.lock:
            self.arms = {
                name: Arm(
                    name,
                    np.asarray(a["A"], dtype=float),
                    np.asarray(a["b"], dtype=float),
                    a.get("impressions", 0),
                    a.get("clicks", 0),
                    a.get("reward_sum", 0.0),
                )
                for name, a in state.get("arms", {}).items()
            }

    def reset_arm(self, name: str) -> None:
        with self.lock:
            self.arms[name] = Arm(name, np.eye(self.dim), np.zeros(self.dim))

    def reset_all(self) -> None:
        with self.lock:
            self.arms = {name: Arm(name, np.eye(self.dim), np.zeros(self.dim)) for name in self.arms}
