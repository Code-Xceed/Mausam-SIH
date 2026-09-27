"""GKMS agromet adapter (TASK-012) — Phase 1 stub.

Gramin Krishi Mausam Sewa block-level advisories are published as bulletins
per Agromet Field Unit (AMFU); there is no open structured API, so Phase 1
carries authentic advisory text in city fixtures (see
weather_context_vidarbha.json). Phase 4 (TASK-036) renders it in the
Meghdoot-style agro card, and structured ingestion (scrape/API) is added
only if the GKMS portal shape is stable at that point.
"""

from __future__ import annotations

from typing import Any


class GkmsAdapter:
    """Placeholder — structured ingestion decision deferred to Phase 4 (TASK-036)."""

    name = "GKMS"

    async def fetch_agro(self, district: str) -> dict[str, Any] | None:
        return None
