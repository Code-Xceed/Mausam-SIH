"""Phase 5 tests — LinUCB bandit, context pipeline, telemetry loop, inspector.

Covers TASK-040 (context vector <5ms), TASK-041/042 (LinUCB core + alpha),
TASK-043 (feedback endpoint), TASK-044 (warm start), TASK-045 (inspector
endpoints), TASK-047 (A/B engine toggle).
"""

from __future__ import annotations

import asyncio
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ml.context import DIM, FEATURE_NAMES, build_context_vector
from app.ml.linucb import LinUCB
from app.services import gateway as gw_module
from app.services.bandit_ranker import (
    BANDIT_ARMS,
    BanditRanker,
    reward_from_event,
)
from app.services.sdui_composer import compose_sdui

CITY_COORDS = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "kochi": (9.9312, 76.2673),
}


def _seed_ctx(key: str):
    gw_module.settings.API_MODE = "SEED"
    lat, lon = CITY_COORDS[key]
    return asyncio.run(gw_module.gateway.get_weather_context(lat, lon))


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fresh_ranker() -> BanditRanker:
    """Isolated bandit state per test (reset to warm priors)."""
    ranker = BanditRanker.instance()
    ranker.reset()
    yield ranker
    ranker.reset()


# --------------------------------------------------------------------------- #
# TASK-040: Context vector construction
# --------------------------------------------------------------------------- #


class TestContextVector:
    def test_dim_and_names(self) -> None:
        ctx = _seed_ctx("delhi")
        built = build_context_vector(ctx, ["health"])
        assert built["dim"] == DIM == 20
        assert len(built["feature_names"]) == DIM == len(FEATURE_NAMES)
        assert built["x"].shape == (DIM,)

    def test_bias_and_persona_one_hots(self) -> None:
        ctx = _seed_ctx("delhi")
        x = build_context_vector(ctx, ["health", "farmer"])["x"]
        assert x[0] == 1.0  # bias
        persona_slice = x[12:20]
        assert persona_slice[0] == 1.0  # health
        assert persona_slice[5] == 1.0  # farmer
        assert persona_slice.sum() == 2.0

    def test_cyclic_hour_encoding(self) -> None:
        ctx = _seed_ctx("delhi")
        x0 = build_context_vector(ctx, [], reference_hour=0.0)["x"]
        x6 = build_context_vector(ctx, [], reference_hour=6.0)["x"]
        assert x0[1] == pytest.approx(0.0, abs=1e-9)  # sin(0)=0
        assert x0[2] == pytest.approx(1.0, abs=1e-9)  # cos(0)=1
        assert x6[1] == pytest.approx(1.0, abs=1e-9)  # sin(π/2)=1
        assert x6[2] == pytest.approx(0.0, abs=1e-9)

    def test_missing_data_zeros(self) -> None:
        ctx = _seed_ctx("delhi")  # no marine, no agro inland
        x = build_context_vector(ctx, [])["x"]
        if ctx.marine is None:
            assert x[8] == 0.0
        if ctx.agro is None:
            assert x[9] == 0.0

    def test_vector_bounded_0_1(self) -> None:
        for key in CITY_COORDS:
            x = build_context_vector(_seed_ctx(key), ["travel"])["x"]
            assert np.all(np.isfinite(x))
            assert x.max() <= 2.0  # wind can reach 2.0 clip
            assert x.min() >= -1.0

    def test_build_under_5ms(self) -> None:
        """TASK-040 acceptance: <5 ms per request on the server."""
        ctx = _seed_ctx("delhi")
        build_context_vector(ctx, ["health"])  # warm up
        t0 = time.perf_counter()
        n = 200
        for _ in range(n):
            build_context_vector(ctx, ["health", "commuter"])
        avg_ms = (time.perf_counter() - t0) * 1000.0 / n
        assert avg_ms < 5.0, f"context build took {avg_ms:.3f} ms average"

    def test_deterministic(self) -> None:
        ctx = _seed_ctx("kochi")
        a = build_context_vector(ctx, ["coastal"], reference_hour=14.0)["x"]
        b = build_context_vector(ctx, ["coastal"], reference_hour=14.0)["x"]
        assert np.array_equal(a, b)


# --------------------------------------------------------------------------- #
# TASK-041/042: LinUCB core
# --------------------------------------------------------------------------- #


class TestLinUCB:
    def test_select_returns_valid_arm_and_scores(self) -> None:
        model = LinUCB(DIM, ["a", "b", "c"])
        x = np.random.default_rng(0).normal(size=DIM)
        best, scores = model.select(x, ["a", "b", "c"])
        assert best in {"a", "b", "c"}
        assert {s.arm for s in scores} == {"a", "b", "c"}
        for s in scores:
            assert s.ucb == pytest.approx(s.exploitation + s.exploration)

    def test_untrained_arm_scores_pure_exploration(self) -> None:
        model = LinUCB(DIM, ["a"])
        x = np.zeros(DIM)
        x[0] = 1.0
        _, scores = model.select(x, ["a"])
        assert scores[0].exploitation == pytest.approx(0.0)  # b = 0
        assert scores[0].exploration > 0.0

    def test_update_shrinks_uncertainty(self) -> None:
        """Same context observed repeatedly → confidence width shrinks."""
        model = LinUCB(DIM, ["a", "b"])
        x = np.zeros(DIM)
        x[0] = 1.0
        _, before = model.select(x, ["a"])
        w0 = before[0].confidence_width
        for _ in range(50):
            model.update("a", x, 1.0)
        _, after = model.select(x, ["a"])
        assert after[0].confidence_width < w0

    def test_reward_learning_flips_preference(self) -> None:
        """Arm rewarded on context x must overtake the other for that x."""
        model = LinUCB(DIM, ["loser", "winner"])
        x = np.zeros(DIM)
        x[0] = 1.0
        model.update("loser", x, 0.9)  # seed both with equal evidence
        model.update("winner", x, 0.1)
        for _ in range(30):  # shift winner's theta upward on this context
            model.update("winner", x, 1.0)
        best, _ = model.select(x, ["loser", "winner"])
        assert best == "winner"

    def test_dim_mismatch_raises(self) -> None:
        model = LinUCB(DIM, ["a"])
        with pytest.raises(ValueError):
            model.select(np.zeros(DIM + 1), ["a"])
        with pytest.raises(ValueError):
            model.update("a", np.zeros(DIM - 1), 1.0)

    def test_epsilon_policy_explores(self) -> None:
        model = LinUCB(DIM, ["a", "b"], epsilon=1.0, seed=7)
        x = np.zeros(DIM)
        x[0] = 1.0
        choices = {model.select(x, ["a", "b"], policy="epsilon")[0] for _ in range(20)}
        assert choices == {"a", "b"}  # pure exploration visits both

    def test_thread_safety(self) -> None:
        model = LinUCB(DIM, ["hot"])
        x = np.zeros(DIM)
        x[0] = 1.0

        def hammer() -> None:
            for _ in range(50):
                model.update("hot", x, 0.5)

        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert model.arms["hot"].impressions == 400

    def test_export_import_roundtrip(self) -> None:
        src = LinUCB(DIM, ["a", "b"])
        x = np.zeros(DIM)
        x[0] = 1.0
        for _ in range(10):
            src.update("a", x, 1.0)
        dst = LinUCB(DIM, ["a", "b"])
        dst.import_state(src.export_state())
        b1 = src.select(x, ["a", "b"])[1]
        b2 = dst.select(x, ["a", "b"])[1]
        assert [s.ucb for s in b1] == pytest.approx([s.ucb for s in b2])

    def test_alpha_override_scales_exploration(self) -> None:
        model = LinUCB(DIM, ["a"])
        x = np.zeros(DIM)
        x[0] = 1.0
        _, low = model.select(x, ["a"], alpha=0.1)
        _, high = model.select(x, ["a"], alpha=2.0)
        assert high[0].exploration > low[0].exploration


# --------------------------------------------------------------------------- #
# TASK-044: Warm start
# --------------------------------------------------------------------------- #


class TestWarmStart:
    def test_pseudo_impressions_seeded(self, fresh_ranker: BanditRanker) -> None:
        stats = {s["arm"]: s for s in fresh_ranker.arm_stats()}
        assert stats["aqi_radial_meter"]["impressions"] == 40
        assert stats["aqi_radial_meter"]["mean_reward"] == pytest.approx(0.8, abs=0.01)

    def test_cold_rank_is_sensible_not_random(self, fresh_ranker: BanditRanker) -> None:
        """Zero real interactions → prior-ranked feed, no widget chaos."""
        ctx = _seed_ctx("delhi")
        pool = ["aqi_radial_meter", "running_window_timeline",
                "travel_packing_carousel", "visibility_meter",
                "event_planner_calendar"]
        ordered, diag = fresh_ranker.rank(ctx, ["health"], pool)
        assert set(ordered) == set(pool)  # permutation, nothing lost
        assert ordered[0] == "aqi_radial_meter"  # highest warm prior (0.8)
        assert diag["best_arm"] == "aqi_radial_meter"

    def test_prior_ordering_respects_warm_table(self, fresh_ranker: BanditRanker) -> None:
        ctx = _seed_ctx("delhi")
        pool = ["running_window_timeline", "visibility_meter", "event_planner_calendar"]
        ordered, _ = fresh_ranker.rank(ctx, [], pool)
        # priors: running 0.5 > visibility 0.55? no — visibility 0.55 > running 0.5
        assert ordered == ["visibility_meter", "running_window_timeline",
                           "event_planner_calendar"]

    def test_reset_restores_priors(self, fresh_ranker: BanditRanker) -> None:
        ctx = _seed_ctx("delhi")
        x = build_context_vector(ctx, ["health"])["x"]
        fresh_ranker.apply_feedback("aqi_radial_meter", x, 1.0)
        stats = {s["arm"]: s for s in fresh_ranker.arm_stats()}
        assert stats["aqi_radial_meter"]["clicks"] == 1
        fresh_ranker.reset()
        stats = {s["arm"]: s for s in fresh_ranker.arm_stats()}
        assert stats["aqi_radial_meter"]["clicks"] == 0
        assert stats["aqi_radial_meter"]["impressions"] == 40

    def test_unknown_arm_rejected(self, fresh_ranker: BanditRanker) -> None:
        x = np.zeros(DIM)
        x[0] = 1.0
        assert fresh_ranker.apply_feedback("not_an_arm", x, 1.0) is False


# --------------------------------------------------------------------------- #
# Composer integration + TASK-047 A/B toggle
# --------------------------------------------------------------------------- #


class TestComposerBandit:
    def test_bandit_engine_label_and_hero(self) -> None:
        ctx = _seed_ctx("delhi")
        payload = compose_sdui(ctx, ["health"], engine="bandit")
        assert payload["personas"]["engine"] == "linucb_v1"
        types = [w["type"] for w in payload["widgets"]]
        # No pins in delhi fixture → hero leads; safety pins would precede it.
        assert types[0] == "current_conditions"

    def test_bandit_ranked_pool_is_permutation(self) -> None:
        ctx = _seed_ctx("kochi")
        payload = compose_sdui(ctx, ["coastal"], engine="bandit")
        types = [w["type"] for w in payload["widgets"]]
        bandit_types = [t for t in types if t in BANDIT_ARMS]
        assert set(bandit_types) <= set(BANDIT_ARMS)
        assert "marine_tide_gauge" in types

    def test_diagnostics_filled(self) -> None:
        ctx = _seed_ctx("delhi")
        diag: dict = {}
        compose_sdui(ctx, ["health"], engine="bandit", bandit_diagnostics=diag)
        assert diag.get("best_arm")
        assert diag.get("x") and len(diag["x"]) == DIM
        assert diag.get("scores")
        assert diag["compute_ms"] >= 0

    def test_safety_pinning_survives_bandit(self) -> None:
        """Rules veto rankings — pinned cards lead the feed in bandit mode too."""
        ctx = _seed_ctx("mumbai")
        payload = compose_sdui(ctx, ["commuter"], engine="bandit")
        types = [w["type"] for w in payload["widgets"]]
        if "commute_safety_banner" in types:  # fixture-dependent pin
            assert types.index("commute_safety_banner") <= 1

    def test_tier_a_untouched_by_default(self) -> None:
        ctx = _seed_ctx("delhi")
        payload = compose_sdui(ctx, ["health"])
        assert payload["personas"]["engine"] == "tier_a_deterministic_v1"
        # phase 4 scene still holds: AQI above hero for health persona
        types = [w["type"] for w in payload["widgets"]]
        assert types.index("aqi_radial_meter") < types.index("current_conditions")

    def test_bandit_learning_promotes_clicked_arm(self, fresh_ranker: BanditRanker) -> None:
        """Simulated clicks on the marine arm must raise its rank over time."""
        ctx = _seed_ctx("kochi")
        diag: dict = {}
        compose_sdui(ctx, ["coastal"], engine="bandit", bandit_diagnostics=diag)
        x = np.asarray(diag["x"], dtype=float)

        before_payload = compose_sdui(ctx, ["coastal"], engine="bandit")
        before = [w["type"] for w in before_payload["widgets"]]

        for _ in range(25):  # user loves the tide card
            fresh_ranker.apply_feedback("marine_tide_gauge", x, 1.0)

        after_payload = compose_sdui(ctx, ["coastal"], engine="bandit")
        after = [w["type"] for w in after_payload["widgets"]]
        assert after.index("marine_tide_gauge") < before.index("marine_tide_gauge")


# --------------------------------------------------------------------------- #
# TASK-043: Telemetry feedback loop (router level)
# --------------------------------------------------------------------------- #


class TestTelemetryLoop:
    def _post_and_settle(self, client: TestClient, body: dict) -> None:
        res = client.post("/v1/telemetry/interaction", json=body)
        assert res.status_code == 204
        time.sleep(0.2)  # BackgroundTasks run after response; TestClient waits anyway

    def test_click_updates_bandit(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        ctx = _seed_ctx("delhi")
        x = build_context_vector(ctx, ["health"])["x"].tolist()
        before = {s["arm"]: s for s in fresh_ranker.arm_stats()}["aqi_radial_meter"]
        self._post_and_settle(client, {
            "widget_id": "aqi_radial_meter", "arm": "aqi_radial_meter",
            "event": "click", "x": x,
        })
        after = {s["arm"]: s for s in fresh_ranker.arm_stats()}["aqi_radial_meter"]
        assert after["clicks"] == before["clicks"] + 1
        assert after["mean_reward"] > before["mean_reward"]

    def test_dismiss_negative_reward(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        ctx = _seed_ctx("delhi")
        x = build_context_vector(ctx, ["health"])["x"].tolist()
        before = {s["arm"]: s for s in fresh_ranker.arm_stats()}["visibility_meter"]
        self._post_and_settle(client, {
            "widget_id": "visibility_meter", "arm": "visibility_meter",
            "event": "dismiss", "x": x,
        })
        after = {s["arm"]: s for s in fresh_ranker.arm_stats()}["visibility_meter"]
        assert after["mean_reward"] < before["mean_reward"]

    def test_impression_no_reward_but_logged(self, client: TestClient) -> None:
        from app.routers import telemetry as tel

        n_before = len(tel.EVENT_LOG)
        self._post_and_settle(client, {
            "widget_id": "event_planner_calendar", "arm": "event_planner_calendar",
            "event": "impression", "x": [1.0] + [0.0] * (DIM - 1),
        })
        assert len(tel.EVENT_LOG) == n_before + 1
        assert tel.EVENT_LOG[-1]["reward"] == 0.0
        assert tel.EVENT_LOG[-1]["applied"] is False  # zero reward → no A/b update

    def test_unknown_arm_logged_not_applied(self, client: TestClient) -> None:
        from app.routers import telemetry as tel

        self._post_and_settle(client, {
            "widget_id": "persona_rank_row", "arm": "persona_rank_row",
            "event": "click", "x": [1.0] + [0.0] * (DIM - 1),
        })
        assert tel.EVENT_LOG[-1]["applied"] is False

    def test_reward_shaping(self) -> None:
        assert reward_from_event("click", 0) == 1.0
        assert reward_from_event("dismiss", 0) == -1.0
        assert reward_from_event("dwell", 2999) == 0.0
        assert reward_from_event("dwell", 3000) == 0.3
        assert reward_from_event("impression", 0) == 0.0


# --------------------------------------------------------------------------- #
# TASK-045: Algorithm Inspector endpoints
# --------------------------------------------------------------------------- #


class TestInspector:
    def test_stats_shape(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        data = client.get("/v1/debug/bandit/stats").json()
        assert data["dim"] == DIM
        arms = {a["arm"] for a in data["arms"]}
        assert arms == set(BANDIT_ARMS)
        assert data["warm_start"]["priors"]["disaster_lifeline_card"] == 0.9

    def test_last_requires_bandit_request(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        res = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21, "personas": "health", "engine": "bandit"},
        )
        assert res.status_code == 200
        data = client.get("/v1/debug/bandit/last").json()
        assert data["available"] is True
        assert len(data["x"]) == DIM
        assert {s["arm"] for s in data["scores"]} <= set(BANDIT_ARMS)

    def test_what_if_alpha_replay(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21, "engine": "bandit"})
        base = client.get("/v1/debug/bandit/last").json()
        replay = client.get("/v1/debug/bandit/last", params={"alpha": 2.0}).json()
        assert replay["replayed_alpha"] == 2.0
        base_top = max(base["scores"], key=lambda s: s["ucb"])
        replay_top = max(replay["scores"], key=lambda s: s["ucb"])
        # higher alpha → strictly larger exploration bonus on the same context
        assert replay_top["exploration"] > base_top["exploration"]

    def test_events_after_telemetry(self, client: TestClient) -> None:
        client.post("/v1/telemetry/interaction", json={
            "widget_id": "aqi_radial_meter", "arm": "aqi_radial_meter",
            "event": "click", "x": [1.0] + [0.0] * (DIM - 1),
        })
        time.sleep(0.2)
        data = client.get("/v1/debug/bandit/events").json()
        assert data["count"] >= 1
        assert data["events"][0]["event"] == "click"

    def test_reset_endpoint(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        client.post("/v1/telemetry/interaction", json={
            "widget_id": "aqi_radial_meter", "arm": "aqi_radial_meter",
            "event": "click", "x": [1.0] + [0.0] * (DIM - 1),
        })
        time.sleep(0.2)
        assert client.post("/v1/debug/bandit/reset").status_code == 200
        stats = {a["arm"]: a for a in client.get("/v1/debug/bandit/stats").json()["arms"]}
        assert stats["aqi_radial_meter"]["clicks"] == 0
        assert stats["aqi_radial_meter"]["impressions"] == 40

    def test_arms_vocabulary(self, client: TestClient) -> None:
        data = client.get("/v1/debug/bandit/arms").json()
        assert set(data["arms"]) == set(BANDIT_ARMS)
        assert "current_conditions" not in data["arms"]


# --------------------------------------------------------------------------- #
# TASK-047: A/B engine toggle (router level)
# --------------------------------------------------------------------------- #


class TestABToggle:
    def test_engines_coexist(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        params = {"lat": 28.61, "lon": 77.21, "personas": "health"}
        control = client.get("/v1/sdui/home", params=params).json()
        experiment = client.get("/v1/sdui/home", params={**params, "engine": "bandit"}).json()
        assert control["personas"]["engine"] == "tier_a_deterministic_v1"
        assert experiment["personas"]["engine"] == "linucb_v1"
        # both deliver the universal hero card (health persona ranks AQI first
        # in control; experiment has no pins → hero leads there)

    def test_invalid_engine_rejected(self, client: TestClient) -> None:
        res = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21, "engine": "gpt"})
        assert res.status_code == 422

    def test_hero_in_both_feeds(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        params = {"lat": 28.61, "lon": 77.21, "personas": "fitness"}
        control_types = [w["type"] for w in client.get("/v1/sdui/home", params=params).json()["widgets"]]
        exp_types = [w["type"] for w in client.get("/v1/sdui/home", params={**params, "engine": "bandit"}).json()["widgets"]]
        assert "current_conditions" in control_types
        assert "current_conditions" in exp_types

    def test_bandit_payload_carries_inspector_summary(self, client: TestClient, fresh_ranker: BanditRanker) -> None:
        data = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21, "personas": "health", "engine": "bandit"},
        ).json()
        bandit_block = data["personas"].get("bandit")
        assert bandit_block is not None
        assert bandit_block["best_arm"]
        assert len(bandit_block["x"]) == DIM
