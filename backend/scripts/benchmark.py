"""Full-service benchmark harness — every Mausam API vs its acceptance target.

Exercises ALL 26 endpoints with realistic traffic plus direct micro-benchmarks
of the ML/geofence cores, compares measured numbers against the SIH/DPR
acceptance targets, and writes docs/evidence/benchmark_report.json.

Exit code: 0 = every target met; 1 = at least one FAILED row (fix and re-run).

Usage:
    cd backend && .venv/Scripts/python scripts/benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

# Make `app` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.adapters.cap import parse_cap_xml  # noqa: E402
from app.main import app  # noqa: E402
from app.ml.context import build_context_vector  # noqa: E402
from app.ml.linucb import LinUCB  # noqa: E402
from app.services import gateway as gw_module  # noqa: E402
from app.services.alert_store import alert_store  # noqa: E402
from app.services.bandit_ranker import BANDIT_ARMS, BanditRanker  # noqa: E402
from app.services.geofence import alert_target_set, circle_polygon  # noqa: E402
from app.services.sdui_composer import compose_sdui  # noqa: E402

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence"

CITIES = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "kochi": (9.9312, 76.2673),
    "vidarbha": (21.1458, 79.0882),
    "shimla": (31.1048, 77.1734),
}

RESULTS: list[dict] = []


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(len(s) * p) - 1))
    return s[idx]


def record(section: str, name: str, value: float, target: float, unit: str,
           basis: str, higher_is_worse: bool = True) -> None:
    ok = (value <= target) if higher_is_worse else (value >= target)
    RESULTS.append({
        "section": section, "metric": name, "measured": round(value, 3),
        "target": target, "unit": unit, "basis": basis,
        "status": "PASS" if ok else "FAIL",
    })
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}: {value:.3f} {unit} (target {'<=' if higher_is_worse else '>='} {target})")


def bench_endpoint(client: TestClient, section: str, name: str, method: str,
                   path: str, n: int, target_ms: float, basis: str, **kwargs) -> dict:
    """Hit an endpoint n times; record p95 latency; return the last response."""
    times: list[float] = []
    response = None
    for _ in range(n):
        t0 = time.perf_counter()
        response = client.request(method, path, **kwargs)
        times.append((time.perf_counter() - t0) * 1000)
        assert response.status_code < 500, f"{path} -> {response.status_code}"
    record(section, f"{name}.p95_ms", pct(times, 0.95), target_ms, "ms", basis)
    if RESULTS and times:
        RESULTS[-1]["p50_ms"] = round(statistics.median(times), 3)
        RESULTS[-1]["samples"] = n
    return response  # type: ignore[return-value]


def main() -> int:
    # Windows consoles default to cp1252 — never crash on pretty output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    gw_module.settings.API_MODE = "SEED"
    failures_before = len(RESULTS)

    with TestClient(app) as client:
        # Deterministic pipeline state: ingest fixture alerts via the real
        # poll path (same as a live poll tick).
        stats = client.post("/v1/admin/poll-now").json()
        print(f"boot: CAP poll ingested {stats['new']} alerts "
              f"({alert_store.summary()['by_severity']})")

        # ---------------------------------------------------------- META #
        print("\n== meta ==")
        bench_endpoint(client, "meta", "health", "GET", "/health", 50, 50,
                       "TASK-069 liveness probe responsiveness")
        bench_endpoint(client, "meta", "ready", "GET", "/ready", 20, 50,
                       "readiness probe")

        # ------------------------------------------------------- WEATHER #
        print("\n== weather ==")
        for key, (lat, lon) in CITIES.items():
            bench_endpoint(client, "weather", f"context_{key}", "GET",
                           "/v1/weather/context", 10, 500,
                           "full gateway compose (fixture replay)", params={"lat": lat, "lon": lon})

        # ---------------------------------------------------------- SDUI #
        print("\n== sdui ==")
        res = bench_endpoint(client, "sdui", "home_delhi", "GET", "/v1/sdui/home",
                             30, 250, "TASK-016 compose+serialize budget",
                             params={"lat": 28.61, "lon": 77.21, "personas": "health,commuter"})
        record("sdui", "home.payload_bytes", len(res.content), 15_360, "B",
               "TASK-016 15 KB budget (uncompressed)")
        # Brotli wire size. NOTE: httpx transparently decompresses .content,
        # so the honest wire size is the backend's own header (cross-checked
        # against Content-Encoding).
        br = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21},
                        headers={"Accept-Encoding": "br"})
        assert br.headers.get("Content-Encoding") == "br", "Brotli path did not engage"
        wire = int(br.headers["X-SDUI-Brotli-Bytes"])
        record("sdui", "home.payload_brotli_bytes", wire, 15_360, "B",
               "wire size with Accept-Encoding: br")
        record("sdui", "home.compression_ratio",
               RESULTS[-2]["measured"] / max(wire, 1), 1.0, "x",
               "uncompressed/wire — higher is better", higher_is_worse=False)
        # ETag/304 revalidation path (mobile pull-to-refresh)
        etag = res.headers.get("etag")
        t0 = time.perf_counter()
        re304 = client.get("/v1/sdui/home", params={"lat": 28.61, "lon": 77.21},
                           headers={"If-None-Match": etag} if etag else {})
        record("sdui", "revalidation_304.p95_ms", (time.perf_counter() - t0) * 1000,
               100, "ms", "TASK-022 pull-to-refresh save")
        assert re304.status_code == 304, f"expected 304, got {re304.status_code}"
        # Bandit engine variant
        bench_endpoint(client, "sdui", "home_bandit_engine", "GET", "/v1/sdui/home",
                       15, 250, "LinUCB ranking variant",
                       params={"lat": 28.61, "lon": 77.21, "engine": "bandit"})
        # Multi-city carousel
        bench_endpoint(client, "sdui", "home_multi_city", "GET", "/v1/sdui/home",
                       10, 250, "TASK-034 carousel with 3 extra cities",
                       params={"lat": 19.076, "lon": 72.8777,
                               "cities": "28.61:77.21,9.93:76.27,31.10:77.17"})

        # ------------------------------------------------------ BANDIT #
        print("\n== bandit/telemetry ==")
        ranker = BanditRanker.instance()
        ranker.reset()
        ctx = asyncio.run(gw_module.gateway.get_weather_context(*CITIES["delhi"]))
        built = build_context_vector(ctx, ["health"])
        x = built["x"]

        t0 = time.perf_counter()
        build_context_vector(ctx, ["health", "commuter"])
        record("ml", "context_vector.ms", (time.perf_counter() - t0) * 1000, 5,
               "ms", "TASK-040 <5 ms")

        model = LinUCB(dim=built["dim"], arms=list(BANDIT_ARMS), seed=7)
        t0 = time.perf_counter()
        for _ in range(50):
            model.select(x, list(BANDIT_ARMS))
        record("ml", "linucb_select.avg_ms", (time.perf_counter() - t0) * 1000 / 50,
               5, "ms", "TASK-041 UCB over 9 arms")

        t0 = time.perf_counter()
        for _ in range(50):
            ranker.rank(ctx, ["health", "commuter"], list(BANDIT_ARMS))
        record("ml", "bandit_ranker.rank.avg_ms", (time.perf_counter() - t0) * 1000 / 50,
               25, "ms", "full ranking incl. warm priors")

        ingest = bench_endpoint(client, "telemetry", "interaction", "POST",
                                "/v1/telemetry/interaction", 30, 50,
                                "TASK-043 204 immediate, non-blocking",
                                json={"widget_id": "aqi_radial_meter",
                                      "arm": "aqi_radial_meter", "event": "click",
                                      "x": [1.0] + [0.0] * (built["dim"] - 1)})
        assert ingest.status_code == 204
        bench_endpoint(client, "bandit_api", "stats", "GET", "/v1/debug/bandit/stats",
                       10, 100, "inspector payload")
        bench_endpoint(client, "bandit_api", "arms", "GET", "/v1/debug/bandit/arms",
                       10, 100, "arm vocabulary")

        # ------------------------------------------------- CAP pipeline #
        print("\n== CAP pipeline (disaster path) ==")
        t0 = time.perf_counter()
        target_set = alert_target_set({
            "polygons": [circle_polygon(*CITIES["mumbai"])],
        })
        record("geofence", "mumbai_circle.resolve_ms", (time.perf_counter() - t0) * 1000,
               500, "ms", f"TASK-049 polygon clipping ({target_set.size} cells)")

        fixture = Path(__file__).resolve().parents[2] / "mock_fixtures" / "cap_alerts.xml"
        t0 = time.perf_counter()
        parsed = parse_cap_xml(fixture.read_text(encoding="utf-8"), expired_policy="extend")
        record("cap", "parse_fixture.ms", (time.perf_counter() - t0) * 1000, 50,
               "ms", f"TASK-048 parse ({len(parsed)} infos)")

        injected = client.post("/v1/admin/inject-alert",
                               json={"city": "mumbai", "severity": "Extreme"}).json()
        record("dispatcher", "inject_alert.total_ms",
               injected["dispatch"]["inject_elapsed_ms"], 2500, "ms",
               "TASK-050/054 full geofence+dispatch budget")
        record("dispatcher", "dispatch.topics", injected["dispatch"]["topics"],
               1, "topics", "geofence fan-out must resolve >= 1 topic",
               higher_is_worse=False)
        bench_endpoint(client, "cap", "poll_now", "POST", "/v1/admin/poll-now",
                       5, 2500, "TASK-048 diff tick (ingest+dispatch)")
        bench_endpoint(client, "cap", "admin_alerts", "GET", "/v1/admin/alerts",
                       10, 100, "control-panel listing")
        bench_endpoint(client, "alerts", "active_feed", "GET", "/v1/alerts/active",
                       10, 100, "TASK-055 map polygon feed")
        client.request("DELETE", "/v1/admin/alerts/injected")

        # ---------------------------------------------------- FAVORITES #
        print("\n== favorites / privacy ==")
        bench_endpoint(client, "favorites", "sync", "POST", "/v1/favorites/sync",
                       20, 100, "TASK-028 dual-write mirror",
                       json={"device_id_hash": "benchmark0device0hash0",
                             "favorites": [{"name": "Mumbai", "lat": 19.07, "lon": 72.87,
                                            "state": "MH"}]})
        bench_endpoint(client, "favorites", "fetch", "GET",
                       "/v1/favorites/sync/benchmark0device0hash0", 20, 100,
                       "multi-device restore")
        t0 = time.perf_counter()
        client.post("/v1/privacy/purge", json={"device_id_hash": "benchmark0device0hash0"})
        record("privacy", "purge.ms", (time.perf_counter() - t0) * 1000, 100,
               "ms", "TASK-072 erase-all")

        # --------------------------------------------------------- I18N #
        print("\n== i18n ==")
        bench_endpoint(client, "i18n", "languages", "GET", "/v1/i18n/languages",
                       10, 100, "TASK-063 selector vocab")
        for lang in ("hi", "ta", "bn", "te", "mr"):
            bench_endpoint(client, "i18n", f"strings_{lang}", "GET",
                           f"/v1/i18n/strings/{lang}", 6, 100,
                           "TASK-062 offline bundle")
        bench_endpoint(client, "i18n", "translate", "POST", "/v1/i18n/translate",
                       15, 100, "glossary engine",
                       json={"text": "rain", "target_lang": "hi"})

        # ---------------------------------------------------------- GEO #
        print("\n== geo ==")
        bench_endpoint(client, "geo", "boundaries", "GET", "/v1/geo/boundaries",
                       10, 100, "TASK-060 boundary rings")

        def tile_for(lat: float, lon: float, z: int) -> tuple[int, int]:
            import math as _m

            n = 2**z
            x = int((lon + 180.0) / 360.0 * n)
            lat_rad = _m.radians(lat)
            y = int((1.0 - _m.log(_m.tan(lat_rad) + 1 / _m.cos(lat_rad)) / _m.pi) / 2 * n)
            return x, y

        # Tiles anchored on real demo cities (a hardcoded guess lands on
        # ocean and measures an empty tile, not the service).
        for z, (lat, lon) in [(5, CITIES["delhi"]), (7, CITIES["mumbai"]), (11, CITIES["delhi"])]:
            x, y = tile_for(lat, lon, z)
            res_t = bench_endpoint(client, "geo", f"tile_z{z}", "GET",
                                   f"/v1/geo/tile/{z}/{x}/{y}.json",
                                   8, 100, "TASK-059 viewport bundle")
            record("geo", f"tile_z{z}.bytes", len(res_t.content), 60_000, "B",
                   "TASK-059 <60 KB per view")
            kinds = {f["properties"]["kind"] for f in res_t.json()["features"]}
            assert "boundary" in kinds, f"z{z} tile unexpectedly empty"
        bench_endpoint(client, "personas", "list", "GET", "/v1/personas", 10, 100,
                       "persona vocabulary")

        # -------------------------------------------- 5-min session sim #
        print("\n== bandwidth (5-min session simulation) ==")
        total = 0
        total += len(client.get("/v1/sdui/home", params={"lat": 19.076, "lon": 72.8777,
                                                         "personas": "commuter,coastal"}).content) * 10
        total += len(client.get("/v1/i18n/strings/hi").content)
        total += len(client.get("/v1/geo/boundaries").content)
        total += len(client.get("/v1/alerts/active").content)
        total += len(client.get("/v1/personas").content)
        record("bandwidth", "session_5min.bytes", total, 1_200_000, "B",
               "TASK-071 <1.2 MB per 5-min session")

        # -------------------------------------------- concurrency probe #
        print("\n== concurrency (50 parallel SDUI) ==")

        async def parallel_probe() -> list[float]:
            from httpx import ASGITransport, AsyncClient

            latencies: list[float] = []
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                async def one() -> float:
                    t = time.perf_counter()
                    r = await ac.get("/v1/sdui/home",
                                     params={"lat": 19.076, "lon": 72.8777})
                    latencies.append((time.perf_counter() - t) * 1000)
                    assert r.status_code == 200

                await asyncio.gather(*(one() for _ in range(50)))
            return latencies

        lat = asyncio.run(parallel_probe())
        record("concurrency", "sdui_x50.p95_ms", pct(lat, 0.95), 500, "ms",
               "single-worker in-process saturation")

    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    passed = [r for r in RESULTS if r["status"] == "PASS"]

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "targets_total": len(RESULTS),
        "passed": len(passed),
        "failed": len(failed),
        "results": RESULTS,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "benchmark_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{'=' * 62}\nBENCHMARK SUMMARY: {len(passed)} PASS / {len(failed)} FAIL "
          f"of {len(RESULTS)} targets -> {out.relative_to(EVIDENCE.parents[2])}")
    for f in failed:
        print(f"  ❌ {f['section']}.{f['metric']}: {f['measured']} {f['unit']} "
              f"(target {f['target']}) — {f['basis']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
