"""
floor_skeleton/frame_deriver.py
--------------------------------
Derive UnitLocalFrame from a FloorSkeleton and UnitZone using geometry only.

Origin is purely geometric (min corner of zone bounds). Axis vectors are aligned
with the footprint coordinate frame; rotated footprints are not supported in Phase 1.5.
Edge detection is tolerance-based (tol=1e-6); segment direction is normalized
for stable ordering. No use of placement_label.
"""

from __future__ import annotations

from typing import Optional

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from floor_skeleton.models import (
    FloorSkeleton,
    UnitZone,
    AXIS_WIDTH_DOMINANT,
    AXIS_DEPTH_DOMINANT,
)
from floor_skeleton.unit_local_frame import UnitLocalFrame

# Tolerance for edge segment length; ignore segments shorter than this
_EDGE_LENGTH_TOL = 1e-6
_COORD_ROUND = 6


def _extract_linestrings_with_length(
    geom: BaseGeometry,
) -> list[tuple[list[tuple[float, float]], float]]:
    """Extract LineString coordinate lists and their lengths. Returns [(coords, length), ...]."""
    result: list[tuple[list[tuple[float, float]], float]] = []
    if geom is None or geom.is_empty:
        return result
    if geom.geom_type == "LineString":
        coords = list(geom.coords)
        if len(coords) >= 2:
            length = geom.length
            result.append((coords, length))
        return result
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        for part in geom.geoms:
            result.extend(_extract_linestrings_with_length(part))
    return result


def _normalize_segment(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return (start, end) with lexicographic order so same edge yields same tuple."""
    r = _COORD_ROUND
    a = (round(p1[0], r), round(p1[1], r))
    b = (round(p2[0], r), round(p2[1], r))
    if a <= b:
        return (a, b)
    return (b, a)


def _longest_shared_segment(
    zone_poly: Polygon,
    other_poly: Optional[Polygon],
    tol: float,
) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    """
    Find longest shared boundary segment between zone_poly and other_poly.
    Returns normalized (start, end) or None if no segment with length >= tol.
    """
    if other_poly is None or other_poly.is_empty or not other_poly.is_valid:
        return None
    if zone_poly.is_empty or not zone_poly.is_valid:
        return None
    try:
        intersection = zone_poly.boundary.intersection(other_poly.boundary)
    except Exception:
        return None
    if intersection.is_empty:
        return None
    segments = _extract_linestrings_with_length(intersection)
    # Filter by length >= tol
    valid = [(coords, length) for coords, length in segments if length >= tol]
    if not valid:
        return None
    # Longest segment
    best_coords, _ = max(valid, key=lambda x: x[1])
    if len(best_coords) < 2:
        return None
    start = (best_coords[0][0], best_coords[0][1])
    end = (best_coords[-1][0], best_coords[-1][1])
    return _normalize_segment(start, end)


def derive_local_frame(
    skeleton: FloorSkeleton,
    zone: UnitZone,
) -> UnitLocalFrame:
    """
    Derive a deterministic UnitLocalFrame for the given zone.

    Uses geometry only (boundary intersection for edges). Origin is purely
    geometric (min corner); axis vectors are footprint-aligned. Rotated
    footprints are not supported in Phase 1.5.
    """
    band_id = getattr(zone, "band_id", 0)

    # Origin: purely geometric min corner
    bounds = zone.polygon.bounds
    if bounds is None or len(bounds) < 2:
        minx, miny = 0.0, 0.0
    else:
        minx, miny = bounds[0], bounds[1]
    origin = (round(minx, _COORD_ROUND), round(miny, _COORD_ROUND))

    # Repeat/depth axes from orientation_axis (axis-aligned only in Phase 1.5)
    axis = getattr(zone, "orientation_axis", AXIS_DEPTH_DOMINANT)
    if axis == AXIS_WIDTH_DOMINANT:
        repeat_axis = (1.0, 0.0)
        depth_axis = (0.0, 1.0)
        band_length_m = zone.zone_width_m
        band_depth_m = zone.zone_depth_m
    else:
        repeat_axis = (0.0, 1.0)
        depth_axis = (1.0, 0.0)
        band_length_m = zone.zone_depth_m
        band_depth_m = zone.zone_width_m

    # Core-facing edge (geometry only)
    core_facing_edge = _longest_shared_segment(
        zone.polygon,
        skeleton.core_polygon if getattr(skeleton, "core_polygon", None) else None,
        _EDGE_LENGTH_TOL,
    )

    # Corridor-facing edge
    corridor_poly = getattr(skeleton, "corridor_polygon", None)
    corridor_facing_edge = None
    if corridor_poly is not None:
        corridor_facing_edge = _longest_shared_segment(
            zone.polygon,
            corridor_poly,
            _EDGE_LENGTH_TOL,
        )

    return UnitLocalFrame(
        band_id=band_id,
        origin=origin,
        repeat_axis=repeat_axis,
        depth_axis=depth_axis,
        band_length_m=band_length_m,
        band_depth_m=band_depth_m,
        core_facing_edge=core_facing_edge,
        corridor_facing_edge=corridor_facing_edge,
    )
