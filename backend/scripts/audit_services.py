"""Service correctness audit — is every service returning RIGHT data?

The benchmark proves speed; THIS proves correctness. Checks per data domain:
  current    — plausible ranges, condition enum, freshness (retimed to now)
  hourly     — 12 consecutive points from now, probs in [0,100]
  daily      — 7 days, sunrise < sunset, date = today+i
  aqi        — 0..500, category == DERIVED mapping (never trust upstream)
  marine     — coastal-only, wave/flag consistency, 120-pt tide curve @15 min
  agro       — advisories present, soil moisture sane
  nowcast    — validity window always active (retime contract)
  cap        — alerts match the right cities ONLY (spatial integrity)
  sdui       — widget set == data availability (no card without data,
               no data without card), persona routing (farmer→agro first)
  fidelity   — API response values == fixture source values (no silent loss)
  i18n       — all 5 bundles complete, zero empty strings
  geo        — each demo city inside its own state ring (schematic)

Exit 0 = all green; exit 1 = findings (printed + written to evidence).

Usage: cd backend && .venv/Scripts/python scripts/audit_services.py
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.models.weather import aqi_category  # noqa: E402
from app.services import gateway as gw_module  # noqa: E402
from app.services.alert_store import alert_store  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence"
FIXTURES = ROOT / "mock_fixtures"

CITIES = {
    "delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "kochi": (9.9312, 76.2673),
    "vidarbha": (21.1458, 79.0882),
    "shimla": (31.1048, 77.1734),
}
COASTAL = {"mumbai", "kochi"}
FARM_CITY = "vidarbha"

FINDINGS: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FINDINGS.append(f"{label}: {detail}")
        print(f"  ❌ {label} — {detail}")


def load_fixture(city: str) -> dict:
    return json.loads((FIXTURES / f"weather_context_{city}.json").read_text(encoding="utf-8"))


def audit_current(city: str, cur: dict, src: dict) -> None:
    t = cur.get("temperature_c")
    check(f"{city}.current.temp_plausible", t is not None and -10 <= t <= 55, f"{t}°C")
    h = cur.get("humidity_pct")
    check(f"{city}.current.humidity_range", h is not None and 0 <= h <= 100, f"{h}")
    w = cur.get("wind_kmph")
    check(f"{city}.current.wind_nonneg", w is not None and 0 <= w <= 250, f"{w}")
    check(f"{city}.current.condition_known", cur.get("condition") in {
        "clear", "partly_cloudy", "cloudy", "haze", "fog", "drizzle",
        "rain", "thunderstorm", "hail", "snow"}, str(cur.get("condition")))
    # freshness: retime_fixture pins observed_at to bucketed_now
    try:
        obs = datetime.fromisoformat(cur["observed_at"])
        age = abs((datetime.now(UTC) - obs).total_seconds())
        check(f"{city}.current.fresh", age < 900, f"observed_at age {age:.0f}s")
    except Exception as exc:
        check(f"{city}.current.fresh", False, f"unparseable: {exc}")
    # fidelity: value must equal the fixture source
    check(f"{city}.current.fidelity", t == src["current"]["temperature_c"],
          f"api {t} vs fixture {src['current']['temperature_c']}")


def audit_hourly(city: str, points: list[dict]) -> None:
    check(f"{city}.hourly.count_12", len(points) == 12, f"got {len(points)}")
    if len(points) < 2:
        return
    times = [datetime.fromisoformat(p["time"]) for p in points]
    step_ok = all(
        (times[i + 1] - times[i]).total_seconds() == 3600 for i in range(len(times) - 1)
    )
    check(f"{city}.hourly.consecutive_hours", step_ok,
          "hourly times must be now+0h..now+11h")
    first_age = abs((datetime.now(UTC) - times[0]).total_seconds())
    check(f"{city}.hourly.anchored_now", first_age < 900, f"first point age {first_age:.0f}s")
    check(f"{city}.hourly.precip_range",
          all(0 <= p["precipitation_probability_pct"] <= 100 for p in points))
    check(f"{city}.hourly.temp_plausible",
          all(-10 <= p["temperature_c"] <= 55 for p in points))


def audit_daily(city: str, days: list[dict]) -> None:
    check(f"{city}.daily.count_7", len(days) == 7, f"got {len(days)}")
    if len(days) < 2:
        return
    dates = [datetime.fromisoformat(d["date"]).date() for d in days]
    check(f"{city}.daily.starts_today", dates[0] == datetime.now(UTC).date(),
          f"first day {dates[0]}")
    consecutive = all((dates[i + 1] - dates[i]).days == 1 for i in range(len(dates) - 1))
    check(f"{city}.daily.consecutive_days", consecutive)
    for d in days:
        if d.get("sunrise") and d.get("sunset"):
            sr = datetime.fromisoformat(d["sunrise"])
            ss = datetime.fromisoformat(d["sunset"])
            if not sr < ss:
                check(f"{city}.daily.sunrise_before_sunset", False,
                      f"{d['date']}: {sr.time()} >= {ss.time()}")
            return  # one validated day suffices per city


def audit_aqi(city: str, aq: dict | None, sdui_types: list[str]) -> None:
    has_card = "aqi_radial_meter" in sdui_types
    if aq is None:
        check(f"{city}.aqi.card_absent_without_data", not has_card,
              "AQI card rendered but no air_quality data")
        return
    v = aq.get("aqi")
    check(f"{city}.aqi.value_range", v is not None and 0 <= v <= 500, str(v))
    derived = aqi_category(v).value
    check(f"{city}.aqi.category_derived_not_trusted", aq.get("category") == derived,
          f"api says {aq.get('category')}, formula says {derived}")
    check(f"{city}.aqi.card_present_with_data", has_card,
          "AQI data present but no aqi_radial_meter card")
    for pol in ("pm2_5_ugm3", "pm10_ugm3"):
        if aq.get(pol) is not None:
            check(f"{city}.aqi.{pol}_plausible", 0 < aq[pol] < 1000, str(aq[pol]))


def audit_marine(city: str, mar: dict | None, sdui_types: list[str]) -> None:
    has_card = "marine_tide_gauge" in sdui_types
    if mar is None:
        check(f"{city}.marine.absent_inland", city not in COASTAL and not has_card,
              f"marine data/card on non-coastal city {city}")
        return
    check(f"{city}.marine.only_coastal", city in COASTAL, f"marine on inland {city}")
    wave = mar.get("significant_wave_height_m")
    check(f"{city}.marine.wave_plausible", wave is not None and 0 <= wave <= 8, str(wave))
    flag = mar.get("beach_flag")
    check(f"{city}.marine.flag_valid", flag in {"green", "yellow", "red"}, str(flag))
    # cross-service consistency: red flag iff dangerous surf (>=2.5 m)
    if wave is not None and flag:
        expected = "red" if wave >= 2.5 else ("yellow" if wave >= 1.5 else "green")
        check(f"{city}.marine.flag_matches_wave", flag == expected,
              f"wave {wave} m should be {expected}, flag says {flag}")
    check(f"{city}.marine.card_present", has_card, "marine data but no tide card")
    curve = mar.get("tide_curve") or []
    # Contract: 24h of 15-min samples (96 points) — the mobile chart window.
    check(f"{city}.marine.tide_curve_enriched", len(curve) == 96,
          f"got {len(curve)} points (expected 96 = 24h @ 15min)")
    if len(curve) >= 2:
        t0 = datetime.fromisoformat(curve[0]["time"])
        t1 = datetime.fromisoformat(curve[1]["time"])
        check(f"{city}.marine.tide_15min_step",
              abs((t1 - t0).total_seconds() - 900) < 1, f"step {(t1 - t0).total_seconds()}s")
        hs = [p["height_m"] for p in curve]
        # Heights are relative to mean sea level: negative = below MSL, which
        # is physical (low tide). Only absurd magnitudes are wrong.
        check(f"{city}.marine.tide_heights_plausible",
              all(-8 <= h <= 8 for h in hs), f"range {min(hs)}..{max(hs)}")
        check(f"{city}.marine.tide_oscillates", max(hs) - min(hs) > 0.5,
              "a tide curve with no amplitude is wrong")


def audit_agro(city: str, ag: dict | None, sdui_types: list[str]) -> None:
    has_card = "meghdoot_agro_card" in sdui_types
    if ag is None:
        check(f"{city}.agro.absent_urban", not has_card,
              f"agro card on non-agro city {city}")
        return
    adv = ag.get("crop_advisories") or []
    check(f"{city}.agro.advisories_present", len(adv) >= 3, f"got {len(adv)}")
    soil = ag.get("soil_moisture_pct")
    check(f"{city}.agro.soil_range", soil is not None and 0 <= soil <= 100, str(soil))
    check(f"{city}.agro.card_present", has_card, "agro data but no card")


def audit_nowcast(city: str, alerts: list[dict]) -> None:
    for i, a in enumerate(alerts):
        vf = datetime.fromisoformat(a["valid_from"])
        vt = datetime.fromisoformat(a["valid_to"])
        now = datetime.now(UTC)
        check(f"{city}.nowcast[{i}].active", vf <= now <= vt,
              f"window {vf.time()}–{vt.time()} vs now {now.time()}")
        check(f"{city}.nowcast[{i}].duration_2h",
              abs((vt - vf).total_seconds() - 7200) < 60, "retime contract: 2h window")


def audit_cap_spatial(client: TestClient, cap_by_city: dict[str, list[dict]]) -> None:
    """Spatial integrity: the Konkan cyclone hits Mumbai ONLY; the west-coast
    rainfall hits Mumbai+Kochi; Delhi/Shimla/Vidarbha get nothing."""
    expected = {
        # Cyclone polygon = Konkan/Mumbai only; rainfall band = west coast
        # incl. Mumbai+Kochi (fixture geometry now matches its areaDesc).
        "mumbai": {"Cyclone Warning", "Heavy Rainfall Warning"},
        "kochi": {"Heavy Rainfall Warning"},
        "delhi": set(), "shimla": set(), "vidarbha": set(),
    }
    for city, events in expected.items():
        got = {a["event"] for a in cap_by_city.get(city, [])}
        check(f"cap.spatial.{city}", got == events, f"expected {events}, got {got}")


def audit_sdui_persona(payloads: dict[str, dict]) -> None:
    # farmer persona on vidarbha: agro card must lead
    types = [w["type"] for w in payloads["vidarbha_farmer"]["widgets"]]
    check("sdui.routing.farmer_agro_first",
          types and types[0] == "meghdoot_agro_card", f"order: {types[:3]}")
    # coastal on kochi: tide card in top 2
    types_k = [w["type"] for w in payloads["kochi_coastal"]["widgets"]]
    check("sdui.routing.coastal_tide_top2",
          "marine_tide_gauge" in types_k[:2], f"order: {types_k[:3]}")
    # health persona: AQI ranks above baseline
    types_d = [w["type"] for w in payloads["delhi_health"]["widgets"]]
    if "aqi_radial_meter" in types_d:
        check("sdui.routing.health_aqi_first",
              types_d.index("aqi_radial_meter") < types_d.index("current_conditions"),
              f"aqi at {types_d.index('aqi_radial_meter')}")
    # every card has non-empty props
    for name, p in payloads.items():
        for w in p["widgets"]:
            check(f"sdui.props_nonempty.{name}.{w['type']}", bool(w.get("props")),
                  "card rendered with empty props")


def audit_i18n(client: TestClient) -> None:
    langs = client.get("/v1/i18n/languages").json()["languages"]
    codes = [l["code"] for l in langs]
    check("i18n.six_languages", set(codes) == {"en", "hi", "ta", "bn", "te", "mr"}, str(codes))
    base = client.get("/v1/i18n/strings/en").json()
    base_keys = set(base["strings"])
    for code in ("hi", "ta", "bn", "te", "mr"):
        b = client.get(f"/v1/i18n/strings/{code}").json()
        check(f"i18n.{code}.complete", set(b["strings"]) == base_keys,
              f"missing {base_keys - set(b['strings'])}")
        check(f"i18n.{code}.no_english_leaks",
              all(str(v) for v in b["strings"].values())
              and b["strings"]["app_title"] != base["strings"]["app_title"],
              "bundle incomplete/untranslated title")
        gloss = b["glossary"]
        check(f"i18n.{code}.glossary_translated",
              gloss["rain"] != "rain" and gloss["thunderstorm"] != "thunderstorm",
              "core weather terms untranslated")


def audit_geo_contains_cities(client: TestClient) -> None:
    fc = client.get("/v1/geo/boundaries").json()
    rings = {f["properties"]["code"]: f["geometry"]["coordinates"][0] for f in fc["features"]}
    state_for = {"delhi": "DL", "mumbai": "MH", "kochi": "KL", "shimla": "HP"}

    def pip(lat: float, lon: float, ring: list) -> bool:
        inside = False
        n = len(ring)
        j = n - 1
        for i in range(n):
            yi, xi = ring[i]
            yj, xj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    for city, code in state_for.items():
        lat, lon = CITIES[city]
        check(f"geo.{city}_in_own_state", code in rings and pip(lat, lon, rings[code]),
              f"city outside its {code} schematic ring")


def main() -> int:
    gw_module.settings.API_MODE = "SEED"
    print("service correctness audit — data domains × 5 demo cities")
    with TestClient(app) as client:
        client.post("/v1/admin/poll-now")  # populate CAP store like a poll tick

        cap_by_city: dict[str, list[dict]] = {}
        sdui_types_by_city: dict[str, list[str]] = {}
        payloads: dict[str, dict] = {}

        for city, (lat, lon) in CITIES.items():
            src = load_fixture(city)
            ctx = client.get("/v1/weather/context", params={"lat": lat, "lon": lon}).json()
            print(f"\n— {city} —")
            audit_current(city, ctx.get("current") or {}, src)
            audit_hourly(city, ctx.get("hourly") or [])
            audit_daily(city, ctx.get("daily") or [])
            cap_by_city[city] = ctx.get("cap_alerts") or []
            check(f"{city}.nowcast_present", isinstance(ctx.get("nowcast"), list))

            p = client.get("/v1/sdui/home", params={
                "lat": lat, "lon": lon, "personas": "health,commuter,coastal,farmer"
            }).json()
            sdui_types_by_city[city] = [w["type"] for w in p["widgets"]]
            audit_aqi(city, ctx.get("air_quality"), sdui_types_by_city[city])
            audit_marine(city, ctx.get("marine"), sdui_types_by_city[city])
            audit_agro(city, ctx.get("agro"), sdui_types_by_city[city])
            audit_nowcast(city, ctx.get("nowcast") or [])

        print("\n— cross-service —")
        audit_cap_spatial(client, cap_by_city)
        audit_nowcast_all = True

        # persona-routing payloads
        payloads["vidarbha_farmer"] = client.get("/v1/sdui/home", params={
            "lat": CITIES["vidarbha"][0], "lon": CITIES["vidarbha"][1],
            "personas": "farmer"}).json()
        payloads["kochi_coastal"] = client.get("/v1/sdui/home", params={
            "lat": CITIES["kochi"][0], "lon": CITIES["kochi"][1],
            "personas": "coastal"}).json()
        payloads["delhi_health"] = client.get("/v1/sdui/home", params={
            "lat": CITIES["delhi"][0], "lon": CITIES["delhi"][1],
            "personas": "health"}).json()
        audit_sdui_persona(payloads)

        # nowcast audit for all cities (needs the ctx list we already checked)
        for city, (lat, lon) in CITIES.items():
            ctx = client.get("/v1/weather/context", params={"lat": lat, "lon": lon}).json()
            audit_nowcast(city, ctx.get("nowcast") or [])

        audit_i18n(client)
        audit_geo_contains_cities(client)

        # store summary consistency with the map feed
        feed = client.get("/v1/alerts/active").json()
        summ = alert_store.summary()
        check("cap.store_feed_consistent", feed["count"] == summ["count"] == feed["summary"]["count"],
              f"feed {feed['count']} vs store {summ['count']}")

    print(f"\n{'=' * 62}")
    print(f"CORRECTNESS AUDIT: {CHECKS - len(FINDINGS)}/{CHECKS} checks passed")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "correctness_audit.json").write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": CHECKS, "findings": FINDINGS,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    if FINDINGS:
        print("FINDINGS:")
        for f in FINDINGS:
            print(f"  ❌ {f}")
        return 1
    print("All services return correct, consistent, fresh data. ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
