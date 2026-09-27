"""Phase 0 smoke tests — the API contract is frozen from day one."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    # Hit /health once inside lifespan context to confirm boot wiring.
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["api_mode"] in {"LIVE", "HYBRID", "SEED"}


def test_weather_context_contract(client: TestClient) -> None:
    res = client.get("/v1/weather/context", params={"lat": 28.61, "lon": 77.21})
    assert res.status_code == 200
    ctx = res.json()

    assert ctx["location"]["display_name"] == "New Delhi"
    assert ctx["current"]["temperature_c"] == pytest.approx(34.2, abs=0.01)
    assert ctx["air_quality"]["aqi"] == 187
    assert ctx["air_quality"]["category"] == "Moderate"  # derived, not trusted
    assert ctx["current"]["observed_at"] > "2026-01-01"  # retimed, not stale
    assert len(ctx["hourly"]) == 12
    assert len(ctx["daily"]) == 7


def test_weather_context_rejects_bad_coords(client: TestClient) -> None:
    res = client.get("/v1/weather/context", params={"lat": 999, "lon": 77.21})
    assert res.status_code == 422


def test_sdui_home_etag(client: TestClient) -> None:
    res = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21})
    assert res.status_code == 200
    etag = res.headers.get("ETag")
    assert etag

    # Second request with If-None-Match should get 304 Not Modified.
    res2 = client.get(
        "/v1/sdui/home",
        params={"lat": 28.61, "lon": 77.21},
        headers={"If-None-Match": etag},
    )
    assert res2.status_code == 304


def test_telemetry_ingest_returns_204(client: TestClient) -> None:
    res = client.post(
        "/v1/telemetry/interaction",
        json={
            "widget_id": "aqi_radial_meter",
            "event": "click",
            "dwell_ms": 4200,
        },
    )
    assert res.status_code == 204


def test_telemetry_rejects_unknown_event(client: TestClient) -> None:
    res = client.post(
        "/v1/telemetry/interaction",
        json={"widget_id": "x", "event": "hover"},
    )
    assert res.status_code == 422
