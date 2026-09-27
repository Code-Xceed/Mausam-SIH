"""Polygon → geohash clipping (TASK-049): CAP danger zones to coarse cells.

The gateway snaps every user to a ~5 km grid cell (`snap_geohash5`, the
"geohash5" of the task list). To push an alert to the right devices we need
the inverse mapping: which grid cells lie inside the alert's CAP polygon?

Strategy (no PostGIS per AD-001, no shapely yet):
    1. Polygon bounding box.
    2. Walk the 0.05° grid inside the box (~5 km cells).
    3. Keep cells whose CENTER passes the existing ray-casting
       `point_in_polygon` test (shared with the request path — one geometry
       implementation, one set of edge cases).
    4. Huge polygons (>1000 candidate cells, e.g. statewide warnings) sample
       a 0.25° grid (~25 km cells), then EXPAND each matched coarse cell back
       to its 25 constituent fine cells so device subscriptions (fine-grid
       topics) keep exact coverage. Expansion beyond FINE_EXPANSION_CELLS
       degrades to broadcast ("*") — over-coverage is safe, under-coverage
       silently drops alerts, so we always err wide.

Area-wide alerts (no polygon) return the sentinel `{"*"}` = broadcast to all
topics. Zero spatial leaks: a device topic is included iff its cell lies
inside the polygon.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from app.adapters.cap import point_in_polygon
from app.models.weather import snap_geohash5

logger = logging.getLogger(__name__)

# Grid resolution in degrees. 0.05° ≈ 5.5 km lat — matches snap_geohash5.
FINE_STEP = 0.05
COARSE_STEP = 0.25
# Nominal switch at 1000 candidates, +10% headroom: bbox-corner float noise
# (e.g. 20.4/0.05 = 408.00000000000006) can add a phantom boundary row/col
# (~+25 cells for city-scale polygons) — the pad stops a polygon flickering
# between fine and coarse treatment across feed revisions.
MAX_FINE_CELLS = 1100
COARSE_FINE_RATIO = int(round(COARSE_STEP / FINE_STEP))  # 5 → 25 sub-cells
FINE_EXPANSION_CAP = 8000  # expanded coarse set beyond this → broadcast

BROADCAST = "*"  # sentinel topic-part for polygon-less (area-wide) alerts

Polygon = list[tuple[float, float]]


@dataclass
class TargetSet:
    """Resolved push targets for one alert."""

    geohashes: set[str] = field(default_factory=set)
    area_wide: bool = False   # no polygon → broadcast
    coarse: bool = False      # fell back to 25 km grid

    @property
    def size(self) -> int:
        return 0 if self.area_wide else len(self.geohashes)

    def topic_names(self, prefix: str = "alert") -> list[str]:
        """FCM topic names, e.g. `alert_28.55_77.20` (or `alert_broadcast`)."""
        if self.area_wide:
            return [f"{prefix}_{BROADCAST}"]
        return [f"{prefix}_{g}" for g in sorted(self.geohashes)]


def polygon_bbox(polygon: Polygon) -> tuple[float, float, float, float] | None:
    """(min_lat, min_lon, max_lat, max_lon) or None for degenerate polygons."""
    if len(polygon) < 3:
        return None
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    return min(lats), min(lons), max(lats), max(lons)


def grid_cells_in_bbox(
    bbox: tuple[float, float, float, float], step: float
) -> list[tuple[float, float]]:
    """Cell ORIGINS (multiples of `step`) covering the bbox.

    Index-multiplicative (no float accumulation drift) so boundary cells are
    never skipped on large bboxes.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    lat0 = math.floor(min_lat / step) * step
    lon0 = math.floor(min_lon / step) * step
    n_lat = int(math.floor((max_lat - lat0) / step + 1e-9)) + 1
    n_lon = int(math.floor((max_lon - lon0) / step + 1e-9)) + 1
    return [
        (round(lat0 + i * step, 4), round(lon0 + j * step, 4))
        for i in range(n_lat)
        for j in range(n_lon)
    ]


def geohashes_in_polygon(polygon: Polygon) -> tuple[set[str], bool]:
    """Grid cells whose centers are inside `polygon` → (geohash strings, coarse).

    Coarse mode returns fine-floor addresses of coarse-cell CENTERS; callers
    expand them back to full fine coverage (see `_expand_coarse_cells`).
    """
    bbox = polygon_bbox(polygon)
    if bbox is None:
        return set(), False

    # Candidate count arithmetically — never materialize the fine grid for a
    # continental bbox just to decide it's too big.
    min_lat, min_lon, max_lat, max_lon = bbox
    lat0 = math.floor(min_lat / FINE_STEP) * FINE_STEP
    lon0 = math.floor(min_lon / FINE_STEP) * FINE_STEP
    n_lat = int(math.floor((max_lat - lat0) / FINE_STEP + 1e-9)) + 1
    n_lon = int(math.floor((max_lon - lon0) / FINE_STEP + 1e-9)) + 1
    coarse = n_lat * n_lon > MAX_FINE_CELLS
    step = COARSE_STEP if coarse else FINE_STEP

    half = step / 2.0
    matched: set[str] = set()
    for cell_lat, cell_lon in grid_cells_in_bbox(bbox, step):
        c_lat = cell_lat + half
        c_lon = cell_lon + half
        if point_in_polygon(c_lat, c_lon, polygon):
            matched.add(snap_geohash5(c_lat, c_lon))
    return matched, coarse


def _expand_coarse_cells(cells: set[str]) -> set[str]:
    """Expand matched coarse cells to their 25 constituent fine cells.

    Coarse matching yields fine-grid addresses of coarse-cell CENTERS only;
    a device subscribed to a neighbouring fine cell inside the same coarse
    cell would be silently missed. Expanding restores exact coverage while
    keeping the fine-grid topic namespace the client already speaks.

    Addresses are built from INTEGER cell indices (`k * FINE_STEP`), never by
    re-snapping floats: snap_geohash5 floors, so snap(19.15) collapses to
    "19.10" (19.15/0.05 = 382.999…9) and float-addition expansion would drop
    whole rows. Index arithmetic matches device-side snapping exactly.
    """
    expanded: set[str] = set()
    for cell in cells:
        try:
            lat_s, lon_s = cell.split("_")
            c_lat, c_lon = float(lat_s), float(lon_s)
        except ValueError:
            expanded.add(cell)
            continue
        o_lat = math.floor(round(c_lat, 6) / COARSE_STEP) * COARSE_STEP
        o_lon = math.floor(round(c_lon, 6) / COARSE_STEP) * COARSE_STEP
        k_lat0 = int(round(o_lat / FINE_STEP))
        k_lon0 = int(round(o_lon / FINE_STEP))
        for i in range(COARSE_FINE_RATIO):
            for j in range(COARSE_FINE_RATIO):
                expanded.add(
                    f"{(k_lat0 + i) * FINE_STEP:.2f}_{(k_lon0 + j) * FINE_STEP:.2f}"
                )
    return expanded


def alert_target_set(alert: dict) -> TargetSet:
    """Resolve one parsed CAP alert dict to its push-target cell set."""
    polygons: list[Polygon] = alert.get("polygons") or []
    if not polygons:
        return TargetSet(area_wide=True)

    targets: set[str] = set()
    any_coarse = False
    for poly in polygons:
        cells, coarse = geohashes_in_polygon(poly)
        targets |= cells
        any_coarse = any_coarse or coarse

    if any_coarse:
        # Early-exit: a genuinely continental polygon would expand to
        # hundreds of thousands of strings — broadcast before paying for it.
        if len(targets) * COARSE_FINE_RATIO * COARSE_FINE_RATIO > FINE_EXPANSION_CAP:
            logger.info(
                "[geofence] polygon exceeds %d fine cells — broadcasting",
                FINE_EXPANSION_CAP,
            )
            return TargetSet(area_wide=True, coarse=True)
        expanded = _expand_coarse_cells(targets)
        return TargetSet(geohashes=expanded, coarse=True)
    return TargetSet(geohashes=targets)


def circle_polygon(
    lat: float, lon: float, radius_deg: float = 0.35, points: int = 16
) -> Polygon:
    """Synthetic ~circular CAP polygon (demo injection tool, TASK-054).

    `radius_deg` is a latitude-degree radius (~39 km at 0.35); longitude
    offsets are scaled by cos(lat) so the circle stays roughly round.
    """
    poly: Polygon = []
    for i in range(points):
        theta = 2.0 * math.pi * i / points
        d_lat = radius_deg * math.cos(theta)
        d_lon = radius_deg * math.sin(theta) / max(0.2, math.cos(math.radians(lat)))
        poly.append((round(lat + d_lat, 4), round(lon + d_lon, 4)))
    poly.append(poly[0])  # CAP polygons repeat the first vertex to close
    return poly
