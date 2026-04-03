"""
placement_engine/geometry/inscribed_rectangle.py
-------------------------------------------------
Finds the maximum-area axis-aligned inscribed rectangle inside a SINGLE
Shapely Polygon at a given orientation angle using:

  1. Rotate polygon by -angle so it becomes (approximately) axis-aligned
  2. Rasterize to a binary occupancy grid (adaptive resolution)
  3. Apply the Maximum Rectangle in Histogram DP algorithm
  4. Convert the grid-cell rectangle back to real coordinates
  5. Rotate +angle to restore original orientation
  6. Clip to the original polygon to handle rounding errors

This module operates ONLY on single Polygon objects.  MultiPolygon
decomposition is handled upstream by multipolygon_handler.py.

Grid resolution is chosen adaptively:
    resolution = clamp(bbox_max / TARGET_CELLS_PER_AXIS,
                       MIN_RESOLUTION_DXF, MAX_RESOLUTION_DXF)

This guarantees the grid is never larger than 200×200 = 40,000 cells,
keeping every DP pass well under 1 ms.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from placement_engine.geometry import (
    TARGET_CELLS_PER_AXIS,
    MIN_RESOLUTION_DXF,
    MAX_RESOLUTION_DXF,
    METRES_TO_DXF,
    DXF_TO_METRES,
    MIN_FOOTPRINT_AREA_SQFT,
    FootprintCandidate,
)
from placement_engine.geometry.orientation_finder import find_orientation

# Orientation sweep step — module-level so find_best_inscribed_rect and
# find_top_n_inscribed_rects use the identical sweep without duplicating the constant.
_SWEEP_STEP_DEG: int = 15   # 7 angles: 0°, 15°, 30°, 45°, 60°, 75°, 90°


# ── Public API ─────────────────────────────────────────────────────────────────

def find_top_n_inscribed_rects(
    polygon:       Polygon,
    min_width_dxf: float,
    min_depth_dxf: float,
    n:             int = 10,
    force_angle:   Optional[float] = None,
) -> list[FootprintCandidate]:
    """
    Return up to *n* rectangle candidates sorted by area descending.

    This is the multi-candidate companion to find_best_inscribed_rect.  The
    same 7-angle orientation sweep (0°–90° in 15° steps anchored at the MBR
    primary angle) is applied; all valid candidates are collected, sorted by
    area, and the top-N returned.

    The scorer (placement_engine.scoring.placement_scorer) consumes this list
    to select the architecturally best candidate instead of the purely largest.

    Parameters
    ----------
    polygon       : Shapely Polygon (single, valid).
    min_width_dxf : Minimum acceptable width (DXF feet).
    min_depth_dxf : Minimum acceptable depth (DXF feet).
    n             : Maximum candidates to return (default 10).
    force_angle   : If given, only test this angle (COL_WISE / DIAG_WISE mode).

    Returns
    -------
    List of FootprintCandidate sorted by area descending.  May be empty.
    """
    if not polygon.is_valid or polygon.is_empty or polygon.area < MIN_FOOTPRINT_AREA_SQFT:
        return []

    if force_angle is not None:
        c = find_inscribed_rect(polygon, force_angle, "FORCED", min_width_dxf, min_depth_dxf)
        return [c] if c is not None else []

    orient = find_orientation(polygon)
    candidates: list[FootprintCandidate] = []

    for offset in range(0, 91, _SWEEP_STEP_DEG):
        angle = orient.angle_primary_deg + offset
        if offset == 0:
            label = "PRIMARY"
        elif offset == 90:
            label = "PERPENDICULAR"
        else:
            label = f"ROTATED_{offset}"
        c = find_inscribed_rect(polygon, angle, label, min_width_dxf, min_depth_dxf)
        if c is not None:
            candidates.append(c)

    candidates.sort(key=lambda c: -c.area_sqft)
    return candidates[:n]


def find_inscribed_rect(
    polygon:       Polygon,
    angle_deg:     float,
    orientation_label: str,
    min_width_dxf: float,
    min_depth_dxf: float,
) -> Optional[FootprintCandidate]:
    """
    Find the maximum inscribed rectangle inside *polygon* at *angle_deg*.

    Parameters
    ----------
    polygon           : Shapely Polygon (single, valid)
    angle_deg         : Rotation angle; the MBR edge direction to align to x-axis.
    orientation_label : "PRIMARY" or "PERPENDICULAR" — stored in the candidate.
    min_width_dxf     : Minimum width of the result rectangle (DXF feet).
    min_depth_dxf     : Minimum depth of the result rectangle (DXF feet).

    Returns
    -------
    FootprintCandidate, or None if no rectangle satisfying minimums was found.
    """
    if not polygon.is_valid or polygon.is_empty:
        return None
    if polygon.area < MIN_FOOTPRINT_AREA_SQFT:
        return None

    resolution = _adaptive_resolution(polygon)

    # Work in rotated (axis-aligned) space
    rotated = rotate(polygon, -angle_deg, origin="centroid", use_radians=False)
    minx, miny, maxx, maxy = rotated.bounds

    # Build grid
    cols = max(1, int(math.ceil((maxx - minx) / resolution)))
    rows = max(1, int(math.ceil((maxy - miny) / resolution)))

    # Cap grid to avoid any edge-case blowup
    cols = min(cols, TARGET_CELLS_PER_AXIS + 10)
    rows = min(rows, TARGET_CELLS_PER_AXIS + 10)

    grid = _rasterize(rotated, minx, miny, resolution, cols, rows)

    best = _max_rect_in_grid(grid, resolution)
    if best is None:
        return None

    best_row, best_col, rect_w_cells, rect_h_cells = best

    rect_w = rect_w_cells * resolution   # width along x-axis (cols) in DXF feet
    rect_h = rect_h_cells * resolution   # height along y-axis (rows) in DXF feet

    # Map cell indices back to DXF coordinates in rotated space
    x0 = minx + best_col * resolution
    y0 = miny + best_row * resolution
    x1 = x0 + rect_w
    y1 = y0 + rect_h

    rect_rotated = box(x0, y0, x1, y1)

    # Rotate back to original orientation
    rect_original = rotate(rect_rotated, angle_deg, origin="centroid", use_radians=False)

    # Clip to polygon to handle floating-point rounding
    clipped = rect_original.intersection(polygon)
    if clipped.is_empty or not hasattr(clipped, "exterior"):
        return None

    # Use the clipped bounds for final dimensions (more accurate than cell counts)
    clipped_minx, clipped_miny, clipped_maxx, clipped_maxy = clipped.bounds
    final_w = clipped_maxx - clipped_minx
    final_h = clipped_maxy - clipped_miny

    # Map width/depth to the orientation frame
    # "width" = dimension along angle_deg, "depth" = perpendicular
    # After clipping we may lose orientation info from the bounding box,
    # so use the original rect_w / rect_h which are orientation-aware.
    width_dxf = rect_w
    depth_dxf = rect_h

    if width_dxf < min_width_dxf or depth_dxf < min_depth_dxf:
        # Try swapping — the grid DP gives axis-aligned dims, orientation frame may differ
        if rect_h >= min_width_dxf and rect_w >= min_depth_dxf:
            width_dxf, depth_dxf = rect_h, rect_w
        else:
            return None

    area_sqft = clipped.area
    if area_sqft < MIN_FOOTPRINT_AREA_SQFT:
        return None

    # Use the *unclipped* rotated rectangle as the footprint for clean geometry
    # (clipping can produce non-rectangular shapes at float boundaries)
    return FootprintCandidate(
        footprint_polygon=rect_original,
        area_sqft=area_sqft,
        width_dxf=width_dxf,
        depth_dxf=depth_dxf,
        width_m=width_dxf * DXF_TO_METRES,
        depth_m=depth_dxf * DXF_TO_METRES,
        orientation_angle_deg=angle_deg,
        orientation_label=orientation_label,
        grid_resolution_dxf=resolution,
        source_component_index=0,
    )


def find_best_inscribed_rect(
    polygon:       Polygon,
    min_width_dxf: float,
    min_depth_dxf: float,
    force_angle:   Optional[float] = None,
) -> Optional[FootprintCandidate]:
    """
    Find the maximum inscribed rectangle by sweeping orientations and returning
    the globally best result.

    Selection rules (in order):
      1. Larger footprint area wins.
      2. Tie: aspect ratio closer to 2:1 wins.
      3. Tie: smaller angle_deg wins (deterministic absolute tie-break).

    Orientation strategy
    --------------------
    Delegates to find_top_n_inscribed_rects (same 7-angle sweep, 0°–90° in
    15° steps) and applies the three-rule _select_winner reduction to choose
    the single best candidate.

    When force_angle is given (COL_WISE / DIAG_WISE packing), only that angle
    is tested.

    Parameters
    ----------
    polygon       : Shapely Polygon
    min_width_dxf : Minimum acceptable width (DXF feet)
    min_depth_dxf : Minimum acceptable depth (DXF feet)
    force_angle   : If given, only test this angle.

    Returns
    -------
    Best FootprintCandidate, or None.
    """
    # Collect all candidates from the sweep (or single forced angle)
    candidates = find_top_n_inscribed_rects(
        polygon=polygon,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        n=100,            # effectively unbounded — we want all angles
        force_angle=force_angle,
    )

    # Apply the original three-rule tie-breaking reduction
    best: Optional[FootprintCandidate] = None
    for candidate in candidates:
        best = _select_winner(best, candidate)
    return best


# ── Internal helpers ───────────────────────────────────────────────────────────

def _adaptive_resolution(polygon: Polygon) -> float:
    """Compute an adaptive grid resolution based on the polygon bounding box."""
    minx, miny, maxx, maxy = polygon.bounds
    bbox_max = max(maxx - minx, maxy - miny)
    if bbox_max <= 0:
        return MIN_RESOLUTION_DXF
    resolution = bbox_max / TARGET_CELLS_PER_AXIS
    return max(MIN_RESOLUTION_DXF, min(MAX_RESOLUTION_DXF, resolution))


def _rasterize(
    polygon:    Polygon,
    minx:       float,
    miny:       float,
    resolution: float,
    cols:       int,
    rows:       int,
) -> np.ndarray:
    """
    Build a boolean occupancy grid.  grid[row][col] = 1 if the cell centre
    is inside *polygon*, else 0.  Row 0 is the BOTTOM of the bounding box.

    Uses a fully vectorised approach: build a flat (rows*cols) array of cell
    centres, call shapely's batch contains once, then reshape.  This is
    20-50x faster than the previous Python double-loop, making multi-angle
    rotation sweeps practical.
    """
    col_indices = np.arange(cols)
    row_indices = np.arange(rows)
    cx = minx + (col_indices + 0.5) * resolution   # shape (cols,)
    cy = miny + (row_indices + 0.5) * resolution   # shape (rows,)

    # Build flat coordinate arrays for all cell centres: shape (rows*cols,)
    gx, gy = np.meshgrid(cx, cy)          # both shape (rows, cols)
    flat_x = gx.ravel()
    flat_y = gy.ravel()

    # Try shapely 2.x vectorised API first (fastest); fall back to 1.x.
    try:
        import shapely
        mask = shapely.contains_xy(polygon, flat_x, flat_y)
    except AttributeError:
        # shapely < 2.0: use vectorized module
        try:
            from shapely.vectorized import contains as _vec_contains
            mask = _vec_contains(polygon, flat_x, flat_y)
        except Exception:
            # Final fallback: prepared-geometry row-by-row loop
            from shapely.prepared import prep
            from shapely.geometry import Point
            prepared = prep(polygon)
            mask = np.array(
                [prepared.contains(Point(float(x), float(y)))
                 for x, y in zip(flat_x, flat_y)],
                dtype=bool,
            )

    grid = mask.reshape(rows, cols).astype(np.int32)
    return grid


def _max_rect_in_grid(
    grid: np.ndarray,
    resolution: float,
) -> Optional[tuple[int, int, int, int]]:
    """
    Maximum Rectangle in a Binary Matrix using the histogram DP approach.

    Returns (bottom_row, left_col, width_cells, height_cells) of the largest
    all-1 rectangle, or None if no cell is set.

    Time complexity: O(rows × cols).

    Optimisations vs. the naïve implementation:
    - Histogram height update is vectorised with np.where (no Python column loop).
    - The histogram is converted to a Python list before the stack pass since
      Python list indexing in a tight loop is faster than numpy scalar access.
    """
    rows, cols = grid.shape
    if rows == 0 or cols == 0:
        return None

    heights = np.zeros(cols, dtype=np.int32)

    best_area = 0
    best: Optional[tuple[int, int, int, int]] = None

    for r in range(rows):
        # Vectorised height update: increment where occupied, reset elsewhere.
        heights = np.where(grid[r] == 1, heights + 1, 0)

        # Convert to Python list — faster for the tight stack loop below.
        h_list: list[int] = heights.tolist()

        # Largest rectangle in histogram for this row (stack-based O(n)).
        result = _largest_rect_in_histogram(h_list, r)
        if result is not None:
            area_cells = result[2] * result[3]
            if area_cells > best_area:
                best_area = area_cells
                best = result

    return best


def _largest_rect_in_histogram(
    heights: list[int],
    current_row: int,
) -> Optional[tuple[int, int, int, int]]:
    """
    Classic stack-based O(n) algorithm.

    Accepts a plain Python list for heights (faster index access in tight loop).

    Returns (bottom_row, left_col, width_cells, height_cells) for the
    largest rectangle ending at *current_row*, or None.
    """
    n = len(heights)
    stack: list[int] = []   # indices into heights
    best_area = 0
    best: Optional[tuple[int, int, int, int]] = None

    for i in range(n + 1):
        h = heights[i] if i < n else 0
        while stack and heights[stack[-1]] > h:
            height = heights[stack.pop()]
            left = stack[-1] + 1 if stack else 0
            width = i - left
            area = width * height
            if area > best_area:
                best_area = area
                best = (current_row - height + 1, left, width, height)
        stack.append(i)

    return best


def _select_winner(
    a: Optional[FootprintCandidate],
    b: Optional[FootprintCandidate],
) -> Optional[FootprintCandidate]:
    """
    Select the better of two candidates using the deterministic three-rule
    priority: area → aspect ratio closeness to 2:1 → smaller angle.
    """
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a

    if a.area_sqft != b.area_sqft:
        return a if a.area_sqft > b.area_sqft else b

    # Tie on area: prefer aspect ratio closer to 2:1
    if a.aspect_ratio_score != b.aspect_ratio_score:
        return a if a.aspect_ratio_score < b.aspect_ratio_score else b

    # Absolute tie-break: smaller angle is more stable
    return a if a.orientation_angle_deg <= b.orientation_angle_deg else b
