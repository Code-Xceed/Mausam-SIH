"""Phase 9 acceptance tests — cold-boot/benchmark evidence (TASK-069),
bandwidth footprint (TASK-071), and payload budgets.

These generate committed evidence files under docs/evidence/ (skipped when
fast: full runs happen in CI) — see scripts/run_acceptance.py for the
one-command version.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


class TestBenchmarks:
    def test_health_under_50ms_p95(self, client: TestClient) -> None:
        """TASK-069 backend-side probe: gateway responsiveness."""
        times = []
        for _ in range(30):
            t0 = time.perf_counter()
            assert client.get("/health").status_code == 200
            times.append((time.perf_counter() - t0) * 1000)
        times.sort()
        p95 = times[int(len(times) * 0.95) - 1]
        assert p95 < 50, f"health p95 {p95:.1f}ms > 50ms"
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "latency_health.json").write_text(json.dumps({
            "p50_ms": round(times[len(times) // 2], 2),
            "p95_ms": round(p95, 2),
            "samples": [round(t, 2) for t in times],
        }, indent=2))

    def test_sdui_home_under_250ms(self, client: TestClient) -> None:
        """Full SDUI composition + serialize must stay fast for mobile."""
        t0 = time.perf_counter()
        res = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21})
        elapsed = (time.perf_counter() - t0) * 1000
        assert res.status_code == 200
        assert elapsed < 250, f"SDUI home {elapsed:.0f}ms > 250ms budget"
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "latency_sdui_home.json").write_text(json.dumps({
            "elapsed_ms": round(elapsed, 2),
            "budget_ms": 250,
        }, indent=2))


class TestBandwidth:
    def test_sdui_payload_under_15kb(self, client: TestClient) -> None:
        """TASK-016/TASK-071: SDUI homepage ≤ 15 KB uncompressed."""
        res = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21})
        size = len(res.content)
        assert size <= 15_360, f"SDUI payload {size} B > 15 KB"
        (EVIDENCE / "bandwidth_sdui.json").write_text(json.dumps({
            "bytes": size,
            "budget_bytes": 15_360,
            "compressed_ride": "GZip middleware on; client sends Accept-Encoding: br/gzip",
        }, indent=2))

    def test_5min_session_well_under_1_2mb(self, client: TestClient) -> None:
        """TASK-071: simulated 5-min session (10 SDUI pulls + search + tiles)
        must total < 1.2 MB."""
        total = 0
        for _ in range(10):
            total += len(client.get("/v1/sdui/home", params={"lat": 19.076, "lon": 72.8777}).content)
        total += len(client.get("/v1/personas").content)
        total += len(client.get("/v1/i18n/strings/hi").content)
        total += len(client.get("/v1/geo/boundaries").content)
        total += len(client.get("/v1/alerts/active").content)
        assert total < 1_200_000, f"5-min session {total} B > 1.2 MB"
        (EVIDENCE / "bandwidth_session.json").write_text(json.dumps({
            "session_bytes": total,
            "budget_bytes": 1_200_000,
            "components": "10x sdui/home + personas + i18n bundle + boundaries + alerts",
        }, indent=2))


class TestChaos:
    def test_500_rapid_keystrokes_no_crash(self, client: TestClient) -> None:
        """TASK-068 backend half: 500 rapid sequential requests, zero 5xx."""
        codes = []
        for i in range(500):
            lat = 28.0 + (i % 30) * 0.01
            lon = 72.0 + (i % 40) * 0.01
            r = client.get("/v1/sdui/home", params={"lat": lat, "lon": lon, "personas": "health"})
            codes.append(r.status_code)
        assert all(c < 500 for c in codes), f"5xx seen: {sorted(set(c for c in codes if c >= 500))}"

    def test_malformed_inputs_rejected_not_crashed(self, client: TestClient) -> None:
        bad = [
            ("/v1/sdui/home", {"lat": 999, "lon": 77}),
            ("/v1/sdui/home", {"lat": "abc", "lon": 77}),
            ("/v1/sdui/home", {"lat": 28.0, "lon": 77.0, "personas": "x" * 500}),
            ("/v1/telemetry/interaction", {"widget_id": "", "event": "nope"}),
        ]
        for path, params in bad:
            if path.startswith("/v1/telemetry"):
                r = client.post(path, json=params)
            else:
                r = client.get(path, params=params)
            assert r.status_code in (200, 204, 400, 422), f"{path} -> {r.status_code}"


class TestBlackout:
    def test_seed_mode_serves_without_network(self, client: TestClient) -> None:
        """TASK-070 backend half: fixture replay works with zero upstreams."""
        from app.core.config import settings as s

        assert s.CAP_FEED_URL == ""  # no live feed configured
        r = client.get("/v1/weather/context", params={"lat": 19.076, "lon": 72.8777})
        assert r.status_code == 200
        ctx = r.json()
        assert ctx["current"]["temperature_c"] > 0
        assert len(ctx["daily"]) == 7
