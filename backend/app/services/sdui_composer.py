"""SDUIComposer (TASK-016) — WeatherContext → persona-ranked widget nodes.

Tier A deterministic engine:
    score = 0.6 * persona_affinity + 0.4 * data_urgency

Widgets without data are skipped (no marine data → no tide card). Safety
widgets (disaster lifeline, active commute warnings) pin to the top — rules
veto rankings. Output validates against contracts/sdui_v1.schema.json and
must fit the Brotli budget; on overflow the lowest-priority cards are
dropped first (current_conditions and pinned cards never drop).

Phase 5 swaps the scoring function for LinUCB; nothing else changes.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.adapters.mosdac import fog_index_from_visibility
from app.models.weather import WeatherCondition, WeatherContext
from app.services.personas import (
    AFFINITY_RANK_BONUS,
    PERSONA_BOOST,
    URGENCY_RULES,
    persona_affinity,
)

logger = logging.getLogger(__name__)

SDUI_VERSION = "v1"
MAX_WIDGETS = 8
BUDGET_BYTES = 15 * 1024  # <15 KB target (Brotli compresses well below this)

_WF = WeatherCondition


# --------------------------------------------------------------------------- #
# Prop builders — one per widget type; return props dict or None to skip
# --------------------------------------------------------------------------- #


def _props_current(ctx: WeatherContext) -> dict[str, Any] | None:
    c = ctx.current
    uv = c.uv_index
    uv_advice = None
    if uv is not None:
        if uv >= 8:
            uv_advice = "Very high UV — sunscreen & shade essential"
        elif uv >= 6:
            uv_advice = "High UV — sunscreen recommended"
        elif uv >= 3:
            uv_advice = "Moderate UV — cover up midday"
        else:
            uv_advice = "Low UV — safe exposure"
    return {
        "temperature_c": c.temperature_c,
        "feels_like_c": c.feels_like_c,
        "condition": c.condition.value,
        "condition_text": c.condition_text,
        "humidity_pct": c.humidity_pct,
        "wind_kmph": c.wind_kmph,
        "uv_index": uv,
        "uv_advice": uv_advice,
        "observed_at": _bucket(c.observed_at).isoformat(),
    }


def _bucket(dt: datetime) -> datetime:
    """Floor an ISO timestamp to the 5-min bucket for ETag stability."""
    from app.services.clock import BUCKET_SECONDS

    epoch = int(dt.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % BUCKET_SECONDS), tz=dt.tzinfo or UTC)


def _props_aqi(ctx: WeatherContext) -> dict[str, Any] | None:
    aq = ctx.air_quality
    if aq is None:
        return None
    advice = {
        "Good": "Air quality is good — ideal for outdoor activity.",
        "Satisfactory": "Minor breathing discomfort possible for sensitive people.",
        "Moderate": "Sensitive groups should limit prolonged outdoor exertion.",
        "Poor": "Wear a mask outdoors; reduce strenuous activity.",
        "Very Poor": "Avoid outdoor exertion; run air purifiers indoors.",
        "Severe": "Stay indoors. Health emergency levels — masks mandatory outdoors.",
    }.get(aq.category.value, "")
    return {
        "aqi": aq.aqi,
        "category": aq.category.value,
        "dominating_pollutant": aq.dominating_pollutant,
        "pm2_5_ugm3": aq.pm2_5_ugm3,
        "pm10_ugm3": aq.pm10_ugm3,
        "advice": advice,
    }


def _props_running(ctx: WeatherContext) -> dict[str, Any] | None:
    """Best running hours: T ≤ 30°C, RH ≤ 85%, wind < 20 km/h (TASK-032 rule)."""
    windows: list[dict[str, Any]] = []
    run_start: int | None = None
    temps: list[float] = []

    def close(end_hour: int) -> None:
        nonlocal run_start, temps
        if run_start is not None:
            avg = sum(temps) / len(temps) if temps else None
            windows.append(
                {
                    "start_hour": run_start,
                    "end_hour": end_hour,
                    "avg_temp_c": round(avg, 1) if avg is not None else None,
                    "rating": "optimal" if avg is not None and avg < 27 else "good",
                }
            )
        run_start = None
        temps = []

    for point in ctx.hourly:
        ok = (
            point.temperature_c <= 30
            and point.humidity_pct <= 85
            and point.wind_kmph < 20
            and point.precipitation_probability_pct < 40
        )
        if ok:
            if run_start is None:
                run_start = point.time.hour
            temps.append(point.temperature_c)
        else:
            close(point.time.hour)
    close(24)

    return {"windows": windows[:4]} if windows else None


def _props_marine(ctx: WeatherContext) -> dict[str, Any] | None:
    m = ctx.marine
    if m is None:
        return None
    swell_p = m.swell_period_s or 0.0
    wave = m.significant_wave_height_m
    surf_ok = swell_p > 10 and (wave is not None and 1.0 <= wave <= 2.5)
    flag_note = {
        "green": "Calm conditions — normal beach activity.",
        "yellow": "Caution — moderate surf; stay near shore.",
        "red": "Danger — sea state unsafe. No water activity.",
    }.get(m.beach_flag or "", "")
    # Hourly subsample of the tide curve keeps the payload small.
    curve = [{"time": p.time.isoformat(), "height_m": p.height_m} for p in m.tide_curve[::4]]
    return {
        "wave_height_m": wave,
        "swell_period_s": m.swell_period_s,
        "sst_c": m.sst_c,
        "tide_state": m.tide_state,
        "next_high_tide": m.next_high_tide.isoformat() if m.next_high_tide else None,
        "next_low_tide": m.next_low_tide.isoformat() if m.next_low_tide else None,
        "beach_flag": m.beach_flag,
        "beach_note": flag_note,
        "surf_ok": surf_ok,
        "tide_curve": curve,
    }


def _props_packing(ctx: WeatherContext) -> dict[str, Any] | None:
    """Rule-based packing engine (TASK-034): rain, ΔT, heat, cold."""
    if not ctx.daily:
        return None
    items: list[str] = []
    rain = max(d.precipitation_probability_pct for d in ctx.daily[:3])
    if rain >= 50:
        items.append("Raincoat / umbrella")
    if rain >= 30:
        items.append("Waterproof footwear")
    t_max = max(d.temp_max_c for d in ctx.daily[:3])
    t_min = min(d.temp_min_c for d in ctx.daily[:3])
    if t_max - t_min > 15:
        items.append("Layered clothing")
    if t_max >= 35:
        items.append("Sunscreen & hydration")
    if t_min <= 10:
        items.append("Warm layers / jacket")
    days = [
        {
            "date": d.date.date().isoformat(),
            "temp_max_c": d.temp_max_c,
            "temp_min_c": d.temp_min_c,
            "condition": d.condition.value,
            "rain_pct": d.precipitation_probability_pct,
        }
        for d in ctx.daily[:3]
    ]
    return {"packing": items, "days": days}


def _props_commute(ctx: WeatherContext) -> dict[str, Any] | None:
    """School/office commute banner (TASK-035): storm near 07–09 or 14–16."""
    windows = ((7, 9), (14, 16))
    rain_hour: int | None = None
    storm = False
    for point in ctx.hourly:
        if point.condition in (_WF.RAIN, _WF.THUNDERSTORM, _WF.DRIZZLE):
            if any(s <= point.time.hour < e for s, e in windows):
                if rain_hour is None:
                    rain_hour = point.time.hour
                storm = storm or point.condition is _WF.THUNDERSTORM
    if rain_hour is None:
        return None
    label = "Thunderstorm risk" if storm else "Rain expected"
    message = (
        f"{label} around {rain_hour:02d}:00 during commute hours — carry rain gear and allow extra travel time."
    )
    return {
        "alert_level": "storm" if storm else "rain",
        "message": message,
        "rain_start_hour": rain_hour,
        "estimated_delay_min": 15 if storm else 10,
    }


def _props_agro(ctx: WeatherContext) -> dict[str, Any] | None:
    a = ctx.agro
    if a is None:
        return None
    return {
        "block_name": a.block_name,
        "amfu_name": a.amfu_name,
        "advisories": a.crop_advisories,
        "soil_moisture_pct": a.soil_moisture_pct,
        "frost_risk": a.frost_risk,
        "issued_on": a.issued_on.isoformat() if a.issued_on else None,
    }


def _props_visibility(ctx: WeatherContext) -> dict[str, Any] | None:
    vis = ctx.current.visibility_m
    if vis is None:
        return None
    idx = fog_index_from_visibility(vis)
    if vis >= 4000:
        note = "Clear visibility — normal travel."
    elif vis >= 1000:
        note = "Light haze — no significant delay expected."
    elif vis >= 500:
        note = "Moderate fog — allow extra travel time."
    else:
        note = "Dense fog — major delays likely; drive with fog lamps."
    return {
        "visibility_m": vis,
        "fog_index": round(idx, 2),
        "note": note,
    }


def _props_event(ctx: WeatherContext) -> dict[str, Any] | None:
    """10-day color-coded suitability (TASK-038): composite comfort score."""
    if not ctx.daily:
        return None
    days = []
    for d in ctx.daily[:10]:
        # comfort: start at 100, subtract rain/heat/cold penalties
        score = 100
        score -= int(d.precipitation_probability_pct * 0.7)
        if d.temp_max_c >= 38:
            score -= 25
        elif d.temp_max_c >= 35:
            score -= 12
        if d.temp_min_c <= 5:
            score -= 20
        if d.condition is _WF.THUNDERSTORM:
            score -= 20
        score = max(0, min(100, score))
        suitability = (
            "excellent" if score >= 75
            else "good" if score >= 55
            else "fair" if score >= 35
            else "poor"
        )
        days.append(
            {
                "date": d.date.date().isoformat(),
                "score": score,
                "suitability": suitability,
                "condition": d.condition.value,
                "rain_pct": d.precipitation_probability_pct,
            }
        )
    return {"days": days}


def _props_disaster(ctx: WeatherContext) -> dict[str, Any] | None:
    if not ctx.cap_alerts:
        return None
    worst = max(ctx.cap_alerts, key=lambda a: {"Extreme": 4, "Severe": 3, "Moderate": 2, "Minor": 1, "Unknown": 0}.get(a.severity.value, 0))
    return {
        "event": worst.event or worst.message,
        "severity": worst.severity.value,
        "headline": worst.message,
        "instruction": worst.description,
        "area_desc": worst.area_desc,
        "expires": worst.valid_to.isoformat(),
        # Bundled NDMA public-safety steps for cyclone/flood class events.
        "safety_steps": [
            "Charge phones and power banks; keep a torch handy.",
            "Store at least 3 days of drinking water and dry food.",
            "Keep documents in a waterproof bag.",
            "Follow official evacuation routes to the nearest shelter.",
            "Stay away from the coast until the all-clear is issued.",
        ],
        "emergency_numbers": [
            {"label": "National Emergency", "number": "112"},
            {"label": "NDMA Helpline", "number": "1078"},
        ],
    }


def _props_ranks(ranks: list[dict[str, Any]]) -> dict[str, Any] | None:
    return {"ranks": ranks}


PROP_BUILDERS = {
    "current_conditions": _props_current,
    "aqi_radial_meter": _props_aqi,
    "running_window_timeline": _props_running,
    "marine_tide_gauge": _props_marine,
    "travel_packing_carousel": _props_packing,
    "commute_safety_banner": _props_commute,
    "meghdoot_agro_card": _props_agro,
    "visibility_meter": _props_visibility,
    "event_planner_calendar": _props_event,
    "disaster_lifeline_card": _props_disaster,
}

# Widgets pinned to the top when their urgency crosses the threshold.
PIN_RULES = {
    "disaster_lifeline_card": 90.0,   # any Severe+ CAP alert
    "commute_safety_banner": 80.0,    # active commute-window storm
}

NEVER_DROP = {"current_conditions"}


# --------------------------------------------------------------------------- #
# Composer
# --------------------------------------------------------------------------- #


def summarize_city(ctx: WeatherContext) -> dict[str, Any]:
    """Slim per-city summary for the multi-city travel carousel (TASK-034)."""
    d0 = ctx.daily[0] if ctx.daily else None
    return {
        "name": ctx.location.display_name,
        "lat": ctx.location.lat,
        "lon": ctx.location.lon,
        "temp_max_c": d0.temp_max_c if d0 else ctx.current.temperature_c,
        "temp_min_c": d0.temp_min_c if d0 else ctx.current.temperature_c,
        "condition": (d0.condition if d0 else ctx.current.condition).value,
        "rain_pct": d0.precipitation_probability_pct if d0 else 0,
    }


def _props_multi_city(
    home: dict[str, Any], extras: list[dict[str, Any]]
) -> dict[str, Any] | None:
    cities = [home, *extras][:6]
    if len(cities) < 2:
        return None
    return {"cities": cities, "is_favorite_flags": [False] * len(cities)}


def compose_sdui(
    ctx: WeatherContext,
    active_personas: list[str],
    extra_city_summaries: list[dict[str, Any]] | None = None,
    engine: str = "tier_a",
    bandit_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the SDUI homepage payload for a context + persona set.

    `extra_city_summaries` (from the router) enables the multi-city travel
    carousel when the client requests additional cities.

    `engine` selects the ranking policy (TASK-047 A/B toggle):
      "tier_a" — deterministic 0.6·affinity + 0.4·urgency (control)
      "bandit" — LinUCB UCB ordering with safety pinning (experiment)
    When `bandit_diagnostics` is a dict, the bandit branch fills it with the
    Algorithm Inspector payload (context vector, per-arm scores, timings).
    """
    personas = [p for p in active_personas if p] or ["health", "commuter"]
    extra_city_summaries = extra_city_summaries or []

    # Feasibility pass (shared): widgets without data are never candidates.
    feasible: list[dict[str, Any]] = []
    for wtype, builder in PROP_BUILDERS.items():
        props = builder(ctx)
        if props is None:
            continue
        urgency_fn = URGENCY_RULES.get(wtype)
        urgency = urgency_fn(ctx) if callable(urgency_fn) else None
        affinity = persona_affinity(wtype, personas)
        if wtype == "current_conditions":
            affinity = 50.0  # universal baseline
        feasible.append(
            {
                "id": wtype,
                "type": wtype,
                "props": props,
                "urgency": urgency,
                "affinity": affinity,
            }
        )

    candidates: list[dict[str, Any]]
    engine_name = "tier_a_deterministic_v1"

    if engine == "bandit":
        candidates, engine_name = _bandit_candidates(
            ctx, personas, feasible, bandit_diagnostics
        )
    else:
        candidates = _tier_a_candidates(feasible)

    # Multi-city travel carousel — only when the client requested extras.
    if extra_city_summaries:
        multi_props = _props_multi_city(summarize_city(ctx), extra_city_summaries)
        if multi_props is not None:
            affinity = persona_affinity("travel_multi_city_carousel", personas)
            multi_score = 0.6 * affinity + 0.4 * 45
            candidates.append(
                {
                    "id": "travel_multi_city_carousel",
                    "type": "travel_multi_city_carousel",
                    "props": multi_props,
                    "priority": int(round(multi_score)),
                    "_score": multi_score,
                    "_pinned": False,
                }
            )

    # Diagnostics row — Phase 5's Algorithm Inspector reads this shape.
    candidates.append(
        {
            "id": "persona_rank_row",
            "type": "persona_rank_row",
            "props": _props_ranks(
                [{"persona": p, "note": engine_name} for p in personas]
            ),
            "priority": 5,
            "_score": 5.0,
            "_pinned": False,
        }
    )

    if engine != "bandit":
        # Tier A: pinned first (by urgency), then score desc. The bandit
        # branch produced its order already — sorting would erase it.
        candidates.sort(key=lambda c: (c["_pinned"], c["_score"]), reverse=True)

    # Budget enforcement: drop lowest-priority, non-pinned cards on overflow.
    def payload_size(widgets: list[dict[str, Any]]) -> int:
        return len(json.dumps(_payload(ctx, personas, widgets), separators=(",", ":")))

    kept = candidates[:MAX_WIDGETS]
    while payload_size(kept) > BUDGET_BYTES and len(kept) > 1:
        for i in range(len(kept) - 1, -1, -1):
            if kept[i]["type"] not in NEVER_DROP and not kept[i]["_pinned"]:
                del kept[i]
                break
        else:
            break

    for w in kept:
        w.pop("_score", None)
        w.pop("_pinned", None)

    payload = _payload(ctx, personas, kept, engine_name, bandit_diagnostics)
    return payload


def _tier_a_candidates(feasible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic scoring (unchanged Tier A behavior)."""
    candidates: list[dict[str, Any]] = []
    for f in feasible:
        urgency = f["urgency"]
        data_score = urgency if urgency is not None else 30.0
        score = 0.6 * f["affinity"] + 0.4 * data_score
        pinned = urgency is not None and urgency >= PIN_RULES.get(f["type"], 101.0)
        if pinned:
            score = max(score, PIN_RULES[f["type"]] + 1.0)
        candidates.append(
            {
                "id": f["id"],
                "type": f["type"],
                "props": f["props"],
                "priority": int(round(max(0.0, min(100.0, score)))),
                "_score": score,
                "_pinned": pinned,
            }
        )
    return candidates


def _bandit_candidates(
    ctx: WeatherContext,
    personas: list[str],
    feasible: list[dict[str, Any]],
    bandit_diagnostics: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    """LinUCB ordering (TASK-041/042). Safety pinning still vetoes: rules
    decide IF a card pins, the bandit only orders everything else."""
    from app.services.bandit_ranker import BANDIT_ARMS, BanditRanker

    # Hero card: universal baseline leads the feed (bandit never demotes it;
    # safety pinning inserts between hero and the ranked arms).
    hero = next((f for f in feasible if f["type"] == "current_conditions"), None)
    pinned_records = [
        f for f in feasible
        if f["urgency"] is not None
        and f["urgency"] >= PIN_RULES.get(f["type"], 101.0)
    ]
    pinned_records.sort(key=lambda f: f["urgency"], reverse=True)
    ranked_pool = [
        f for f in feasible
        if f["type"] in BANDIT_ARMS
        and (f["urgency"] is None or f["urgency"] < PIN_RULES.get(f["type"], 101.0))
    ]

    ordered_candidates: list[dict[str, Any]] = []
    # Safety pins lead (Tier A parity: red alert above current weather),
    # then the universal hero card, then the bandit-ranked arms.
    for f in pinned_records:
        score = PIN_RULES[f["type"]] + 1.0
        ordered_candidates.append(
            {
                "id": f["id"],
                "type": f["type"],
                "props": f["props"],
                "priority": int(round(min(100.0, score))),
                "_score": score,
                "_pinned": True,
            }
        )
    if hero is not None:
        score = 0.6 * hero["affinity"] + 0.4 * (hero["urgency"] or 30.0)
        ordered_candidates.append(
            {
                "id": hero["id"],
                "type": hero["type"],
                "props": hero["props"],
                "priority": int(round(max(0.0, min(100.0, score)))),
                "_score": score,
                "_pinned": False,
            }
        )

    if ranked_pool:
        ranker = BanditRanker.instance()
        order, diags = ranker.rank(
            ctx, personas, [f["type"] for f in ranked_pool]
        )
        if bandit_diagnostics is not None:
            bandit_diagnostics.clear()
            bandit_diagnostics.update(diags)
        pos = {arm: i for i, arm in enumerate(order)}
        ranked_pool.sort(key=lambda f: pos.get(f["type"], len(order)))
        for i, f in enumerate(ranked_pool):
            # Priority mirrors rank position so clients see a stable ordering
            # signal (payload schema still caps priority at 100).
            slot = max(0, min(100, 90 - 10 * i))
            ordered_candidates.append(
                {
                    "id": f["id"],
                    "type": f["type"],
                    "props": f["props"],
                    "priority": slot,
                    "_score": 100.0 - i,
                    "_pinned": False,
                }
            )

    return ordered_candidates, "linucb_v1"


def _payload(
    ctx: WeatherContext,
    personas: list[str],
    widgets: list[dict[str, Any]],
    engine_name: str = "tier_a_deterministic_v1",
    bandit_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    personas_block: dict[str, Any] = {
        "active": personas,
        "engine": engine_name,
    }
    if engine_name == "linucb_v1" and bandit_diagnostics:
        # Compact inspector summary travels with every bandit-ranked page;
        # the full breakdown lives at /v1/debug/bandit/last (TASK-045).
        personas_block["bandit"] = {
            "best_arm": bandit_diagnostics.get("best_arm"),
            "alpha": bandit_diagnostics.get("alpha"),
            "x": [
                round(v, 3) for v in (bandit_diagnostics.get("x") or [])
            ],
        }
    return {
        "schema_version": SDUI_VERSION,
        "location": {
            "display_name": ctx.location.display_name,
            "district": ctx.location.district,
            "state": ctx.location.state,
            "lat": ctx.location.lat,
            "lon": ctx.location.lon,
        },
        "personas": personas_block,
        "sources_used": ctx.sources_used,
        "stale": ctx.stale,
        "widgets": widgets,
    }
