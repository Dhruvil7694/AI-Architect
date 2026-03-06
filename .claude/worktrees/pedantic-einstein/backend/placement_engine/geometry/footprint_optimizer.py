"""
placement_engine/geometry/footprint_optimizer.py
-------------------------------------------------
Tower footprint optimization inside a single zone.

Instead of taking the first rectangle that fits (from the packer), this module
explores a grid of width × depth combinations and selects the footprint with
the largest area that fits entirely inside the zone. This improves ground
coverage utilization (e.g. 30–50%) when zones have irregular shape or when
the inscribed-rectangle grid resolution would miss a better fit.

Algorithm:
  1. Get zone orientation (primary and secondary) and rotated bbox to cap max dimensions.
  2. Build a grid: width_m ∈ [min_width_m, max_width_m], depth_m ∈ [min_depth_m, max_depth_m].
  3. For each (width_m, depth_m), try both orientations; place rectangle at zone
     representative point; check zone.contains(rect).
  4. Return the FootprintCandidate with largest valid area.

Spacing and road corridor logic are unchanged; this only affects the single-zone
footprint used in the zone placement cache.
"""

from __future__ import annotations

import math
from typing import Optional, List

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box, Point
from shapely.prepared import prep

from placement_engine.geometry import (
    METRES_TO_DXF,
    DXF_TO_METRES,
    MIN_FOOTPRINT_AREA_SQFT,
    MIN_FOOTPRINT_WIDTH_M,
    MIN_FOOTPRINT_DEPTH_M,
    FootprintCandidate,
)
from placement_engine.geometry.orientation_finder import find_orientation


# Grid step in metres; coarser = faster, finer = better utilization
FOOTPRINT_GRID_STEP_M: float = 1.0

# Maximum footprint side in metres (cap for very large zones)
MAX_FOOTPRINT_SIDE_M: float = 60.0


def _rect_at_center(
    center_x: float,
    center_y: float,
    width_dxf: float,
    depth_dxf: float,
    angle_deg: float,
) -> Polygon:
    """
    Build a Shapely Polygon for a rectangle centered at (center_x, center_y)
    with given width (along angle) and depth (perpendicular), rotated by angle_deg.
    All units DXF feet.
    """
    # Local: box from (0,0) to (width_dxf, depth_dxf), then center at origin
    r = box(0, 0, width_dxf, depth_dxf)
    r = translate(r, -width_dxf / 2.0, -depth_dxf / 2.0)
    r = rotate(r, angle_deg, origin=(0, 0), use_radians=False)
    r = translate(r, center_x, center_y)
    return r


def _rotated_bbox_dims(zone: Polygon, angle_deg: float) -> tuple[float, float]:
    """Return (width_dxf, depth_dxf) of zone's bbox in rotated (axis-aligned) space."""
    from shapely.affinity import rotate as shapely_rotate
    rotated = shapely_rotate(zone, -angle_deg, origin="centroid", use_radians=False)
    minx, miny, maxx, maxy = rotated.bounds
    w = maxx - minx
    h = maxy - miny
    return w, h


def _sample_centers(zone: Polygon, prepared_zone, points_per_axis: int = 3) -> list[tuple[float, float]]:
    """
    Sample a small grid of candidate centre points inside the zone.

    This lets the optimizer slide the rectangle within the polygon instead of
    being locked to zone.representative_point().
    """
    minx, miny, maxx, maxy = zone.bounds
    if not math.isfinite(minx) or not math.isfinite(miny) or not math.isfinite(maxx) or not math.isfinite(maxy):
        rep = zone.representative_point()
        return [(rep.x, rep.y)]

    dx = (maxx - minx) / (points_per_axis + 1) if points_per_axis > 0 else 0.0
    dy = (maxy - miny) / (points_per_axis + 1) if points_per_axis > 0 else 0.0

    centres: list[tuple[float, float]] = []
    for i in range(points_per_axis):
        cx = minx + (i + 1) * dx
        for j in range(points_per_axis):
            cy = miny + (j + 1) * dy
            p = Point(cx, cy)
            if prepared_zone.contains(p):
                centres.append((cx, cy))

    if not centres:
        rep = zone.representative_point()
        return [(rep.x, rep.y)]

    return centres


def generate_footprint_candidates_in_zone(
    zone: Polygon,
    building_height_m: float,
    min_width_m: float = MIN_FOOTPRINT_WIDTH_M,
    min_depth_m: float = MIN_FOOTPRINT_DEPTH_M,
    step_m: float = FOOTPRINT_GRID_STEP_M,
    max_side_m: float = MAX_FOOTPRINT_SIDE_M,
    top_n: int = 3,
) -> List[FootprintCandidate]:
    """
    Generate up to *top_n* footprint candidates for a zone, ordered by area
    (largest first).  Uses a grid over width×depth and a small grid of centre
    points so rectangles can slide inside the zone.

    Returns an empty list if no rectangle fits.
    """
    del building_height_m  # reserved for future use (e.g. height-dependent limits)

    if not zone.is_valid or zone.is_empty:
        return []
    if zone.area < MIN_FOOTPRINT_AREA_SQFT:
        return []

    orient = find_orientation(zone)
    prepared_zone = prep(zone)

    # Cap max dimensions from zone's rotated bbox (primary orientation)
    w_pri, d_pri = _rotated_bbox_dims(zone, orient.angle_primary_deg)
    max_width_dxf = min(w_pri, max_side_m * METRES_TO_DXF)
    max_depth_dxf = min(d_pri, max_side_m * METRES_TO_DXF)
    max_width_m = max(min_width_m, max_width_dxf * DXF_TO_METRES)
    max_depth_m = max(min_depth_m, max_depth_dxf * DXF_TO_METRES)

    if max_width_m < min_width_m or max_depth_m < min_depth_m:
        return []

    # Descending grids so we try largest rectangles first
    n_w = max(1, int(math.floor((max_width_m - min_width_m) / step_m)) + 1)
    n_d = max(1, int(math.floor((max_depth_m - min_depth_m) / step_m)) + 1)
    width_values = [max_width_m - i * step_m for i in range(n_w)]
    depth_values = [max_depth_m - j * step_m for j in range(n_d)]

    centres = _sample_centers(zone, prepared_zone, points_per_axis=3)

    candidates: List[FootprintCandidate] = []

    for width_m in width_values:
        if width_m < min_width_m:
            continue
        for depth_m in depth_values:
            if depth_m < min_depth_m:
                continue

            width_dxf = width_m * METRES_TO_DXF
            depth_dxf = depth_m * METRES_TO_DXF
            nominal_area_sqft = width_dxf * depth_dxf
            if nominal_area_sqft < MIN_FOOTPRINT_AREA_SQFT:
                continue

            for angle_deg, label in [
                (orient.angle_primary_deg, "PRIMARY"),
                (orient.angle_secondary_deg, "PERPENDICULAR"),
            ]:
                placed = False
                for cx, cy in centres:
                    rect = _rect_at_center(cx, cy, width_dxf, depth_dxf, angle_deg)
                    if not rect.is_valid or rect.is_empty:
                        continue
                    if not prepared_zone.contains(rect):
                        continue
                    if rect.area < MIN_FOOTPRINT_AREA_SQFT:
                        continue

                    area_sqft = rect.area
                    candidate = FootprintCandidate(
                        footprint_polygon=rect,
                        area_sqft=area_sqft,
                        width_dxf=width_dxf,
                        depth_dxf=depth_dxf,
                        width_m=width_m,
                        depth_m=depth_m,
                        orientation_angle_deg=angle_deg,
                        orientation_label=label,
                        grid_resolution_dxf=step_m * METRES_TO_DXF,
                        source_component_index=0,
                    )

                    candidates.append(candidate)
                    # Keep only the top_n by area
                    candidates.sort(key=lambda c: c.area_sqft, reverse=True)
                    if top_n > 0 and len(candidates) > top_n:
                        candidates = candidates[:top_n]

                    placed = True
                    break  # Don't search more centres for this size / angle

                # If we successfully placed at this size+angle, move on to next size
                # (smaller rectangles will be considered later in the grid anyway).
                # This keeps the search focused on large rectangles.
                # We don't early-break depth/width loops to avoid missing shapes
                # where only the perpendicular orientation fits.

    return candidates


def optimize_footprint_in_zone(
    zone: Polygon,
    building_height_m: float,
    min_width_m: float = MIN_FOOTPRINT_WIDTH_M,
    min_depth_m: float = MIN_FOOTPRINT_DEPTH_M,
    step_m: float = FOOTPRINT_GRID_STEP_M,
    max_side_m: float = MAX_FOOTPRINT_SIDE_M,
) -> Optional[FootprintCandidate]:
    """
    Find the largest valid tower footprint that fits entirely inside the zone
    by trying a grid of width × depth combinations.

    Parameters
    ----------
    zone                : Shapely Polygon (single zone) in DXF feet.
    building_height_m    : Building height in metres (for API consistency; spacing unchanged).
    min_width_m         : Minimum footprint width (m).
    min_depth_m         : Minimum footprint depth (m).
    step_m              : Grid step for width/depth (m).
    max_side_m          : Cap on max width/depth (m).

    Returns
    -------
    FootprintCandidate with largest area that fits inside zone, or None if none fit.
    """
    # Backwards-compatible wrapper: return only the single best candidate.
    candidates = generate_footprint_candidates_in_zone(
        zone=zone,
        building_height_m=building_height_m,
        min_width_m=min_width_m,
        min_depth_m=min_depth_m,
        step_m=step_m,
        max_side_m=max_side_m,
        top_n=1,
    )
    return candidates[0] if candidates else None
