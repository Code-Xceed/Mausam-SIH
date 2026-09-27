"""Shared fixtures — hermetic alert pipeline for the whole suite.

The alert store and CAP poller are process-global singletons wired into the
FastAPI lifespan. Without these fixtures:
  - every module's TestClient lifespan re-ingests fixture alerts into the
    global store, whose state then leaks into later modules through the
    gateway/SDUI path, and
  - background 60 s ticks race per-test store count assertions.

So the session quiets the poller's FEED (the loop task itself still starts
and stops per lifespan, exercising the real wiring), and every test begins
and ends with an empty store. Tests that need feed content (poller tests)
re-point ``poller.fetch_alerts`` locally.
"""

from __future__ import annotations

import pytest

from app.services.alert_store import alert_store
from app.services.cap_poller import poller


@pytest.fixture(scope="session", autouse=True)
def _quiet_poller_feed():
    real = poller.fetch_alerts

    async def _none() -> list[dict]:
        return []

    poller.fetch_alerts = _none
    yield poller
    poller.fetch_alerts = real


@pytest.fixture(autouse=True)
def _clean_alert_store():
    alert_store.clear_all()
    yield
    alert_store.clear_all()
