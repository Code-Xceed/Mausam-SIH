# ml/ — LinUCB Bandit Workspace

Phase 5 lives here: the bandit engine prototype, warm-start prior
generation, and offline replay evaluation (`TASK-046`).

Planned contents:

- `linucb.py` — disjoint LinUCB core (NumPy), mirrored into the backend service
- `priors/` — synthetic warm-start matrices `A_a`, `b_a` per persona arm
- `replay_eval.py` — counterfactual policy evaluation vs. random/greedy baselines
- `notebooks/` — reward-curve experiments for the pitch deck graph
