"""
presentation_engine/wall_builder.py
-------------------------------------
Converts FloorSkeleton polygons into WallGeometry objects (double-line walls)
and partition lines (single-line zone boundaries).

Public API
----------
    build(skeleton) -> tuple[
        list[WallGeometry],   # external_walls  (footprint)
        list[WallGeometry],   # core_walls
        list[list[tuple]],    # partition_lines
        bool,                 # used_fallback_walls
    ]

Wall representation
-------------------
Each wall is a pair of LWPOLYLINE rings:
    outer ring  — the source polygon's exterior
    inner ring  — inward-buffered polygon's exterior (double-line)

Three-tier fallback per polygon
--------------------------------
1. buffer(−wall_t_m, join_style=2, mitre_limit=2.0)  — sharp corners
2. buffer(−wall_t_m, join_style=1)                    — round corners
3. Single-line only (is_double_line=False)

Safety pre-check
-----------------
If min(width, depth) < 2 * wall_t_m + 0.1:
    → skip buffer entirely, use single-line fallback.

Partition lines
---------------
Shared boundaries between adjacent zones (core ↔ unit, corridor ↔ unit, etc.)
extracted via Shapely boundary intersection.  Any non-LineString result is
silently skipped.
"""

from __future__ import annotations

import logging
import warnings
from typing import Optional

from shapely.geometry import Polygon, MultiLineString, LineString, MultiPolygon
from shapely.errors import ShapelyError

from floor_skeleton.models import FloorSkeleton
from presentation_engine.models import WallGeometry

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

WALL_T_M: float = 0.23          # standard external wall thickness (metres)
CORE_WALL_T_M: float = 0.30     # core / shear wall thickness (metres)
_MIN_CLEAR: float = 0.10        # minimum clear space after both walls (metres)

# DXF layer names
_LAYER_EXT  = "A-WALL-EXT"
_LAYER_CORE = "A-CORE"


# ── Public function ────────────────────────────────────────────────────────────

def build(
    skeleton: FloorSkeleton,
) -> tuple[list[WallGeometry], list[WallGeometry], list[list[tuple]], bool]:
    """
    Build wall geometry from *skeleton*.

    Returns
    -------
    external_walls      : WallGeometry list for the footprint.
    core_walls          : WallGeometry list for the core polygon.
    partition_lines     : List of (x,y) coordinate sequences for zone boundaries.
    used_fallback_walls : True if any wall fell back to single-line mode.
    """
    used_fallback = False

    # ── External footprint wall ───────────────────────────────────────────────
    ext_wall, ext_fallback = _build_wall(
        skeleton.footprint_polygon, WALL_T_M, _LAYER_EXT
    )
    if ext_fallback:
        used_fallback = True

    # ── Core wall ─────────────────────────────────────────────────────────────
    core_wall, core_fallback = _build_wall(
        skeleton.core_polygon, CORE_WALL_T_M, _LAYER_CORE
    )
    if core_fallback:
        used_fallback = True

    # ── Partition lines ───────────────────────────────────────────────────────
    partition_lines = _extract_partition_lines(skeleton)

    return [ext_wall], [core_wall], partition_lines, used_fallback


def build_fallback(
    skeleton: FloorSkeleton,
) -> tuple[list[WallGeometry], list[WallGeometry], list[list[tuple]]]:
    """
    Emergency fallback: single-line walls only (no buffer attempted).

    Returns
    -------
    external_walls, core_walls, partition_lines
    """
    ext_wall  = _single_line_wall(skeleton.footprint_polygon, _LAYER_EXT)
    core_wall = _single_line_wall(skeleton.core_polygon, _LAYER_CORE)
    partition_lines = _extract_partition_lines(skeleton)
    return [ext_wall], [core_wall], partition_lines


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_wall(
    polygon: Polygon,
    wall_t_m: float,
    layer: str,
) -> tuple[WallGeometry, bool]:
    """
    Attempt double-line wall for *polygon* with three-tier fallback.

    Returns (WallGeometry, used_fallback:bool).
    """
    outer_coords = _poly_coords(polygon)

    # Safety pre-check: polygon must be wide enough to accommodate both walls
    minx, miny, maxx, maxy = polygon.bounds
    min_dim = min(maxx - minx, maxy - miny)
    if min_dim < 2 * wall_t_m + _MIN_CLEAR:
        logger.warning(
            "Wall safety pre-check failed for polygon (min_dim=%.3f m, "
            "required=%.3f m) — using single-line fallback.",
            min_dim, 2 * wall_t_m + _MIN_CLEAR,
        )
        return _single_line_wall(polygon, layer), True

    # Tier 1: mitre buffer (sharp corners)
    inner = _try_buffer(polygon, wall_t_m, join_style=2, mitre_limit=2.0)
    if inner is not None:
        return WallGeometry(
            outer_coords=outer_coords,
            inner_coords=_poly_coords(inner),
            layer=layer,
            is_double_line=True,
        ), False

    # Tier 2: round buffer (more lenient)
    logger.warning(
        "Mitre buffer failed for layer %s — trying round buffer.", layer
    )
    inner = _try_buffer(polygon, wall_t_m, join_style=1)
    if inner is not None:
        return WallGeometry(
            outer_coords=outer_coords,
            inner_coords=_poly_coords(inner),
            layer=layer,
            is_double_line=True,
        ), False

    # Tier 3: single-line fallback
    logger.warning(
        "Round buffer also failed for layer %s — using single-line fallback.",
        layer,
    )
    return _single_line_wall(polygon, layer), True


def _try_buffer(
    polygon: Polygon,
    wall_t_m: float,
    join_style: int,
    mitre_limit: float = 5.0,
) -> Optional[Polygon]:
    """
    Attempt an inward buffer.  Returns the result Polygon or None on failure.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = polygon.buffer(-wall_t_m, join_style=join_style,
                                    mitre_limit=mitre_limit)
        if (
            result is not None
            and not result.is_empty
            and result.is_valid
            and isinstance(result, Polygon)
            and result.area > 0.01
        ):
            return result
    except (ShapelyError, ValueError, Exception) as exc:
        logger.debug("Buffer attempt failed: %s", exc)
    return None


def _single_line_wall(polygon: Polygon, layer: str) -> WallGeometry:
    """Return a single-line (no inner ring) WallGeometry."""
    return WallGeometry(
        outer_coords=_poly_coords(polygon),
        inner_coords=[],
        layer=layer,
        is_double_line=False,
    )


def _poly_coords(polygon: Polygon) -> list[tuple[float, float]]:
    """
    Extract exterior ring coordinates rounded to 6 decimal places.
    Strips the duplicate closing vertex (Shapely includes it).
    """
    coords = list(polygon.exterior.coords)
    # Remove duplicate closing vertex
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(round(x, 6), round(y, 6)) for x, y in coords]


def _extract_partition_lines(
    skeleton: FloorSkeleton,
) -> list[list[tuple[float, float]]]:
    """
    Find all shared boundary segments between adjacent zone polygons.

    Zones checked:
        core_polygon  ↔  corridor_polygon (if present)
        core_polygon  ↔  each unit_zone.polygon
        corridor_polygon ↔ each unit_zone.polygon (if corridor present)
        unit_zones[0]  ↔  unit_zones[1]  (DOUBLE_LOADED: direct unit adjacency)

    Any intersection that is not a LineString (or MultiLineString) is silently
    skipped — this prevents the corridor splitting edge case from crashing.
    """
    lines: list[list[tuple[float, float]]] = []

    zone_polys: list[Polygon] = [skeleton.core_polygon]
    if skeleton.corridor_polygon is not None:
        zone_polys.append(skeleton.corridor_polygon)
    for uz in skeleton.unit_zones:
        zone_polys.append(uz.polygon)

    for i, poly_a in enumerate(zone_polys):
        for poly_b in zone_polys[i + 1:]:
            shared = _shared_boundary(poly_a, poly_b)
            lines.extend(shared)

    return lines


def _shared_boundary(
    poly_a: Polygon,
    poly_b: Polygon,
) -> list[list[tuple[float, float]]]:
    """
    Return shared edge(s) between two adjacent polygons.
    """
    try:
        intersection = poly_a.boundary.intersection(poly_b.boundary)
        if intersection.is_empty:
            return []
        return _extract_linestrings(intersection)
    except Exception as exc:
        logger.debug("Shared boundary extraction failed: %s", exc)
        return []


def _extract_linestrings(geom) -> list[list[tuple[float, float]]]:
    """Recursively extract LineString coordinate lists from any geometry."""
    if geom.geom_type == "LineString":
        coords = [(round(x, 6), round(y, 6)) for x, y in geom.coords]
        if len(coords) >= 2:
            return [coords]
        return []
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        result = []
        for part in geom.geoms:
            result.extend(_extract_linestrings(part))
        return result
    return []
