"""Phase 6 tests — CAP poller, geofence clipping, FCM dispatcher, injection tool.

Covers TASK-048 (60s poller + diff ingest), TASK-049 (polygon → grid cells),
TASK-050 (dry-run FCM payloads + dispatch bookkeeping), TASK-054 (demo Red-
Alert injection via /v1/admin), plus the multi-info CAP parser regression
(one <alert>, N <info> blocks ⇒ N unique store identifiers) and the gateway
unification (SDUI disaster card reads the alert store, so injected alerts
surface on affected cities' homes).
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.adapters.cap import parse_cap_xml
from app.main import app
from app.models.weather import snap_geohash5
from app.services import gateway as gw_module
from app.services.alert_store import AlertStore, alert_store
from app.services.cap_poller import CapPoller, poller
from app.services.dispatcher import build_push_payload, dispatch_alert
from app.services.geofence import (
    FINE_STEP,
    TargetSet,
    alert_target_set,
    circle_polygon,
    geohashes_in_polygon,
    grid_cells_in_bbox,
    polygon_bbox,
)
from app.services.sdui_composer import compose_sdui

CITY_COORDS = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "kochi": (9.9312, 76.2673),
    "shimla": (31.1048, 77.1734),
}

MUMBAI = CITY_COORDS["mumbai"]
DELHI = CITY_COORDS["delhi"]
KOCHI = CITY_COORDS["kochi"]

# Fixture polygon from mock_fixtures/cap_alerts.xml (Konkan cyclone belt).
KONKAN_POLY = [
    (20.4, 72.6),
    (19.0, 72.6),
    (18.2, 73.2),
    (18.6, 73.6),
    (19.8, 73.0),
    (20.4, 72.6),
]


def _seed_ctx(key: str):
    gw_module.settings.API_MODE = "SEED"
    lat, lon = CITY_COORDS[key]
    return asyncio.run(gw_module.gateway.get_weather_context(lat, lon))


def _mk_alert(
    ident: str = "test-alert-1",
    severity: str = "Severe",
    polygons: list | None = None,
    expires_in_s: int = 3600,
) -> dict:
    from datetime import UTC, datetime, timedelta

    return {
        "identifier": ident,
        "sender": "test@mausam",
        "sent": datetime.now(UTC).isoformat(),
        "event": "Cyclone Warning",
        "severity": severity,
        "headline": f"{severity} cyclone (test)",
        "description": "test alert",
        "expires": (datetime.now(UTC) + timedelta(seconds=expires_in_s)).isoformat(),
        "area_desc": "test area",
        "polygons": polygons if polygons is not None else [KONKAN_POLY],
        "source": "NDMA_CAP",
    }


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        # conftest.py quiets the poller feed session-wide and empties the
        # store around every test — lifespan wiring still runs for real.
        yield c


@pytest.fixture()
def clean_store():
    """Explicit handle for tests that assert on store state (conftest empties)."""
    alert_store.clear_all()
    yield alert_store
    alert_store.clear_all()


# --------------------------------------------------------------------------- #
# TASK-049: Geofence — polygon → grid cells
# --------------------------------------------------------------------------- #


class TestGeofenceBasics:
    def test_bbox(self) -> None:
        bbox = polygon_bbox(KONKAN_POLY)
        assert bbox == (18.2, 72.6, 20.4, 73.6)

    def test_bbox_degenerate(self) -> None:
        assert polygon_bbox([(1.0, 1.0)]) is None
        assert polygon_bbox([]) is None

    def test_grid_cells_multiplicative_no_drift(self) -> None:
        # A large bbox via the fine grid must produce an exact i*j count —
        # float accumulation drift would drop boundary rows.
        bbox = (10.0, 70.0, 15.0, 75.0)
        cells = grid_cells_in_bbox(bbox, FINE_STEP)
        n = int(round(5.0 / FINE_STEP)) + 1
        assert len(cells) == n * n
        # All origins are step-multiples and inside the bbox.
        for lat, lon in cells:
            assert abs(lat / FINE_STEP - round(lat / FINE_STEP)) < 1e-6
            assert 10.0 <= lat <= 15.0 and 70.0 <= lon <= 75.0

    def test_grid_cells_rounding(self) -> None:
        cells = grid_cells_in_bbox((19.0, 72.6, 19.1, 72.7), 0.05)
        assert (19.0, 72.6) in cells
        assert (19.1, 72.7) in cells

    def test_mumbai_circle_catches_mumbai(self) -> None:
        cells, coarse = geohashes_in_polygon(circle_polygon(*MUMBAI))
        assert cells and not coarse
        assert snap_geohash5(*MUMBAI) in cells

    def test_mumbai_circle_excludes_delhi(self) -> None:
        cells, _ = geohashes_in_polygon(circle_polygon(*MUMBAI))
        assert snap_geohash5(*DELHI) not in cells

    def test_konkan_fixture_polygon_contains_mumbai(self) -> None:
        cells, coarse = geohashes_in_polygon(KONKAN_POLY)
        assert not coarse
        assert snap_geohash5(*MUMBAI) in cells
        assert snap_geohash5(*DELHI) not in cells
        assert snap_geohash5(*KOCHI) not in cells  # rainfall polygon's job

    def test_circle_polygon_closes(self) -> None:
        poly = circle_polygon(*MUMBAI, radius_deg=0.35, points=16)
        assert poly[0] == poly[-1]
        assert len(poly) == 17
        # All vertices within radius of the center (lon offset cos-scaled).
        for lat, lon in poly[:-1]:
            assert abs(lat - MUMBAI[0]) <= 0.36
            assert abs(lon - MUMBAI[1]) <= 0.40

    def test_target_set_area_wide(self) -> None:
        ts = alert_target_set({"polygons": []})
        assert ts.area_wide is True
        assert ts.topic_names() == ["alert_*"]

    def test_topic_names_sorted_prefixed(self) -> None:
        ts = TargetSet(geohashes={snap_geohash5(*MUMBAI), snap_geohash5(*DELHI)})
        topics = ts.topic_names(prefix="mausam_alert")
        assert topics == sorted(topics)
        assert all(t.startswith("mausam_alert_") for t in topics)
        assert ts.size == 2


class TestGeofenceCoarseFallback:
    def test_big_polygon_expands_to_fine_coverage(self) -> None:
        # 1.7° square ⇒ 35×35 = 1225 fine candidates (> MAX_FINE_CELLS)
        # → coarse grid: 8×8 candidate centers, 7×6 strictly inside the box
        # (the 20.625 lat row and 74.125 lon col fall on/outside the edge).
        # geohashes_in_polygon returns raw center addresses; alert_target_set
        # does the ×25 expansion — asserted in test_expansion_* and via
        # alert_target_set below.
        square = [(20.7, 72.4), (20.7, 74.1), (19.0, 74.1), (19.0, 72.4), (20.7, 72.4)]
        cells, coarse = geohashes_in_polygon(square)
        assert coarse is True
        assert len(cells) == 42  # 7 lat rows × 6 lon cols of coarse centers
        ts = alert_target_set({"polygons": [square]})
        assert ts.coarse is True
        assert ts.area_wide is False
        assert len(ts.geohashes) == 42 * 25
        assert snap_geohash5(*MUMBAI) in ts.geohashes  # "19.05_72.85"
        # Every address sits on a true 0.05 multiple — including the 19.15 row
        # that float-addition expansion would drop (snap(19.15) → "19.10").
        for addr in ts.geohashes:
            la, lo = addr.split("_")
            assert abs(float(la) / FINE_STEP - round(float(la) / FINE_STEP)) < 1e-6
            assert abs(float(lo) / FINE_STEP - round(float(lo) / FINE_STEP)) < 1e-6
        assert "19.15_72.75" in ts.geohashes

    def test_expansion_covers_neighbouring_fine_cells(self) -> None:
        # A matched coarse cell must expand to all 25 constituent fine cells —
        # devices in fine cells adjacent to the center were previously missed.
        from app.services.geofence import _expand_coarse_cells

        expanded = _expand_coarse_cells({snap_geohash5(19.125, 72.875)})
        assert len(expanded) == 25
        # Index-built: origin row/col plus ±2 fine steps, all distinct.
        assert "19.00_72.75" in expanded   # coarse-cell origin
        assert "19.20_72.95" in expanded   # far corner (k+4)
        assert "19.15_72.85" in expanded   # the float-trap row

    def test_expansion_anchored_to_coarse_origin(self) -> None:
        from app.services.geofence import _expand_coarse_cells

        # Center (19.125, 72.875) lives in the coarse cell [19.00, 19.25)².
        expanded = _expand_coarse_cells({snap_geohash5(19.125, 72.875)})
        lats = sorted({float(a.split("_")[0]) for a in expanded})
        lons = sorted({float(a.split("_")[1]) for a in expanded})
        assert lats == [19.0, 19.05, 19.1, 19.15, 19.2]
        assert lons == [72.75, 72.8, 72.85, 72.9, 72.95]

    def test_oversized_polygon_broadcasts(self) -> None:
        # 24°×20° box ⇒ ~8k matched coarse cells ⇒ ×25 expansion ≫ cap ⇒
        # broadcast without materializing the expansion.
        huge = [(32.0, 70.0), (32.0, 90.0), (8.0, 90.0), (8.0, 70.0), (32.0, 70.0)]
        ts = alert_target_set({"polygons": [huge]})
        assert ts.area_wide is True
        assert ts.coarse is True
        assert ts.topic_names() == ["alert_*"]
        assert ts.size == 0

    def test_target_set_multi_polygon_union(self) -> None:
        a = circle_polygon(*MUMBAI)
        b = circle_polygon(*DELHI)
        ts = alert_target_set({"polygons": [a, b]})
        assert snap_geohash5(*MUMBAI) in ts.geohashes
        assert snap_geohash5(*DELHI) in ts.geohashes


# --------------------------------------------------------------------------- #
# Alert store — registry, lazy expiry, event log
# --------------------------------------------------------------------------- #


class TestAlertStore:
    def test_put_resolves_targets(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("a1"))
        assert clean_store.summary()["count"] == 1
        ts = clean_store.targets_for("a1")
        assert ts is not None and ts.size > 0
        assert not ts.area_wide

    def test_area_wide_put(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("a2", polygons=[]))
        ts = clean_store.targets_for("a2")
        assert ts.area_wide is True
        assert ts.topic_names(prefix="x") == ["x_*"]

    def test_expired_sweep_respects_grace(self, clean_store: AlertStore) -> None:
        # Expired 10 min ago (grace is 300 s) vs 60 s ago (within grace).
        # NOTE: any read access sweeps — the first summary already drops `old`.
        clean_store.put(_mk_alert("old", expires_in_s=-600))
        clean_store.put(_mk_alert("fresh-ish", expires_in_s=-60))
        assert clean_store.summary()["count"] == 1
        assert clean_store.targets_for("old") is None
        assert clean_store.targets_for("fresh-ish") is not None

    def test_active_for_location_polygon_and_area_wide(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("konkan", polygons=[KONKAN_POLY]))
        clean_store.put(_mk_alert("nationwide", polygons=[]))
        mum = [a["identifier"] for a in clean_store.active_for_location(*MUMBAI)]
        assert "konkan" in mum and "nationwide" in mum
        delhi = [a["identifier"] for a in clean_store.active_for_location(*DELHI)]
        assert delhi == ["nationwide"]  # polygon containment respected

    def test_injected_flags_and_clear(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("feed-1"), injected=False)
        clean_store.put(_mk_alert("demo-1"), injected=True)
        assert clean_store.summary()["injected"] == 1
        assert clean_store.clear_injected() == 1
        assert clean_store.summary()["count"] == 1
        assert clean_store.summary()["injected"] == 0
        assert clean_store.clear_injected() == 0  # idempotent

    def test_remove_and_events(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("gone"))
        assert clean_store.remove("gone") is True
        assert clean_store.remove("gone") is False
        kinds = [e["kind"] for e in clean_store.events()]
        assert kinds[:2] == ["remove", "ingest"]  # newest first

    def test_put_many_count(self, clean_store: AlertStore) -> None:
        n = clean_store.put_many([_mk_alert("m1"), _mk_alert("m2")])
        assert n == 2 and clean_store.summary()["count"] == 2


# --------------------------------------------------------------------------- #
# TASK-048: CAP poller — diff ingest, injected survival, bookkeeping
# --------------------------------------------------------------------------- #


class TestCapPoller:
    def test_fixture_parses_two_infos(self) -> None:
        from pathlib import Path

        fixture = Path(__file__).resolve().parents[2] / "mock_fixtures" / "cap_alerts.xml"
        alerts = parse_cap_xml(fixture.read_text(encoding="utf-8"), expired_policy="extend")
        assert len(alerts) == 2
        idents = {a["identifier"] for a in alerts}
        assert len(idents) == 2  # regression: info blocks must not clobber
        assert any(a["severity"] == "Severe" and a["event"] == "Cyclone Warning" for a in alerts)
        assert any(a["severity"] == "Moderate" and a["event"] == "Heavy Rainfall Warning" for a in alerts)

    def test_first_poll_ingests_and_dispatches(self, clean_store: AlertStore) -> None:
        p = CapPoller(interval_s=60)
        stats = asyncio.run(p.poll_once())
        assert stats["fetched"] == 2
        assert stats["new"] == 2
        assert stats["removed"] == 0
        assert stats["pushed"] > 0  # dry-run: every resolved topic "sends"
        assert stats["duration_ms"] < 2500
        # Both severities landed with correct geometry.
        assert clean_store.summary()["by_severity"] == {"Severe": 1, "Moderate": 1}
        assert snap_geohash5(*MUMBAI) in clean_store.targets_for(
            "ndma-sachet-demo-2026-cyclone-001--cyclone-warning-0"
        ).geohashes

    def test_second_poll_is_noop_diff(self, clean_store: AlertStore) -> None:
        p = CapPoller(interval_s=60)
        asyncio.run(p.poll_once())
        again = asyncio.run(p.poll_once())
        assert again["fetched"] == 2
        assert again["new"] == 0 and again["removed"] == 0 and again["pushed"] == 0

    def test_removal_preserves_injected(self, clean_store: AlertStore) -> None:
        p = CapPoller(interval_s=60)
        asyncio.run(p.poll_once())
        clean_store.put(_mk_alert("demo-drill", polygons=[]), injected=True)
        # Feed now returns NOTHING for the fixture alerts → both removed,
        # injected demo alert must survive.
        p.fetch_alerts = lambda: asyncio.sleep(0, result=[])
        stats = asyncio.run(p.poll_once())
        assert stats["removed"] == 2
        assert stats["new"] == 0
        assert clean_store.summary()["count"] == 1
        assert clean_store.summary()["injected"] == 1

    def test_fetch_failure_is_swallowed_and_recorded(self, clean_store: AlertStore) -> None:
        p = CapPoller(interval_s=60)

        async def boom() -> list[dict]:
            raise RuntimeError("feed down")

        p.fetch_alerts = boom
        stats = asyncio.run(p.poll_once())
        assert stats["fetched"] == 0 and stats["new"] == 0
        assert p.last_error is not None and "feed down" in p.last_error
        # Recovery clears the error only on a healthy fetch.
        p.fetch_alerts = p._fetch
        asyncio.run(p.poll_once())
        assert p.last_error is None
        assert p.poll_count == 2

    def test_dispatch_targets_from_store_not_recomputed(self, clean_store: AlertStore) -> None:
        # dispatch_alert with explicit targets must not re-run geometry.
        ts = TargetSet(geohashes={snap_geohash5(*DELHI)})
        book = asyncio.run(dispatch_alert(_mk_alert("explicit"), targets=ts))
        assert book["targets"] == 1
        assert book["topics"] == 1
        assert book["sent"] == 1

    def test_lifespan_poller_running(self, client: TestClient) -> None:
        assert poller._task is not None and not poller._task.done()
        # First tick fires immediately; give the task a moment to schedule.
        for _ in range(50):
            if poller.poll_count >= 1:
                break
            time.sleep(0.05)
        assert poller.poll_count >= 1


# --------------------------------------------------------------------------- #
# TASK-050: FCM dispatcher — payload shape, budget, dry-run
# --------------------------------------------------------------------------- #


class TestDispatcher:
    def test_payload_shape_priority_ttl(self) -> None:
        alert = _mk_alert()
        payload = build_push_payload(alert, "mausam_alert_19.05_72.90", dry_run=False)
        msg = payload["message"]
        assert msg["topic"] == "mausam_alert_19.05_72.90"
        assert msg["android"]["priority"] == "HIGH"
        assert msg["android"]["ttl"] == "0s"
        assert msg["android"]["notification"]["channel_id"] == "mausam_disaster_alerts"
        assert msg["android"]["notification"]["click_action"] == "MAUSAM_ALERT_TAP"
        assert msg["notification"]["title"].startswith("SEVERE: ")
        assert msg["notification"]["body"]

    def test_payload_dry_run_prefix(self) -> None:
        alert = _mk_alert()
        dry = build_push_payload(alert, "t", dry_run=True)
        live = build_push_payload(alert, "t", dry_run=False)
        assert dry["message"]["notification"]["title"].startswith("[DRY-RUN] ")
        assert not live["message"]["notification"]["title"].startswith("[DRY-RUN]")

    def test_payload_body_truncated(self) -> None:
        alert = _mk_alert()
        alert["description"] = "x" * 5000
        body = build_push_payload(alert, "t")["message"]["notification"]["body"]
        assert len(body) <= 220

    def test_dispatch_dry_run_bookkeeping(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("disp-1", polygons=[circle_polygon(*MUMBAI)]))
        alert = clean_store.active()[0]
        book = asyncio.run(dispatch_alert(alert))
        assert book["identifier"] == "disp-1"
        assert book["mode"] == "dry-run"
        assert book["sent"] == book["topics"] == book["targets"]
        assert book["targets"] > 0
        assert book["under_budget"] is True
        assert book["elapsed_ms"] < 2500
        # Dispatch lands in the store's event trail for the inspector.
        kinds = [e["kind"] for e in alert_store.events()]
        assert "dispatch" in kinds

    def test_dispatch_area_wide_single_topic(self, clean_store: AlertStore) -> None:
        book = asyncio.run(dispatch_alert(_mk_alert("wide", polygons=[])))
        assert book["area_wide"] is True
        assert book["topics"] == 1

    def test_dispatch_under_budget_many_topics(self, clean_store: AlertStore) -> None:
        clean_store.put(_mk_alert("many", polygons=[circle_polygon(*MUMBAI)]))
        book = asyncio.run(dispatch_alert(clean_store.active()[0]))
        assert book["targets"] >= 100  # mumbai circle ≈ 158 fine cells
        assert book["under_budget"] is True  # parallel gather, dry-run


# --------------------------------------------------------------------------- #
# TASK-054: Admin injection tool — the jury demo path
# --------------------------------------------------------------------------- #


class TestAdminInjection:
    def test_inject_over_mumbai_full_pipeline(self, client: TestClient, clean_store: AlertStore) -> None:
        res = client.post("/v1/admin/inject-alert", json={
            "lat": MUMBAI[0], "lon": MUMBAI[1],
            "event": "Cyclone Warning", "severity": "Extreme",
        })
        assert res.status_code == 200
        data = res.json()
        alert, dispatch = data["alert"], data["dispatch"]

        assert alert["identifier"].startswith("demo-inject-")
        assert alert["severity"] == "Extreme"
        assert "SIMULATED DRILL" in alert["headline"]
        assert alert["injected"] is True
        assert dispatch["city"] == "Mumbai"
        assert dispatch["polygon_points"] == 17  # 16 vertices + closure
        assert dispatch["sent"] == dispatch["topics"] > 0
        assert dispatch["mode"] == "dry-run"
        assert dispatch["under_budget"] is True
        assert dispatch["inject_elapsed_ms"] < 2500

        # Store reflects the injection.
        assert clean_store.summary()["count"] == 1  # background ticks quieted
        assert clean_store.summary()["injected"] == 1

    def test_inject_by_city_key(self, client: TestClient, clean_store: AlertStore) -> None:
        res = client.post("/v1/admin/inject-alert", json={"city": "kochi", "severity": "Severe"})
        assert res.status_code == 200
        dispatch = res.json()["dispatch"]
        assert dispatch["city"] == "Kochi"
        assert dispatch["targets"] > 0

    def test_inject_kochi_hits_kochi_topics(self, client: TestClient, clean_store: AlertStore) -> None:
        res = client.post("/v1/admin/inject-alert", json={"city": "kochi"})
        topics = res.json()["dispatch"]["topics"]
        assert topics > 0

    def test_inject_default_severity_extreme(self, client: TestClient) -> None:
        res = client.post("/v1/admin/inject-alert", json={"city": "delhi"})
        assert res.json()["alert"]["severity"] == "Extreme"

    def test_inject_bad_severity_422(self, client: TestClient) -> None:
        res = client.post("/v1/admin/inject-alert", json={"city": "delhi", "severity": "Apocalyptic"})
        assert res.status_code == 422

    def test_inject_radius_bounds(self, client: TestClient) -> None:
        assert client.post("/v1/admin/inject-alert", json={"city": "delhi", "radius_deg": 0}).status_code == 422
        assert client.post("/v1/admin/inject-alert", json={"city": "delhi", "radius_deg": 3}).status_code == 422

    def test_clear_injected_endpoint(self, client: TestClient, clean_store: AlertStore) -> None:
        client.post("/v1/admin/inject-alert", json={"city": "mumbai"})
        client.post("/v1/admin/inject-alert", json={"city": "delhi"})
        assert clean_store.summary()["injected"] == 2
        res = client.request("DELETE", "/v1/admin/alerts/injected")
        assert res.status_code == 200
        assert res.json()["removed"] == 2
        assert clean_store.summary()["injected"] == 0

    def test_admin_alerts_listing_shape(self, client: TestClient, clean_store: AlertStore) -> None:
        client.post("/v1/admin/inject-alert", json={"city": "mumbai"})
        data = client.get("/v1/admin/alerts").json()
        assert set(data) >= {"summary", "alerts", "poller", "dispatcher_mode", "api_mode"}
        assert data["dispatcher_mode"] == "dry-run"
        assert data["poller"]["running"] is True
        assert data["poller"]["interval_s"] >= 5
        listed = data["alerts"]
        assert listed, "store should list fixture + injected alerts"
        for a in listed:
            assert set(a) >= {"identifier", "event", "severity", "injected", "target_cells", "area_wide"}
        injected = [a for a in listed if a["injected"]]
        assert len(injected) == 1
        assert injected[0]["target_cells"] > 0

    def test_poll_now_endpoint(self, client: TestClient, clean_store: AlertStore) -> None:
        # Re-point the session-quieted poller at the real fixture fetch for
        # exactly one cycle, then restore the quiet stub.
        poller.fetch_alerts = poller._fetch
        try:
            stats = client.post("/v1/admin/poll-now").json()
        finally:
            async def _none() -> list[dict]:
                return []

            poller.fetch_alerts = _none
        assert set(stats) >= {"fetched", "new", "removed", "pushed", "duration_ms"}
        assert stats["fetched"] == 2
        assert stats["new"] == 2  # fresh store → both fixture alerts are new
        assert clean_store.summary()["count"] == 2


# --------------------------------------------------------------------------- #
# Gateway unification — injected alerts surface on SDUI homes (demo promise)
# --------------------------------------------------------------------------- #


class TestGatewayStoreUnification:
    def test_injected_alert_pins_disaster_card_mumbai(self, client: TestClient, clean_store: AlertStore) -> None:
        client.post("/v1/admin/inject-alert", json={"city": "mumbai", "severity": "Extreme"})
        ctx = _seed_ctx("mumbai")
        assert ctx.cap_alerts, "store alert must reach the Mumbai weather context"
        assert ctx.cap_alerts[0].severity.value == "Extreme"
        widgets = compose_sdui(ctx, ["health", "commuter"])["widgets"]
        types = [w["type"] for w in widgets]
        assert types[0] == "disaster_lifeline_card"  # pinned FIRST
        assert "visibility_meter" in types  # health-persona staple follows

    def test_no_injection_delhi_stays_clean(self, client: TestClient, clean_store: AlertStore) -> None:
        client.post("/v1/admin/inject-alert", json={"city": "mumbai"})
        ctx = _seed_ctx("delhi")
        assert ctx.cap_alerts == []  # Delhi far outside the Mumbai polygon
        widgets = compose_sdui(ctx, ["health"])["widgets"]
        assert "disaster_lifeline_card" not in [w["type"] for w in widgets]

    def test_live_endpoint_carries_disaster_card(self, client: TestClient, clean_store: AlertStore) -> None:
        client.post("/v1/admin/inject-alert", json={"city": "mumbai", "severity": "Severe"})
        res = client.get("/v1/sdui/home", params={
            "lat": MUMBAI[0], "lon": MUMBAI[1], "personas": "health",
        })
        assert res.status_code == 200
        types = [w["type"] for w in res.json()["widgets"]]
        assert types[0] == "disaster_lifeline_card"

    def test_store_is_single_source(self, client: TestClient, clean_store: AlertStore) -> None:
        # Store alert ⇒ served to the context (only the store alert — no
        # parallel fixture fetch); empty store ⇒ NO alerts anywhere, which
        # keeps non-alert test modules hermetic by construction.
        client.post("/v1/admin/inject-alert", json={"city": "kochi", "severity": "Extreme"})
        ctx_store = _seed_ctx("kochi")
        assert [a.severity.value for a in ctx_store.cap_alerts] == ["Extreme"]

        alert_store.clear_all()
        ctx_empty = _seed_ctx("kochi")
        assert ctx_empty.cap_alerts == []

    def test_ctx_via_endpoint_sdui_kochi(self, client: TestClient, clean_store: AlertStore) -> None:
        # End-to-end: inject near Kochi → live SDUI home shows the card.
        client.post("/v1/admin/inject-alert", json={"city": "kochi", "severity": "Extreme"})
        types = [w["type"] for w in client.get("/v1/sdui/home", params={
            "lat": KOCHI[0], "lon": KOCHI[1], "personas": "commuter",
        }).json()["widgets"]]
        assert types[0] == "disaster_lifeline_card"


# --------------------------------------------------------------------------- #
# Parser edge cases (regression armour around the multi-info fix)
# --------------------------------------------------------------------------- #


class TestParseCapRegression:
    def test_single_info_keeps_plain_identifier(self) -> None:
        xml = """<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <identifier>single-1</identifier><sender>s</sender>
          <sent>2026-09-01T00:00:00+00:00</sent>
          <info><event>Heat Wave</event><severity>Severe</severity>
            <expires>2027-01-01T00:00:00+00:00</expires></info>
        </alert>"""
        alerts = parse_cap_xml(xml)
        assert [a["identifier"] for a in alerts] == ["single-1"]

    def test_multi_info_unique_stable_identifiers(self) -> None:
        xml = """<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <identifier>multi-1</identifier><sender>s</sender>
          <sent>2026-09-01T00:00:00+00:00</sent>
          <info><event>Cyclone Warning</event><severity>Extreme</severity>
            <expires>2027-01-01T00:00:00+00:00</expires></info>
          <info><event>Heavy Rainfall Warning</event><severity>Moderate</severity>
            <expires>2027-01-01T00:00:00+00:00</expires></info>
          <info><event>Thunderstorm Warning</event><severity>Minor</severity>
            <expires>2027-01-01T00:00:00+00:00</expires></info>
        </alert>"""
        alerts = parse_cap_xml(xml)
        assert len(alerts) == 3
        idents = [a["identifier"] for a in alerts]
        assert len(set(idents)) == 3
        assert idents == [
            "multi-1--cyclone-warning-0",
            "multi-1--heavy-rainfall-warning-1",
            "multi-1--thunderstorm-warning-2",
        ]

    def test_multi_info_stable_across_repolls(self) -> None:
        # Identifiers must be deterministic (slug + index), not random —
        # otherwise every poll would churn the diff.
        xml = open("mock_fixtures/cap_alerts.xml", encoding="utf-8").read() \
            if False else None
        from pathlib import Path

        fixture = Path(__file__).resolve().parents[2] / "mock_fixtures" / "cap_alerts.xml"
        text = fixture.read_text(encoding="utf-8")
        first = {a["identifier"] for a in parse_cap_xml(text, expired_policy="extend")}
        second = {a["identifier"] for a in parse_cap_xml(text, expired_policy="extend")}
        assert first == second

    def test_expired_info_drop_vs_extend(self) -> None:
        xml = """<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <identifier>exp-1</identifier><sender>s</sender>
          <sent>2020-01-01T00:00:00+00:00</sent>
          <info><event>Old Thing</event><severity>Minor</severity>
            <expires>2020-01-02T00:00:00+00:00</expires></info>
        </alert>"""
        assert parse_cap_xml(xml, expired_policy="drop") == []
        extended = parse_cap_xml(xml, expired_policy="extend")
        assert len(extended) == 1
        assert extended[0]["identifier"] == "exp-1"

    def test_malformed_xml_returns_empty(self) -> None:
        assert parse_cap_xml("<alert><unclosed>") == []

    def test_severity_normalization_lowercase(self) -> None:
        xml = """<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
          <identifier>sev-1</identifier><sender>s</sender>
          <sent>2026-09-01T00:00:00+00:00</sent>
          <info><event>Thing</event><severity>extreme</severity>
            <expires>2027-01-01T00:00:00+00:00</expires></info>
        </alert>"""
        assert parse_cap_xml(xml)[0]["severity"] == "Extreme"
