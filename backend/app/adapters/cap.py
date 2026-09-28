"""NDMA SACHET CAP 1.2 alert ingestion (TASK-048 groundwork, Phase 1).

Parses OASIS CAP 1.2 XML (the format SACHET/IMD distribute) into normalized
alert dicts and provides point-in-polygon geo-fencing so the gateway can
attach only alerts that actually intersect the user's coarse location.

Live polling + FCM fan-out arrive in Phase 6; this module is the parse +
geometry core both phases share.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.core.config import settings

logger = logging.getLogger(__name__)

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def _parse_cap_datetime(raw: str | None, default: datetime) -> datetime:
    """CAP dates like '2026-09-01T15:00:00+05:30' (or with '-05:30' offset quirk)."""
    if not raw:
        return default
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return default


def parse_cap_xml(
    xml: str | bytes, expired_policy: str = "drop"
) -> list[dict[str, Any]]:
    """Parse a CAP 1.2 document into a list of normalized alert dicts.

    expired_policy="drop"   — live feeds: expired info blocks are dropped.
    expired_policy="extend" — demo fixtures: expired blocks are extended to
                              now+6h so the disaster demo never time-bombs.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        logger.warning("[CAP] XML parse error: %s", exc)
        return []

    alerts: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    # <alert> is the document root in CAP 1.2; <info> blocks carry per-language
    # severity/urgency/polygon data. One alert may hold several <info> blocks.
    alerts_in_doc = [root] if root.tag.endswith("alert") else root.findall(".//cap:alert", CAP_NS)

    for alert_el in alerts_in_doc:
        identifier = _text(alert_el.find("cap:identifier", CAP_NS)) or "unknown"
        sender = _text(alert_el.find("cap:sender", CAP_NS)) or "unknown"
        sent = _parse_cap_datetime(_text(alert_el.find("cap:sent", CAP_NS)), now)

        infos = alert_el.findall("cap:info", CAP_NS)
        for info_idx, info in enumerate(infos):
            severity_raw = (_text(info.find("cap:severity", CAP_NS)) or "Unknown").capitalize()
            event = _text(info.find("cap:event", CAP_NS)) or "Weather alert"
            headline = _text(info.find("cap:headline", CAP_NS)) or event
            description = _text(info.find("cap:description", CAP_NS)) or ""
            urgency = _text(info.find("cap:urgency", CAP_NS)) or "Unknown"
            certainty = _text(info.find("cap:certainty", CAP_NS)) or "Unknown"

            expires = _parse_cap_datetime(_text(info.find("cap:expires", CAP_NS)), now + timedelta(hours=6))
            if expires < now:
                if expired_policy == "extend":
                    expires = now + timedelta(hours=6)
                else:
                    continue  # silently drop expired info blocks

            # <area> blocks: polygon coordinates + areaDesc
            polygons: list[list[tuple[float, float]]] = []
            area_descs: list[str] = []
            for area in info.findall("cap:area", CAP_NS):
                if desc := _text(area.find("cap:areaDesc", CAP_NS)):
                    area_descs.append(desc)
                for poly_el in area.findall("cap:polygon", CAP_NS):
                    pts = _parse_polygon(_text(poly_el))
                    if pts:
                        polygons.append(pts)

            # CAP identifiers are alert-level; multiple <info> blocks (common:
            # per-hazard sub-warnings) each need a STABLE unique key so the
            # poller's diff logic doesn't clobber one with the next.
            info_ident = identifier
            if len(infos) > 1:
                slug = event.lower().replace(" ", "-")
                info_ident = f"{identifier}--{slug}-{info_idx}"

            alerts.append(
                {
                    "identifier": info_ident,
                    "sender": sender,
                    "sent": sent.isoformat(),
                    "event": event,
                    "severity": severity_raw if severity_raw in {"Extreme", "Severe", "Moderate", "Minor"} else "Unknown",
                    "urgency": urgency,
                    "certainty": certainty,
                    "headline": headline,
                    "description": description,
                    "expires": expires.isoformat(),
                    "area_desc": "; ".join(area_descs) or None,
                    "polygons": polygons,
                    "source": "NDMA_CAP",
                }
            )
    return alerts


def _parse_polygon(text: str | None) -> list[tuple[float, float]]:
    """CAP polygons: whitespace/newline-separated 'lat,lon' pairs."""
    if not text:
        return []
    pts: list[tuple[float, float]] = []
    for token in text.replace("\n", " ").split():
        try:
            lat_s, lon_s = token.split(",")
            pts.append((float(lat_s), float(lon_s)))
        except ValueError:
            continue
    return pts


def point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon (good enough for city-scale CAP zones)."""
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lat_i > lat) != (lat_j > lat):
            intersect_lat = (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i
            if lon < intersect_lat:
                inside = not inside
        j = i
    return inside


def alerts_for_location(
    alerts: list[dict[str, Any]], lat: float, lon: float
) -> list[dict[str, Any]]:
    """Filter alerts whose polygons contain the point, or with no polygons (area-wide)."""
    matched: list[dict[str, Any]] = []
    for alert in alerts:
        polys = alert.get("polygons") or []
        if not polys:
            matched.append(alert)  # area-wide alert: apply everywhere
            continue
        if any(point_in_polygon(lat, lon, poly) for poly in polys):
            matched.append(alert)
    return matched


def cap_to_nowcast(alert: dict[str, Any]) -> dict[str, Any]:
    """Project a parsed CAP alert into NowcastAlert-compatible fields."""
    description = alert.get("description") or ""
    instruction = alert.get("instruction") or ""
    return {
        "message": alert.get("headline") or alert.get("event") or "Weather alert",
        "event": alert.get("event"),
        "area_desc": alert.get("area_desc"),
        "description": f"{description} {instruction}".strip() or None,
        "severity": alert.get("severity") or "Unknown",
        "valid_from": alert.get("sent"),
        "valid_to": alert.get("expires"),
        "source": "NDMA_CAP",
    }


class CapAdapter:
    """Polls a CAP XML URL (or reads bundled fixture) and exposes parsed alerts."""

    name = "NDMA_CAP"

    async def fetch_alerts(self) -> list[dict[str, Any]]:
        if settings.CAP_FEED_URL:
            from app.adapters.base import get_http_client

            try:
                client = await get_http_client()
                resp = await client.get(settings.CAP_FEED_URL)
                resp.raise_for_status()
                return parse_cap_xml(resp.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[CAP] live poll failed: %s: %s", type(exc).__name__, exc)

        # Fixture fallback (and the SEED-mode default) — extend expiry so the
        # bundled demo alert stays active forever. Resolve via repo layout OR
        # container layout (/srv), matching cap_poller/fixtures discovery.
        here = Path(__file__).resolve()
        fixture = next(
            (
                base / "mock_fixtures" / "cap_alerts.xml"
                for base in (here.parents[3], here.parents[2])
                if (base / "mock_fixtures" / "cap_alerts.xml").exists()
            ),
            here.parents[3] / "mock_fixtures" / "cap_alerts.xml",
        )
        if fixture.exists():
            return parse_cap_xml(fixture.read_text(encoding="utf-8"), expired_policy="extend")
        return []
