"""Shared fixture loading + freshness retiming.

Fixtures are *authentic-shaped* seed payloads (TASK-015). Because a jury
demo must never display stale timestamps, every datetime inside a context
fixture is re-anchored to "now" at load time.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.clock import bucketed_now

logger = logging.getLogger(__name__)

# fixtures.py -> services -> app -> backend -> <repo root>/mock_fixtures
_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "mock_fixtures"


def fixture_dir() -> Path:
    return _FIXTURE_DIR


def load_fixture(name: str) -> dict[str, Any]:
    path = _FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def retime_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Re-anchor all datetimes in a context fixture to *now*.

    Keeps the demo perpetually fresh: observed_at = now, hourly[i] = now + i
    hours, daily[i] = today + i days (sunrise/sunset normalized to the day).
    """
    now = bucketed_now()  # 5-min bucket: keeps ETags stable within max-age window
    raw["generated_at"] = now.isoformat()

    if cur := raw.get("current"):
        cur["observed_at"] = now.isoformat()

    if aq := raw.get("air_quality"):
        aq["observed_at"] = now.isoformat()

    if marine := raw.get("marine"):
        marine["observed_at"] = now.isoformat()

    # Nowcast windows are re-anchored so they are always "active": starts now,
    # expires in 2h. A demo at any hour shows a live short-fuse warning.
    for alert in raw.get("nowcast", []):
        alert["valid_from"] = now.isoformat()
        alert["valid_to"] = (now + timedelta(hours=2)).isoformat()

    for i, point in enumerate(raw.get("hourly", [])):
        point["time"] = (now + timedelta(hours=i)).isoformat()

    for i, day in enumerate(raw.get("daily", [])):
        base = now + timedelta(days=i)
        day["date"] = base.isoformat()
        if day.get("sunrise"):
            day["sunrise"] = base.replace(hour=6, minute=12, second=0, microsecond=0).isoformat()
        if day.get("sunset"):
            day["sunset"] = base.replace(hour=18, minute=34, second=0, microsecond=0).isoformat()

    return raw
