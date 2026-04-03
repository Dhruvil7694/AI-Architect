"""
floorplan_engine/corridor/corridor_generator.py
-----------------------------------------------
Generate corridor geometry using centerline-buffer approach.

R1-3:  ``LineString.buffer(w/2).intersection(footprint)``
R2-2:  ``ensure_single_polygon`` guard after clipping.
R2-3:  Radial arm count for POINT_CORE from ``target_units_per_floor``.
R1-9:  Stores corridor centerline for future loading-mode decision.
R2-10: Uses stair positions (already placed) as corridor endpoints.
"""

from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import unary_union

from floorplan_engine.config import (
    DOUBLE_CORE,
    DOUBLE_CORRIDOR,
    POINT_CORE,
    SINGLE_CORRIDOR,
    CoreConfig,
    resolve_arm_count,
)
from floorplan_engine.geometry.polygon_utils import ensure_single_polygon


def generate_corridor(
    core_type: str,
    core_positions_m: list[tuple[float, float]],
    core_width_m: float,
    stair_centroids_m: list[tuple[float, float]],
    footprint_m: Polygon,
    footprint_length_m: float,
    footprint_width_m: float,
    target_units_per_floor: int,
    config: CoreConfig,
) -> tuple[Optional[Polygon], Optional[LineString | MultiLineString], float]:
    """
    Generate corridor polygon and centerline in local metres.

    Parameters
    ----------
    core_type : str
    core_positions_m : list of (l, s)
    core_width_m : float
    stair_centroids_m : list of (l, s) — stair centroids (R2-10)
    footprint_m : Polygon
    footprint_length_m, footprint_width_m : float
    target_units_per_floor : int — used for POINT_CORE arm count (R2-3)
    config : CoreConfig

    Returns
    -------
    (corridor_poly, centerline, corridor_length_m)
        corridor_poly: Shapely Polygon in local metres (or None)
        centerline: LineString / MultiLineString (or None)
        corridor_length_m: total corridor length in metres
    """
    hw = config.corridor_width / 2.0
    s_center = footprint_width_m / 2.0

    if core_type == POINT_CORE:
        return _point_core_corridor(
            core_positions_m[0], footprint_m,
            footprint_length_m, footprint_width_m,
            target_units_per_floor, hw, config,
        )

    if core_type == SINGLE_CORRIDOR:
        return _single_corridor(
            core_positions_m[0], core_width_m,
            stair_centroids_m, footprint_m,
            footprint_length_m, s_center, hw,
        )

    if core_type == DOUBLE_CORRIDOR:
        return _double_corridor(
            core_positions_m[0], core_width_m,
            stair_centroids_m, footprint_m,
            footprint_length_m, s_center, hw,
        )

    if core_type == DOUBLE_CORE:
        return _double_core_corridor(
            core_positions_m, core_width_m,
            footprint_m, s_center, hw,
        )

    return None, None, 0.0


# ── POINT_CORE — radial arms ────────────────────────────────────────────────

def _point_core_corridor(
    core_center: tuple[float, float],
    footprint_m: Polygon,
    length_m: float,
    width_m: float,
    target_units: int,
    hw: float,
    config: CoreConfig,
) -> tuple[Optional[Polygon], Optional[MultiLineString], float]:
    """
    R2-3: 2–4 radial arms from the core center along L and S axes.
    """
    n_arms = resolve_arm_count(target_units)
    cl, cs = core_center

    # Arm endpoints — extend to footprint edges along principal axes
    arms = []
    if n_arms >= 2:
        # Left and right along L axis
        arms.append(LineString([(cl, cs), (0, cs)]))
        arms.append(LineString([(cl, cs), (length_m, cs)]))
    if n_arms >= 3:
        # Up along S axis
        arms.append(LineString([(cl, cs), (cl, width_m)]))
    if n_arms >= 4:
        # Down along S axis
        arms.append(LineString([(cl, cs), (cl, 0)]))

    arm_polys = []
    valid_arms = []
    total_length = 0.0
    for arm in arms:
        raw = arm.buffer(hw, cap_style="flat")
        clipped = raw.intersection(footprint_m)
        poly = ensure_single_polygon(clipped)
        if poly is not None:
            arm_polys.append(poly)
            valid_arms.append(arm)
            total_length += arm.length

    if not arm_polys:
        return None, None, 0.0

    corridor_poly = ensure_single_polygon(unary_union(arm_polys))
    centerline = MultiLineString(valid_arms) if len(valid_arms) > 1 else valid_arms[0]

    return corridor_poly, centerline, total_length


# ── SINGLE_CORRIDOR ──────────────────────────────────────────────────────────

def _single_corridor(
    core_pos: tuple[float, float],
    core_width_m: float,
    stair_centroids: list[tuple[float, float]],
    footprint_m: Polygon,
    length_m: float,
    s_center: float,
    hw: float,
) -> tuple[Optional[Polygon], Optional[LineString], float]:
    """Core at one end → corridor extends one direction to far stair."""
    core_l = core_pos[0]
    # Corridor starts just past the core
    start_l = core_l + core_width_m / 2
    # Endpoint: the far stair or footprint end
    if stair_centroids and len(stair_centroids) >= 2:
        end_l = stair_centroids[1][0]
    else:
        end_l = length_m

    centerline = LineString([(start_l, s_center), (end_l, s_center)])
    raw = centerline.buffer(hw, cap_style="flat")
    clipped = raw.intersection(footprint_m)
    poly = ensure_single_polygon(clipped)

    return poly, centerline, centerline.length


# ── DOUBLE_CORRIDOR ──────────────────────────────────────────────────────────

def _double_corridor(
    core_pos: tuple[float, float],
    core_width_m: float,
    stair_centroids: list[tuple[float, float]],
    footprint_m: Polygon,
    length_m: float,
    s_center: float,
    hw: float,
) -> tuple[Optional[Polygon], Optional[LineString], float]:
    """Core at center → corridor extends both directions."""
    core_l = core_pos[0]
    half_core = core_width_m / 2

    # Left arm
    if stair_centroids:
        left_end = stair_centroids[0][0]
    else:
        left_end = 0
    # Right arm
    if len(stair_centroids) >= 2:
        right_end = stair_centroids[1][0]
    else:
        right_end = length_m

    centerline = LineString([
        (left_end, s_center),
        (core_l - half_core, s_center),
        (core_l + half_core, s_center),
        (right_end, s_center),
    ])
    raw = centerline.buffer(hw, cap_style="flat")
    clipped = raw.intersection(footprint_m)
    poly = ensure_single_polygon(clipped)

    total_len = (core_l - half_core - left_end) + (right_end - core_l - half_core)
    return poly, centerline, max(total_len, 0)


# ── DOUBLE_CORE ──────────────────────────────────────────────────────────────

def _double_core_corridor(
    core_positions: list[tuple[float, float]],
    core_width_m: float,
    footprint_m: Polygon,
    s_center: float,
    hw: float,
) -> tuple[Optional[Polygon], Optional[LineString], float]:
    """Two cores at ends → corridor connects them."""
    c0_l = core_positions[0][0] + core_width_m / 2
    c1_l = core_positions[1][0] - core_width_m / 2

    if c1_l <= c0_l:
        return None, None, 0.0

    centerline = LineString([(c0_l, s_center), (c1_l, s_center)])
    raw = centerline.buffer(hw, cap_style="flat")
    clipped = raw.intersection(footprint_m)
    poly = ensure_single_polygon(clipped)

    return poly, centerline, centerline.length
