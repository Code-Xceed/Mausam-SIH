"""Phase 4 tests — personas endpoint, multi-city carousel, UV polish."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.weather import WeatherContext
from app.services import gateway as gw_module
from app.services.sdui_composer import compose_sdui, summarize_city

CITY_COORDS = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "kochi": (9.9312, 76.2673),
    "vidarbha": (21.1458, 79.0882),
    "shimla": (31.1048, 77.1734),
}


def _seed_ctx(key: str):
    gw_module.settings.API_MODE = "SEED"
    lat, lon = CITY_COORDS[key]
    return asyncio.run(gw_module.gateway.get_weather_context(lat, lon))


def _commute_ready(ctx: WeatherContext) -> WeatherContext:
    """Re-anchor hourly to 07:00+ so the fixture storm overlaps the commute
    window regardless of wall clock (retime_fixture makes hourly = now+i)."""
    base = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    hourly = [
        p.model_copy(update={"time": base + timedelta(hours=i)})
        for i, p in enumerate(ctx.hourly)
    ]
    return ctx.model_copy(update={"hourly": hourly})


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestPersonasEndpoint:
    def test_lists_all_8(self, client: TestClient) -> None:
        res = client.get("/v1/personas")
        assert res.status_code == 200
        data = res.json()["personas"]
        assert len(data) == 8
        keys = {p["key"] for p in data}
        assert keys == {
            "health", "fitness", "coastal", "travel",
            "family", "farmer", "commuter", "planner",
        }

    def test_shape(self, client: TestClient) -> None:
        p = client.get("/v1/personas").json()["personas"][0]
        assert set(p.keys()) == {"key", "label", "icon", "tagline", "widgets"}
        assert isinstance(p["widgets"], list)


class TestMultiCity:
    def test_summarize_city_shape(self) -> None:
        s = summarize_city(_seed_ctx("delhi"))
        assert s["name"] == "New Delhi"
        assert "temp_max_c" in s and "condition" in s and "rain_pct" in s

    def test_composer_adds_carousel_with_extras(self) -> None:
        ctx = _seed_ctx("delhi")
        extras = [summarize_city(_seed_ctx("kochi")), summarize_city(_seed_ctx("shimla"))]
        payload = compose_sdui(ctx, ["travel"], extra_city_summaries=extras)
        types = [w["type"] for w in payload["widgets"]]
        assert "travel_multi_city_carousel" in types
        card = next(w for w in payload["widgets"] if w["type"] == "travel_multi_city_carousel")
        assert len(card["props"]["cities"]) == 3  # home + 2 extras
        assert card["props"]["cities"][0]["name"] == "New Delhi"

    def test_no_carousel_without_extras(self) -> None:
        payload = compose_sdui(_seed_ctx("delhi"), ["travel"])
        types = [w["type"] for w in payload["widgets"]]
        assert "travel_multi_city_carousel" not in types

    def test_extras_capped_at_6_cities_total(self) -> None:
        ctx = _seed_ctx("delhi")
        extras = [summarize_city(_seed_ctx(k)) for k in ("mumbai", "kochi", "shimla", "vidarbha")]
        extras = extras * 3  # 9 extras — composer must cap
        payload = compose_sdui(ctx, ["travel"], extra_city_summaries=extras)
        card = next(
            (w for w in payload["widgets"] if w["type"] == "travel_multi_city_carousel"),
            None,
        )
        assert card is not None
        assert len(card["props"]["cities"]) <= 6

    def test_router_cities_param(self, client: TestClient) -> None:
        res = client.get(
            "/v1/sdui/home",
            params={
                "lat": 28.61, "lon": 77.21,
                "personas": "travel",
                "cities": "9.93:76.27,31.10:77.17",
            },
        )
        assert res.status_code == 200
        types = [w["type"] for w in res.json()["widgets"]]
        assert "travel_multi_city_carousel" in types

    def test_router_bad_city_pairs_ignored(self, client: TestClient) -> None:
        res = client.get(
            "/v1/sdui/home",
            params={"lat": 28.61, "lon": 77.21, "cities": "garbage,1.0:2.0:3.0"},
        )
        assert res.status_code == 200
        types = [w["type"] for w in res.json()["widgets"]]
        assert "travel_multi_city_carousel" not in types


class TestUvPolish:
    def test_uv_advice_present_when_uv_available(self) -> None:
        payload = compose_sdui(_seed_ctx("delhi"), ["health"])
        card = next(w for w in payload["widgets"] if w["type"] == "current_conditions")
        props = card["props"]
        assert props.get("uv_index") is not None
        assert props.get("uv_advice")

    def test_uv_very_high_wording(self) -> None:
        payload = compose_sdui(_seed_ctx("vidarbha"), ["health"])  # UV 9.1
        props = next(
            w for w in payload["widgets"] if w["type"] == "current_conditions"
        )["props"]
        assert "Very high" in props["uv_advice"]


class TestDemoScenarios:
    """Full persona-switch verification for the TASK-039 jury demo."""

    def test_quick_switch_scene_delhi_health(self) -> None:
        payload = compose_sdui(_seed_ctx("delhi"), ["health"])
        types = [w["type"] for w in payload["widgets"]]
        assert "aqi_radial_meter" in types
        # health persona must rank AQI above baseline current_conditions
        assert types.index("aqi_radial_meter") < types.index("current_conditions")

    def test_quick_switch_scene_kochi_coastal(self) -> None:
        payload = compose_sdui(_seed_ctx("kochi"), ["coastal"])
        types = [w["type"] for w in payload["widgets"]]
        # Kochi's hourly rain overlaps the 14-16h commute window, so the
        # safety banner legitimately pins first (rules veto rankings); the
        # tide card must still lead the persona-scored feed.
        assert types.index("marine_tide_gauge") <= 1
        if "commute_safety_banner" in types:
            assert types.index("marine_tide_gauge") < types.index("travel_packing_carousel")

    def test_quick_switch_scene_vidarbha_farmer(self) -> None:
        payload = compose_sdui(_seed_ctx("vidarbha"), ["farmer"])
        types = [w["type"] for w in payload["widgets"]]
        assert types[0] == "meghdoot_agro_card"

    def test_quick_switch_scene_fitness(self) -> None:
        payload = compose_sdui(_seed_ctx("delhi"), ["fitness"])
        types = [w["type"] for w in payload["widgets"]]
        assert "running_window_timeline" in types
        assert types.index("running_window_timeline") < types.index("current_conditions")

    def test_multi_persona_blend(self) -> None:
        payload = compose_sdui(_commute_ready(_seed_ctx("mumbai")), ["commuter", "family"])
        types = [w["type"] for w in payload["widgets"]]
        # both commute-relevant cards present and top-ranked
        assert "commute_safety_banner" in types[:2]
