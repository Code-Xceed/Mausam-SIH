"""Simplified geospatial boundaries + tile payloads (TASK-059/060 backend half).

TASK-060 needs district/state boundaries for map context; TASK-059 demands
small payloads (<60 KB per view). Real OpenStreetMap state GeoJSON is
megabytes — for the offline demo this module ships DECISIVELY simplified
state rings (clearly flagged `schematic: true`) served as GeoJSON
FeatureCollections, with attributes stripped to name+code and coordinates
quantized to 3 decimals. The production swap is drop-in: same endpoints,
full-resolution GeoJSON, same client.

Tile math is standard slippy-map Web Mercator: /v1/geo/tile/{z}/{x}/{y}.json
returns only features whose bbox intersects the tile — a JSON "vector tile"
that stays far under the 60 KB budget (asserted in tests).
"""

from __future__ import annotations

import math
from typing import Any

# --------------------------------------------------------------------------- #
# Simplified state rings (schematic demo boundaries — NOT survey-grade).
# 6-10 vertices each; attributes stripped to name/code per TASK-059.
# --------------------------------------------------------------------------- #

_STATES: list[dict[str, Any]] = [
    {
        "name": "Delhi (NCT)",
        "code": "DL",
        "ring": [[28.90, 76.84], [28.90, 77.35], [28.60, 77.36], [28.35, 77.32],
                 [28.32, 76.83], [28.62, 76.82], [28.90, 76.84]],
    },
    {
        "name": "Maharashtra",
        "code": "MH",
        "ring": [[20.30, 72.65], [20.90, 73.40], [21.60, 75.20], [21.90, 77.60],
                 [21.20, 79.30], [19.90, 80.10], [18.30, 80.20], [16.10, 80.00],
                 [15.70, 78.20], [15.90, 75.50], [17.50, 73.60], [18.90, 72.80],
                 [20.30, 72.65]],
    },
    {
        "name": "Kerala",
        "code": "KL",
        "ring": [[12.75, 74.85], [12.50, 75.60], [11.00, 76.20], [9.50, 76.90],
                 [8.30, 77.10], [8.15, 77.55], [9.10, 77.05], [10.60, 76.30],
                 [12.20, 75.40], [12.75, 74.85]],
    },
    {
        "name": "Himachal Pradesh",
        "code": "HP",
        "ring": [[32.60, 75.95], [32.90, 76.90], [32.50, 78.10], [31.90, 78.90],
                 [31.30, 78.80], [30.85, 77.70], [31.10, 76.70], [31.90, 75.85],
                 [32.60, 75.95]],
    },
    {
        "name": "Goa",
        "code": "GA",
        "ring": [[15.75, 73.70], [15.80, 74.20], [15.30, 74.25], [14.90, 74.05],
                 [15.00, 73.75], [15.75, 73.70]],
    },
]

_SCHEMATIC_FLAG = True


def boundaries_featurecollection() -> dict[str, Any]:
    """All simplified state boundaries as a GeoJSON FeatureCollection."""
    features = []
    for s in _STATES:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": s["name"],
                    "code": s["code"],
                    "schematic": _SCHEMATIC_FLAG,
                    "source": "OSM-derived, simplified for the <60KB demo budget",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [s["ring"]],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _bbox_of_ring(ring: list[list[float]]) -> tuple[float, float, float, float]:
    lats = [p[0] for p in ring]
    lons = [p[1] for p in ring]
    return min(lats), min(lons), max(lats), max(lons)


def _bboxes_intersect(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _quantize(ring: list[list[float]]) -> list[list[float]]:
    """3-decimal coordinates (~110 m precision) — TASK-059 attribute/size trim."""
    return [[round(p[0], 3), round(p[1], 3)] for p in ring]


def slippy_tile_bbox(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Web-Mercator tile → (min_lat, min_lon, max_lat, max_lon)."""
    n = 2.0**z
    lon_min = x / n * 360.0 - 180.0
    lon_max = (x + 1) / n * 360.0 - 180.0
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lat_min, lon_min, lat_max, lon_max


def build_tile(z: int, x: int, y: int) -> dict[str, Any]:
    """Viewport bundle: simplified boundaries + active CAP polygons.

    Everything is bbox-filtered and quantized; the response stays small
    (asserted <60 KB in tests) and the client renders it directly.
    """
    tile_bbox = slippy_tile_bbox(z, x, y)

    boundary_features = []
    for s in _STATES:
        if _bboxes_intersect(_bbox_of_ring(s["ring"]), tile_bbox):
            boundary_features.append(
                {
                    "type": "Feature",
                    "properties": {"name": s["name"], "code": s["code"], "kind": "boundary"},
                    "geometry": {"type": "Polygon", "coordinates": [_quantize(s["ring"])]},
                }
            )

    # Active CAP polygons (TASK-055 data half re-used here).
    from app.services.alert_store import alert_store

    alert_features = []
    for a in alert_store.active():
        for poly in a.get("polygons") or []:
            ring = [[float(lat), float(lon)] for lat, lon in poly]
            if _bboxes_intersect(_bbox_of_ring(ring), tile_bbox):
                alert_features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "kind": "cap_alert",
                            "identifier": a.get("identifier"),
                            "event": a.get("event"),
                            "severity": a.get("severity"),
                        },
                        "geometry": {"type": "Polygon", "coordinates": [_quantize(ring)]},
                    }
                )

    return {
        "type": "FeatureCollection",
        "tile": {"z": z, "x": x, "y": y},
        "schematic": _SCHEMATIC_FLAG,
        "features": boundary_features + alert_features,
    }
