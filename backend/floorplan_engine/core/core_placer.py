"""
floorplan_engine/core/core_placer.py
------------------------------------
Determine where to place core block(s) within the footprint.

R2-1: Constrained placement — filters inscribed rectangle candidates
to avoid courtyards and wrong wings.  Falls back to a buffer-based
medial-axis approximation if no valid candidate exists.
"""

from __future__ import annotations

import logging
from typing import Optional

from shapely.geometry import Point, Polygon

from floorplan_engine.config import (
    DOUBLE_CORE,
    DOUBLE_CORRIDOR,
    POINT_CORE,
    SINGLE_CORRIDOR,
)

logger = logging.getLogger(__name__)


def find_core_positions(
    footprint_m: Polygon,
    core_type: str,
    core_width_m: float,
    core_depth_m: float,
    length_m: float,
    width_m: float,
) -> list[tuple[float, float]]:
    """
    Return (l_center, s_center) positions for core block(s) in local metres.

    The positions are along the L and S axes of the footprint frame:
    - L runs along the long axis (0 → length_m)
    - S runs along the short axis (0 → width_m)

    Parameters
    ----------
    footprint_m : Polygon
        Footprint in local metres frame.
    core_type : str
        One of the four core-type constants.
    core_width_m, core_depth_m : float
        Dimensions of the core block to place.
    length_m, width_m : float
        Footprint extents along L and S axes.

    Returns
    -------
    list of (l_center, s_center) tuples — one per core block.
    """
    s_center = width_m / 2.0   # always centered on short axis

    # Try inscribed-rectangle-based placement first (R2-1)
    best_l_center = _inscribed_rect_center(
        footprint_m, core_width_m, core_depth_m
    )

    if best_l_center is None:
        # Fallback: buffer-based medial axis approximation
        best_l_center = _medial_fallback(footprint_m, core_depth_m, length_m)

    if core_type == POINT_CORE:
        return [(best_l_center, s_center)]

    if core_type == SINGLE_CORRIDOR:
        # Core at one end (left end preferred)
        l_pos = core_width_m / 2.0
        return [(l_pos, s_center)]

    if core_type == DOUBLE_CORRIDOR:
        # Core at center
        return [(length_m / 2.0, s_center)]

    if core_type == DOUBLE_CORE:
        # Two cores at opposite ends
        margin = core_width_m / 2.0
        return [(margin, s_center), (length_m - margin, s_center)]

    return [(length_m / 2.0, s_center)]


def _inscribed_rect_center(
    footprint_m: Polygon,
    core_width_m: float,
    core_depth_m: float,
) -> Optional[float]:
    """
    R2-1: Find the L-axis center of the best inscribed rectangle that
    can actually hold the core block.

    Tries to import the existing ``find_top_n_inscribed_rects`` from
    the placement engine.  If unavailable, returns None (triggering
    the medial-axis fallback).

    Filters:
      - centroid must be inside footprint
      - centroid must be ≥ core_depth from boundary
      - rectangle must be at least core_width × core_depth
    """
    try:
        from placement_engine.geometry.inscribed_rectangle import (
            find_top_n_inscribed_rects,
        )
    except ImportError:
        logger.debug("inscribed_rectangle not available; using fallback")
        return None

    from common.units import METRES_TO_DXF

    # The inscribed rect finder expects DXF units — but our footprint
    # is already in metres.  We pass min dimensions in the same units.
    try:
        candidates = find_top_n_inscribed_rects(
            footprint_m,
            min_width_dxf=core_width_m,   # same scale (metres)
            min_depth_dxf=core_depth_m,
            n=10,
        )
    except Exception:
        logger.debug("inscribed_rectangle search failed; using fallback")
        return None

    if not candidates:
        return None

    # Filter candidates (R2-1)
    valid = []
    for cand in candidates:
        cx, cy = cand.centroid if hasattr(cand, 'centroid') else (
            (cand.bounds[0] + cand.bounds[2]) / 2,
            (cand.bounds[1] + cand.bounds[3]) / 2,
        ) if hasattr(cand, 'bounds') else (None, None)

        if cx is None:
            continue

        pt = Point(cx, cy)
        if not footprint_m.contains(pt):
            continue
        if footprint_m.boundary.distance(pt) < core_depth_m:
            continue

        # Check dimensions
        cand_w = getattr(cand, 'width_m', None)
        cand_d = getattr(cand, 'depth_m', None)
        if cand_w is not None and cand_d is not None:
            if cand_w < core_width_m or cand_d < core_depth_m:
                continue

        valid.append((cx, cand))

    if not valid:
        return None

    # Return L-coordinate of best (largest area) candidate
    best_cx = valid[0][0]
    return best_cx


def _medial_fallback(
    footprint_m: Polygon,
    core_depth_m: float,
    length_m: float,
) -> float:
    """
    Fallback core center: inward-buffer centroid, or simple midpoint.

    Buffers the footprint inward by ``core_depth_m`` and uses the
    centroid of the result — an approximation of the medial axis.
    """
    try:
        inner = footprint_m.buffer(-core_depth_m)
        if not inner.is_empty and inner.area > 0:
            c = inner.centroid
            return c.x  # L-coordinate in local frame
    except Exception:
        pass

    # Ultimate fallback: midpoint of L axis
    return length_m / 2.0
