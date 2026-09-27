"""SDUI homepage endpoint (TASK-016/022).

GET /v1/sdui/home?lat=&lon=&personas=health,commuter
    - Composes persona-ranked widget nodes from the weather context.
    - ETag/If-None-Match → 304 (saves battery on mobile pull-to-refresh).
    - Content-Encoding: br when the client sends Accept-Encoding: br.
    - X-SDUI-Widget-Count and X-SDUI-Size-Bytes diagnostics headers.
"""

from __future__ import annotations

import asyncio
import brotli
import hashlib
import json
import logging
import time

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse

from app.dependencies import coarse_location
from app.models.weather import WeatherContext
from app.services import gateway
from app.services.sdui_composer import compose_sdui, summarize_city

router = APIRouter(prefix="/v1/sdui", tags=["sdui"])
logger = logging.getLogger(__name__)

# Last bandit diagnostics (Algorithm Inspector reads this; TASK-045).
_last_bandit_diagnostics: dict | None = None


@router.get("/home")
async def sdui_home(
    coords: tuple[float, float] = Depends(coarse_location),
    personas: str = Query(
        default="health,commuter",
        description="Comma-separated persona keys (see services/personas.py)",
    ),
    cities: str = Query(
        default="",
        description="Optional comma-separated 'lat,lon' pairs for the multi-city carousel (max 5)",
    ),
    engine: str = Query(
        default="tier_a",
        pattern="^(tier_a|bandit)$",
        description="Ranking engine: tier_a (heuristic control) or bandit (LinUCB experiment)",
    ),
    if_none_match: str | None = Header(default=None),
    accept_encoding: str | None = Header(default=None),
) -> Response:
    lat, lon = coords
    persona_list = [p.strip() for p in personas.split(",") if p.strip()]

    # Multi-city carousel support (TASK-034): resolve extra cities in
    # parallel; failures simply drop that city from the carousel.
    extra_summaries: list[dict] = []
    city_pairs: list[tuple[float, float]] = []
    for chunk in cities.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 2:
            continue
        try:
            city_pairs.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    city_pairs = city_pairs[:5]
    if city_pairs:
        contexts = await asyncio.gather(
            *(gateway.gateway.get_weather_context(clat, clon) for clat, clon in city_pairs),
            return_exceptions=True,
        )
        extra_summaries = [
            summarize_city(c) for c in contexts if isinstance(c, WeatherContext)
        ]

    ctx = await gateway.gateway.get_weather_context(lat, lon)

    # Phase 5: LinUCB ranking branch (TASK-041/047). Diagnostics are captured
    # per request so the Algorithm Inspector can show the live math.
    bandit_diagnostics: dict = {}
    payload = compose_sdui(
        ctx,
        persona_list,
        extra_city_summaries=extra_summaries,
        engine=engine,
        bandit_diagnostics=bandit_diagnostics,
    )

    if engine == "bandit":
        global _last_bandit_diagnostics
        from app.services.bandit_ranker import BanditRanker
        import numpy as np

        ranker = BanditRanker.instance()
        # Serve-time impression update for every ranked (non-pinned) bandit arm.
        x = np.asarray(bandit_diagnostics.get("x") or [], dtype=float)
        if x.size:
            for w in payload.get("widgets", []):
                if w["type"] in ranker.model.arms:
                    ranker.record_impression(w["type"], x)
        bandit_diagnostics["captured_at"] = time.time()
        _last_bandit_diagnostics = bandit_diagnostics

    body = json.dumps(payload, separators=(",", ":"), sort_keys=False)
    etag = '"' + hashlib.sha1(body.encode()).hexdigest()[:16] + '"'

    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=300, stale-while-revalidate=1800",
        "X-SDUI-Widget-Count": str(len(payload.get("widgets", []))),
        "X-SDUI-Size-Bytes": str(len(body.encode())),
    }

    if if_none_match == etag:
        return Response(status_code=304, headers=headers)

    content_bytes = body.encode("utf-8")
    if accept_encoding and "br" in accept_encoding.lower():
        compressed = brotli.compress(content_bytes)
        if len(compressed) < len(content_bytes):
            headers["Content-Encoding"] = "br"
            headers["X-SDUI-Brotli-Bytes"] = str(len(compressed))
            content_bytes = compressed

    return Response(
        content=content_bytes,
        media_type="application/json",
        headers=headers,
    )
