"""Unified WeatherContext endpoint (fixture-backed in Phase 0).

Phase 1 will insert the real federation gateway between the router and
this service; the contract stays frozen from day one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import coarse_location
from app.models.weather import (
    AirQualityIndex,
    CurrentWeather,
    DailyForecast,
    GeoLocation,
    HourlyForecastPoint,
    WeatherCondition,
    WeatherContext,
)
from app.services.gateway import gateway

router = APIRouter(prefix="/v1/weather", tags=["weather"])


@router.get("/context", response_model=WeatherContext)
async def weather_context(coords: tuple[float, float] = Depends(coarse_location)) -> WeatherContext:
    lat, lon = coords
    return await gateway.get_weather_context(lat, lon)


# --- narrow re-exports so tests (and the SDUI composer) have stable handles --- #

__all__ = [
    "AirQualityIndex",
    "CurrentWeather",
    "DailyForecast",
    "GeoLocation",
    "HourlyForecastPoint",
    "WeatherCondition",
    "WeatherContext",
    "router",
]
