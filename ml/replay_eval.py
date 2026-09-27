"""Counterfactual policy evaluation for the LinUCB ranker (TASK-046).

Answers the jury question "how do you KNOW the bandit beats the old rules?"
by replaying T rounds of synthetic logged traffic — each round draws a random
context x_t and every policy picks a widget arm; the environment rewards the
pick via a fixed hidden preference model (unknown to all policies):

    r_t ~ Bernoulli( sigmoid( theta*_a . x_t ) )

Compared head-to-head:
    linucb   — the production UCB policy (exploration alpha=0.2)
    epsilon  — eps-greedy on the same ridge estimates (5% exploration)
    random   — the "legacy app shuffles cards" baseline

Outputs (committed for the pitch deck):
    ml/replay_results.json  — per-policy cumulative reward + CTR summary
    ml/replay_results.png   — comparative learning curve (matplotlib when
                              available; ASCII chart is always printed)
    stdout table            — final numbers for slides

Usage:
    cd backend && .venv/Scripts/python ../ml/replay_eval.py [--rounds 4000]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

# Make the backend package importable when run from ml/ or repo root.
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "backend"))

from app.ml.linucb import LinUCB  # noqa: E402
from app.services.bandit_ranker import BANDIT_ARMS  # noqa: E402

DIM = 20  # matches app.ml.context.DIM


def _hidden_preferences(rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Ground-truth arm quality — unknown to every policy.

    Constructed so arms differ meaningfully (spread of base quality 0.15..0.65
    CTR) and respond to the context (preferences along random directions),
    which is exactly what makes exploration worth doing.
    """
    prefs: dict[str, np.ndarray] = {}
    base = rng.uniform(0.15, 0.65, size=len(BANDIT_ARMS))
    for i, arm in enumerate(BANDIT_ARMS):
        direction = rng.normal(0, 0.5, size=DIM)
        direction[0] = 0.0  # bias coordinate handled by base quality
        prefs[arm] = direction
        prefs[arm][0] = math.log(base[i] / (1 - base[i]))  # logit offset
    return prefs


def _reward(arm: str, x: np.ndarray, prefs: dict[str, np.ndarray]) -> float:
    p = 1.0 / (1.0 + math.exp(-float(prefs[arm] @ x)))
    return 1.0 if rng.random() < p else 0.0


def _run_policy(
    policy: str, rounds: int, prefs: dict[str, np.ndarray], rng: np.random.Generator
) -> list[float]:
    """Replay `rounds` under one policy; returns cumulative reward trace."""
    model = LinUCB(dim=DIM, arms=list(BANDIT_ARMS), seed=int(rng.integers(1 << 30)))
    cumulative: list[float] = []
    total = 0.0
    for _ in range(rounds):
        x = rng.normal(0, 1, size=DIM)
        x[0] = 1.0  # bias
        candidates = list(BANDIT_ARMS)
        arm, _scores = model.select(x, candidates, policy=policy)
        r = _reward(arm, x, prefs)
        if policy != "random" or True:  # every policy learns nothing but updates honestly
            model.update(arm, x, r)
        total += r
        cumulative.append(total)
    return cumulative


def _ascii_chart(traces: dict[str, list[float]], width: int = 60, height: int = 10) -> str:
    """Terminal-friendly learning curve for CI logs (matplotlib optional)."""
    lines: list[str] = []
    max_y = max(t[-1] for t in traces.values()) or 1.0
    rows = []
    for level in range(height, 0, -1):
        row = ""
        threshold = max_y * level / height
        for col in range(width):
            frac = col / (width - 1)
            idx = int(frac * (len(next(iter(traces.values()))) - 1))
            marks = [name for name, t in traces.items() if t[idx] >= threshold]
            row += marks[0][0].upper() if len(marks) == 1 else ("#" if marks else " ")
        rows.append(f"{threshold:8.0f} |{row}")
    lines.extend(rows)
    lines.append("         +" + "-" * width)
    legend = ", ".join(f"{name[0].upper()}={name}" for name in traces)
    lines.append(f"          {legend}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=26076)  # SIH problem ID :)
    args = ap.parse_args()

    global rng
    rng = np.random.default_rng(args.seed)

    prefs = _hidden_preferences(rng)
    traces = {
        "linucb": _run_policy("ucb", args.rounds, prefs, rng),
        "epsilon": _run_policy("epsilon", args.rounds, prefs, rng),
        "random": _run_policy("random", args.rounds, prefs, rng),
    }

    summary = {
        "rounds": args.rounds,
        "seed": args.seed,
        "dim": DIM,
        "arms": len(BANDIT_ARMS),
        "results": {
            name: {
                "cumulative_reward": trace[-1],
                "reward_per_round": round(trace[-1] / args.rounds, 4),
                "lift_vs_random_pct": round(
                    (trace[-1] / max(traces["random"][-1], 1e-9) - 1) * 100, 1
                ),
            }
            for name, trace in traces.items()
        },
    }

    out_json = Path(__file__).resolve().parent / "replay_results.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # PNG chart for the pitch deck when matplotlib is available.
    png_written = False
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4.2))
        for name, trace in traces.items():
            ax.plot(trace, label=name, linewidth=1.8)
        ax.set_xlabel("Replay round")
        ax.set_ylabel("Cumulative reward")
        ax.set_title("LinUCB vs baselines — offline replay (TASK-046)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(Path(__file__).resolve().parent / "replay_results.png", dpi=140)
        png_written = True
    except ImportError:
        pass

    print(f"replay: {args.rounds} rounds, seed={args.seed}, dim={DIM}, arms={len(BANDIT_ARMS)}")
    for name, res in summary["results"].items():
        print(
            f"  {name:8s} cumulative={res['cumulative_reward']:7.0f}  "
            f"per-round={res['reward_per_round']:.4f}  vs random: {res['lift_vs_random_pct']:+.1f}%"
        )
    print(_ascii_chart(traces))
    print(f"\nwrote {out_json.name}" + (" + replay_results.png" if png_written else " (matplotlib not installed — ASCII chart only)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
