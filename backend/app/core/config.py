"""Application settings (12-factor, env-driven).

The demo-critical knob is API_MODE:
  LIVE   — only real government endpoints; fail loudly.
  HYBRID — try live with LIVE_TIMEOUT_MS budget, fall back to seed fixtures. (default)
  SEED   — never touch the network; pure fixture replay for the jury demo.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "mausam-nextgen-backend"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    LOG_LEVEL: str = "INFO"

    API_MODE: Literal["LIVE", "HYBRID", "SEED"] = "HYBRID"
    LIVE_TIMEOUT_MS: int = Field(default=1200, ge=100, le=10_000)

    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_FORECAST_TTL_S: int = 1800   # 30-min forecast cache (TASK-013)
    CACHE_NOWCAST_TTL_S: int = 300     # 5-min nowcast/AQI cache

    SDUI_SCHEMA_VERSION: str = "v1"
    SDUI_MAX_PAYLOAD_KB: float = 15.0   # Brotli budget (TASK-016)

    BANDIT_ALPHA: float = Field(default=0.2, gt=0)  # LinUCB exploration (TASK-042)
    BANDIT_CONTEXT_DIM: int = 12                    # per DPR §5.2
    BANDIT_RIDGE: float = Field(default=1e-3, ge=0)  # numerical-stability regularizer
    BANDIT_REWARD_CLICK: float = 1.0                # click reward (TASK-043)
    BANDIT_REWARD_DISMISS: float = -1.0             # dismiss reward (negative signal)
    BANDIT_REWARD_DWELL_MS: int = 3000              # dwell ≥ this ⇒ 0.3 implicit reward

    # Optional keys — Phase 1+ fills these; app must boot without any.
    DATA_GOV_API_KEY: str = ""            # api.data.gov.in key (public sample key works)
    DATA_GOV_IMD_RESOURCE: str = ""       # IMD current-weather resource id
    INCOIS_OSF_URL: str = ""              # optional INCOIS OSF JSON endpoint
    CAP_FEED_URL: str = ""                # optional NDMA SACHET CAP XML feed
    CAP_POLL_INTERVAL_S: int = Field(default=60, ge=5)   # TASK-048 poll cadence
    CAP_ALERT_GRACE_S: int = Field(default=300, ge=0)    # keep alerts N s past expiry

    FCM_PROJECT_ID: str = ""              # Firebase project for push (TASK-050)
    IMD_API_KEY: str = ""                 # api.imd.gov.in subscription (Phase 2+)
    BHASHINI_API_KEY: str = ""
    FCM_CREDENTIALS_JSON: str = ""

    ADAPTER_FAILURE_THRESHOLD: int = 3    # breaker opens after N consecutive live failures
    ADAPTER_RESET_TIME_S: float = 60.0    # breaker half-open retry window


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
