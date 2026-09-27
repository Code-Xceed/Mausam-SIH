"""WeatherGateway v2 — live-first federation with fixture replay (Phase 1).

Flow per request:
    1. Snap (lat, lon) to nearest demo city (cities.py).
    2. Cache check (per-piece TTLs; graceful no-op without Redis).
    3. Load that city's fixture as the coherent base context (retimed to now).
    4. If API_MODE != SEED: run live adapters through the HybridCircuitBreaker
       and merge live IMD current / CPCB AQI / CAP alerts over the fixture.
    5. Marine fixtures get a live-computed synthetic tide state.

Every merged piece is tagged `sources_used` and `stale` so the client and the
pitch can always show exactly what is live vs replayed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.adapters.base import HybridCircuitBreaker
from app.adapters.cpcb import CpcbAdapter
from app.adapters.gkms import GkmsAdapter
from app.adapters.imd import ImdAdapter
from app.adapters.incois import IncoisAdapter, enrich_marine_fixture
from app.adapters.mosdac import MosdacAdapter
from app.core.cache import cache
from app.core.config import settings
from app.models.weather import WeatherContext
from app.services.cities import City, nearest_city
from app.services.fixtures import load_fixture, retime_fixture

logger = logging.getLogger(__name__)


class WeatherGateway:
    """Single facade the routers talk to. Mode switch lives here, nowhere else."""

    def __init__(self) -> None:
        self._imd = ImdAdapter()
        self._cpcb = CpcbAdapter()
        self._incois = IncoisAdapter()
        self._mosdac = MosdacAdapter()
        self._gkms = GkmsAdapter()
        self._cap = None  # created lazily; CAP fetch is cheap and stateless
        self._breaker = HybridCircuitBreaker(
            failure_threshold=settings.ADAPTER_FAILURE_THRESHOLD,
            reset_time_s=settings.ADAPTER_RESET_TIME_S,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def get_weather_context(self, lat: float, lon: float) -> WeatherContext:
        city = nearest_city(lat, lon)
        geohash = f"{lat:.2f}_{lon:.2f}"
        cache_key = f"wx:ctx:{city.key}:{geohash}"

        cached = await cache.get_json(cache_key)
        if cached is not None:
            return WeatherContext.model_validate(cached)

        raw = self._city_fixture(city, lat, lon)
        sources = list(raw.get("sources_used") or [])

        # CAP alerts are ALWAYS merged — fixture feed in SEED, live-or-fixture
        # otherwise. The disaster demo must work with radios off.
        await self._merge_cap(raw, lat, lon, sources)

        if settings.API_MODE != "SEED":
            await self._merge_live(raw, city, lat, lon, sources)

        raw["sources_used"] = sources
        raw["stale"] = settings.API_MODE == "SEED"
        ctx = WeatherContext.model_validate(raw)

        # Cache briefly — live-ish data can change, fixtures don't need long TTLs
        # at all; 60s keeps repeat jury-taps fast without hiding live updates.
        await cache.set_json(cache_key, json.loads(ctx.model_dump_json()), ttl_s=60)
        return ctx

    # ------------------------------------------------------------------ #
    # Fixture base
    # ------------------------------------------------------------------ #

    def _city_fixture(self, city: City, lat: float, lon: float) -> dict[str, Any]:
        name = f"weather_context_{city.key}.json"
        raw = load_fixture(name)
        raw = retime_fixture(raw)
        # Tide state + curve are pure math (no network) — enrich in every mode
        # so the Phase 4 sine chart works even in full SEED/airplane demo.
        if raw.get("marine"):
            raw["marine"] = enrich_marine_fixture(raw["marine"])
        loc = raw.setdefault("location", {})
        loc["lat"] = lat
        loc["lon"] = lon
        loc.setdefault("display_name", city.name)
        loc.setdefault("district", city.name)
        loc.setdefault("state", city.state)
        return raw

    # ------------------------------------------------------------------ #
    # CAP alerts — always on (fixture feed is the SEED-mode source)
    # ------------------------------------------------------------------ #

    async def _merge_cap(
        self, raw: dict[str, Any], lat: float, lon: float, sources: list[str]
    ) -> None:
        try:
            from app.adapters.cap import cap_to_nowcast
            from app.services.alert_store import alert_store

            # Single source of truth: the alert store. The lifespan poller
            # (live feed or bundled fixture) is the ONLY intake — demo
            # injections land in the same store, so a staged drill surfaces
            # on affected cities' homes with zero special-casing. No alert
            # store (bare unit-test mounts without lifespan) ⇒ no alerts,
            # which keeps request-path tests hermetic by construction.
            alerts = alert_store.active_for_location(lat, lon)
            matched = [cap_to_nowcast(a) for a in alerts]
            raw["cap_alerts"] = matched
            if matched and "NDMA_CAP" not in sources:
                sources.append("NDMA_CAP")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[gateway] CAP merge skipped: %s", exc)

    # ------------------------------------------------------------------ #
    # Live merge — each piece independent; one failure never blocks the rest
    # ------------------------------------------------------------------ #

    async def _merge_live(
        self, raw: dict[str, Any], city: City, lat: float, lon: float, sources: list[str]
    ) -> None:
        breaker = self._breaker

        if settings.API_MODE == "LIVE" and not (
            settings.DATA_GOV_API_KEY or settings.INCOIS_OSF_URL or settings.CAP_FEED_URL
        ):
            # LIVE without any credentials configured: stay fixture-only and be loud.
            logger.warning("API_MODE=LIVE but no live endpoints configured — fixture-only")

        # --- IMD current weather --- #
        current_live, src = await breaker.call(
            lambda: self._imd.fetch_current(city.name, city.state),
            lambda: None,
            label="IMD",
        )
        if current_live and src == "live":
            raw["current"].update(current_live)
            if "IMD" not in sources:
                sources.append("IMD")

        # --- CPCB AQI --- #
        aqi_live, src = await breaker.call(
            lambda: self._cpcb.fetch_aqi(city.name, city.state),
            lambda: None,
            label="CPCB",
        )
        if aqi_live and src == "live":
            station = aqi_live.pop("station", None)
            raw["air_quality"] = aqi_live
            if station:
                raw["air_quality"]["station"] = station
            if "CPCB" not in sources:
                sources.append("CPCB")

        # --- INCOIS marine (only meaningful for marine cities) --- #
        if city.marine:
            marine_live, src = await breaker.call(
                lambda: self._incois.fetch_marine(lat, lon),
                lambda: None,
                label="INCOIS",
            )
            if marine_live and src == "live" and raw.get("marine"):
                raw["marine"].update(marine_live)
                raw["marine"] = enrich_marine_fixture(raw["marine"])
                if "INCOIS" not in sources:
                    sources.append("INCOIS")

        # MOSDAC/GKMS stubs: keep them referenced so Phase 4 wiring is trivial.
        _ = (self._mosdac, self._gkms)


gateway = WeatherGateway()
