"""Canonical weather data models (TASK-005).

These Pydantic v2 schemas normalize heterogeneous payloads from IMD, CPCB,
INCOIS, MOSDAC, GKMS, and NDMA CAP feeds into one unified WeatherContext.
Every adapter in Phase 1 must emit these models — nothing downstream is
allowed to know about upstream payload quirks.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, field_serializer

# --------------------------------------------------------------------------- #
# Enums & tiny value objects
# --------------------------------------------------------------------------- #


class AQICategory(str, Enum):
    """CPCB National Air Quality Index buckets."""

    GOOD = "Good"
    SATISFACTORY = "Satisfactory"
    MODERATE = "Moderate"
    POOR = "Poor"
    VERY_POOR = "Very Poor"
    SEVERE = "Severe"


class WeatherCondition(str, Enum):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    HAZE = "haze"
    FOG = "fog"
    DRIZZLE = "drizzle"
    RAIN = "rain"
    THUNDERSTORM = "thunderstorm"
    HAIL = "hail"
    SNOW = "snow"


class CAPSeverity(str, Enum):
    """OASIS CAP 1.2 severity scale (NDMA SACHET uses this)."""

    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


def aqi_category(value: int) -> AQICategory:
    """Map a CPCB AQI integer (0-500) to its official category."""
    if value <= 50:
        return AQICategory.GOOD
    if value <= 100:
        return AQICategory.SATISFACTORY
    if value <= 200:
        return AQICategory.MODERATE
    if value <= 300:
        return AQICategory.POOR
    if value <= 400:
        return AQICategory.VERY_POOR
    return AQICategory.SEVERE


def snap_geohash5(lat: float, lon: float) -> str:
    """Snap coordinates to a coarse ~5km grid cell (TASK-013 helper).

    Deliberately a simple grid string, not real geohash: DPDP compliance
    only needs coarse, reversible-by-us quantization for cache keys.
    """
    lat_q = math.floor(lat / 0.05) * 0.05
    lon_q = math.floor(lon / 0.05) * 0.05
    return f"{lat_q:.2f}_{lon_q:.2f}"


# --------------------------------------------------------------------------- #
# Observation & forecast blocks
# --------------------------------------------------------------------------- #


class CurrentWeather(BaseModel):
    model_config = ConfigDict(frozen=True)

    temperature_c: float = Field(..., description="Dry-bulb temperature, °C")
    feels_like_c: float | None = None
    humidity_pct: float = Field(..., ge=0, le=100)
    wind_kmph: float = Field(..., ge=0)
    wind_direction_deg: float | None = Field(None, ge=0, lt=360)
    condition: WeatherCondition
    condition_text: str
    pressure_hpa: float | None = None
    visibility_m: int | None = Field(None, ge=0)
    uv_index: float | None = Field(None, ge=0, le=15)
    observed_at: datetime


class HourlyForecastPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    time: datetime
    temperature_c: float
    precipitation_probability_pct: int = Field(..., ge=0, le=100)
    precipitation_mm: float = Field(..., ge=0)
    wind_kmph: float = Field(..., ge=0)
    humidity_pct: float = Field(..., ge=0, le=100)
    condition: WeatherCondition


class DailyForecast(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: datetime
    temp_max_c: float
    temp_min_c: float
    precipitation_probability_pct: int = Field(..., ge=0, le=100)
    condition: WeatherCondition
    condition_text: str
    sunrise: datetime | None = None
    sunset: datetime | None = None


class NowcastAlert(BaseModel):
    """IMD 3-hourly nowcast / short-fuse warning — also carries CAP alerts."""

    model_config = ConfigDict(frozen=True)

    message: str
    severity: CAPSeverity = CAPSeverity.UNKNOWN
    valid_from: datetime
    valid_to: datetime
    source: Literal["IMD_NOWCAST", "MOSDAC_QPE", "NDMA_CAP"] = "IMD_NOWCAST"
    event: str | None = Field(None, description="CAP event type, e.g. 'Cyclone Warning'")
    area_desc: str | None = Field(None, description="Human-readable affected area")
    description: str | None = Field(None, description="Full description + instruction text")


class TideCurvePoint(BaseModel):
    """One sample of the astronomical tide curve (15-min resolution)."""

    model_config = ConfigDict(frozen=True)

    time: datetime
    height_m: float


class MarineObservation(BaseModel):
    """INCOIS INDOFOS ocean-state parameters for coastal personas."""

    model_config = ConfigDict(frozen=True)

    significant_wave_height_m: float = Field(..., ge=0)
    swell_period_s: float | None = Field(None, ge=0)
    swell_height_m: float | None = Field(None, ge=0)
    sst_c: float | None = None
    tide_height_m: float | None = None
    tide_state: Literal["rising", "falling", "high", "low"] | None = None
    next_high_tide: datetime | None = None
    next_low_tide: datetime | None = None
    beach_flag: Literal["green", "yellow", "red"] | None = None
    observed_at: datetime | None = None
    tide_curve: list[TideCurvePoint] = Field(
        default_factory=list,
        max_length=120,
        description="15-min tide height samples for the sine chart (modeled or observed)",
    )


class AirQualityIndex(BaseModel):
    """CPCB CAAQMS aggregate + individual pollutant concentrations."""

    model_config = ConfigDict(frozen=True)

    aqi: int = Field(..., ge=0, le=500)
    dominating_pollutant: str | None = None
    pm2_5_ugm3: float | None = Field(None, ge=0)
    pm10_ugm3: float | None = Field(None, ge=0)
    no2_ugm3: float | None = Field(None, ge=0)
    so2_ugm3: float | None = Field(None, ge=0)
    o3_ugm3: float | None = Field(None, ge=0)
    observed_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def category(self) -> AQICategory:
        """CPCB category is always derived from the AQI integer — never trusted from upstream."""
        return aqi_category(self.aqi)

    @field_serializer("category", when_used="unless-none")
    def _serialize_category(self, v: AQICategory) -> str:
        return v.value


class AgroAdvisory(BaseModel):
    """GKMS/AMFU block-level crop advisory."""

    model_config = ConfigDict(frozen=True)

    block_name: str
    district: str
    amfu_name: str | None = None
    crop_advisories: list[str] = Field(default_factory=list)
    soil_moisture_pct: float | None = Field(None, ge=0, le=100)
    frost_risk: bool = False
    issued_on: datetime | None = None


class GeoLocation(BaseModel):
    """Coarse location identity — raw lat/lon never leaves the request layer."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    district: str | None = None
    state: str | None = None
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def geohash5(self) -> str:
        """Coarse ~5km grid cell, always derived from lat/lon (DPDP-friendly)."""
        return snap_geohash5(self.lat, self.lon)


# --------------------------------------------------------------------------- #
# Root aggregate
# --------------------------------------------------------------------------- #


class WeatherContext(BaseModel):
    """The one payload every service consumes. Adapter-agnostic by contract."""

    model_config = ConfigDict(frozen=True)

    location: GeoLocation
    current: CurrentWeather
    hourly: list[HourlyForecastPoint] = Field(default_factory=list, max_length=48)
    daily: list[DailyForecast] = Field(default_factory=list, max_length=15)
    nowcast: list[NowcastAlert] = Field(default_factory=list)
    marine: MarineObservation | None = None
    air_quality: AirQualityIndex | None = None
    agro: AgroAdvisory | None = None
    cap_alerts: list[NowcastAlert] = Field(
        default_factory=list,
        description="Active NDMA SACHET CAP alerts intersecting this geohash",
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sources_used: list[str] = Field(default_factory=list)
    stale: bool = Field(False, description="True when served from seed replay/cache")


def utcnow() -> datetime:
    return datetime.now(UTC)
