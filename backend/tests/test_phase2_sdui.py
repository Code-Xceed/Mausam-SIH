"""Phase 2 tests — SDUI composer, personas, router encoding."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.sdui_composer import BUDGET_BYTES, MAX_WIDGETS, compose_sdui
from app.models.weather import WeatherContext

CITY_FIXTURES = [
    "weather_context_delhi.json",
    "weather_context_mumbai.json",
    "weather_context_kochi.json",
    "weather_context_vidarbha.json",
    "weather_context_shimla.json",
]

_CITY_COORDS = {
    "weather_context_delhi.json": (28.6139, 77.2090),
    "weather_context_mumbai.json": (19.0760, 72.8777),
    "weather_context_kochi.json": (9.9312, 76.2673),
    "weather_context_vidarbha.json": (21.1458, 79.0882),
    "weather_context_shimla.json": (31.1048, 77.1734),
}


def _ctx(name: str) -> WeatherContext:
    """Context through the FULL pipeline (gateway SEED mode) — includes
    marine tide enrichment and CAP merging, exactly like production."""
    import asyncio

    from app.services import gateway as gw_module

    lat, lon = _CITY_COORDS[name]
    gw_module.settings.API_MODE = "SEED"
    return asyncio.run(gw_module.gateway.get_weather_context(lat, lon))


def _commute_ready(ctx: WeatherContext) -> WeatherContext:
    """Re-anchor hourly points to 07:00+ so the fixture storm overlaps the
    07–09 commute window regardless of the wall clock (retime_fixture pins
    hourly to now+i, which makes banner assertions time-of-day dependent)."""
    base = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    hourly = [
        p.model_copy(update={"time": base + timedelta(hours=i)})
        for i, p in enumerate(ctx.hourly)
    ]
    return ctx.model_copy(update={"hourly": hourly})


class TestComposition:
    def test_delhi_health_renders_aqi_card(self) -> None:
        payload = compose_sdui(_ctx("weather_context_delhi.json"), ["health"])
        types = [w["type"] for w in payload["widgets"]]
        assert "aqi_radial_meter" in types
        assert "current_conditions" in types
        aqi = next(w for w in payload["widgets"] if w["type"] == "aqi_radial_meter")
        assert aqi["props"]["aqi"] == 187
        assert aqi["props"]["category"] == "Moderate"
        assert "advice" in aqi["props"]

    def test_kochi_coastal_renders_tide_card(self) -> None:
        payload = compose_sdui(_ctx("weather_context_kochi.json"), ["coastal"])
        types = [w["type"] for w in payload["widgets"]]
        assert "marine_tide_gauge" in types
        marine = next(w for w in payload["widgets"] if w["type"] == "marine_tide_gauge")
        assert marine["props"]["beach_flag"] == "yellow"
        assert len(marine["props"]["tide_curve"]) > 0

    def test_mumbai_commuter_pins_commute_banner(self) -> None:
        payload = compose_sdui(_commute_ready(_ctx("weather_context_mumbai.json")), ["commuter"])
        widgets = payload["widgets"]
        types = [w["type"] for w in widgets]
        assert "commute_safety_banner" in types
        # Pinned safety card is at/near the top
        assert types.index("commute_safety_banner") <= 1

    def test_mumbai_cyclone_pins_disaster_card_first(self) -> None:
        # CAP intake flows poller → alert_store → gateway; the suite quiets
        # the poller feed, so seed the store exactly as a poll tick would.
        from pathlib import Path

        from app.adapters.cap import parse_cap_xml
        from app.services.alert_store import alert_store

        fixture = Path(__file__).resolve().parents[2] / "mock_fixtures" / "cap_alerts.xml"
        alert_store.put_many(
            parse_cap_xml(fixture.read_text(encoding="utf-8"), expired_policy="extend")
        )
        try:
            payload = compose_sdui(_ctx("weather_context_mumbai.json"), ["health"])
            widgets = payload["widgets"]
            assert widgets[0]["type"] == "disaster_lifeline_card"
            assert widgets[0]["props"]["severity"] == "Severe"
            assert "112" in json.dumps(widgets[0]["props"])
        finally:
            alert_store.clear_all()

    def test_vidarbha_farmer_renders_agro_card(self) -> None:
        payload = compose_sdui(_ctx("weather_context_vidarbha.json"), ["farmer"])
        types = [w["type"] for w in payload["widgets"]]
        assert "meghdoot_agro_card" in types
        agro = next(w for w in payload["widgets"] if w["type"] == "meghdoot_agro_card")
        assert agro["props"]["soil_moisture_pct"] == pytest.approx(18.4)
        assert len(agro["props"]["advisories"]) >= 3

    def test_shimla_commuter_renders_visibility(self) -> None:
        payload = compose_sdui(_ctx("weather_context_shimla.json"), ["commuter"])
        types = [w["type"] for w in payload["widgets"]]
        assert "visibility_meter" in types
        vis = next(w for w in payload["widgets"] if w["type"] == "visibility_meter")
        assert vis["props"]["visibility_m"] == 900
        assert "fog" in vis["props"]["note"].lower()

    def test_missing_data_skips_widget(self) -> None:
        # Delhi has no marine block → no tide card regardless of persona.
        payload = compose_sdui(_ctx("weather_context_delhi.json"), ["coastal"])
        types = [w["type"] for w in payload["widgets"]]
        assert "marine_tide_gauge" not in types

    def test_unknown_persona_falls_back_to_defaults(self) -> None:
        payload = compose_sdui(_ctx("weather_context_delhi.json"), ["nonexistent"])
        assert len(payload["widgets"]) >= 2  # current_conditions at minimum

    def test_empty_personas_falls_back(self) -> None:
        payload = compose_sdui(_ctx("weather_context_delhi.json"), [])
        assert payload["personas"]["active"]  # default personas applied

    def test_schema_contract_fields(self) -> None:
        payload = compose_sdui(_ctx("weather_context_delhi.json"), ["health"])
        assert payload["schema_version"] == "v1"
        assert payload["personas"]["engine"] == "tier_a_deterministic_v1"
        for w in payload["widgets"]:
            assert "type" in w and "props" in w and "priority" in w
            assert 0 <= w["priority"] <= 100

    def test_widget_count_capped(self) -> None:
        payload = compose_sdui(_ctx("weather_context_mumbai.json"), ["health", "commuter", "travel", "planner"])
        assert len(payload["widgets"]) <= MAX_WIDGETS

    def test_budget_under_15kb_uncompressed(self) -> None:
        for name in CITY_FIXTURES:
            payload = compose_sdui(_ctx(name), ["health", "commuter"])
            size = len(json.dumps(payload, separators=(",", ":")))
            assert size <= BUDGET_BYTES, f"{name}: {size} bytes > budget"

    def test_running_windows_exclude_hot_stormy_hours(self) -> None:
        payload = compose_sdui(_ctx("weather_context_delhi.json"), ["fitness"])
        if running := next((w for w in payload["widgets"] if w["type"] == "running_window_timeline"), None):
            for win in running["props"]["windows"]:
                assert win["avg_temp_c"] <= 30

    def test_event_calendar_scores(self) -> None:
        payload = compose_sdui(_ctx("weather_context_mumbai.json"), ["planner"])
        if cal := next((w for w in payload["widgets"] if w["type"] == "event_planner_calendar"), None):
            for day in cal["props"]["days"]:
                assert 0 <= day["score"] <= 100
                assert day["suitability"] in {"excellent", "good", "fair", "poor"}


class TestSduiRouter:
    @pytest.fixture(scope="class")
    def client(self) -> TestClient:
        with TestClient(app) as c:
            yield c

    def test_home_returns_valid_payload(self, client: TestClient) -> None:
        res = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21})
        assert res.status_code == 200
        body = res.json()
        assert body["schema_version"] == "v1"
        assert body["widgets"]
        assert res.headers["X-SDUI-Widget-Count"] == str(len(body["widgets"]))

    def test_brotli_when_accepted(self, client: TestClient) -> None:
        res = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21},
            headers={"Accept-Encoding": "br"},
        )
        assert res.status_code == 200
        assert res.headers.get("Content-Encoding") == "br"
        assert int(res.headers["X-SDUI-Brotli-Bytes"]) < int(res.headers["X-SDUI-Size-Bytes"])

    def test_etag_304_roundtrip(self, client: TestClient) -> None:
        res1 = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21})
        etag = res1.headers["ETag"]
        res2 = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21},
            headers={"If-None-Match": etag},
        )
        assert res2.status_code == 304

    def test_personas_change_content(self, client: TestClient) -> None:
        r1 = client.get("/v1/sdui/home", params={"lat": 9.93, "lon": 76.27, "personas": "coastal"})
        r2 = client.get("/v1/sdui/home", params={"lat": 9.93, "lon": 76.27, "personas": "farmer"})
        assert r1.headers["ETag"] != r2.headers["ETag"]

    def test_etag_survives_brotli(self, client: TestClient) -> None:
        """304 must work even when first response was Brotli-compressed."""
        r1 = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21},
            headers={"Accept-Encoding": "br"},
        )
        etag = r1.headers["ETag"]
        r2 = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21},
            headers={"If-None-Match": etag},
        )
        assert r2.status_code == 304
