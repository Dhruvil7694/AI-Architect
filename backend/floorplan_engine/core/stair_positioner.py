"""
floorplan_engine/core/stair_positioner.py
-----------------------------------------
Position staircases relative to core blocks and corridor endpoints.

R1-5:  Stairs at corridor endpoints, not flanking lifts.
R2-10: Runs BEFORE corridor generation so stair positions can inform
       corridor endpoint placement.

POINT_CORE is an exception — stairs are inside the core block and
positioned by ``core_layout.assemble_core_block``.
"""

from __future__ import annotations

import math

from shapely.geometry import Point, box

from floorplan_engine.config import (
    DOUBLE_CORE,
    DOUBLE_CORRIDOR,
    POINT_CORE,
    SINGLE_CORRIDOR,
    CoreConfig,
)


def position_stairs(
    core_type: str,
    core_positions_m: list[tuple[float, float]],
    core_depth_m: float,
    footprint_length_m: float,
    footprint_width_m: float,
    config: CoreConfig,
) -> tuple[list, list[tuple[float, float]], float, bool]:
    """
    Determine stair polygon positions in the local-metre frame.

    Parameters
    ----------
    core_type : str
        One of the four core-type constants.
    core_positions_m : list of (l, s)
        Core block centre positions from ``core_placer``.
    core_depth_m : float
        Depth of the core block (S-axis extent).
    footprint_length_m, footprint_width_m : float
        Footprint extents.
    config : CoreConfig
        Dimensional constants.

    Returns
    -------
    (stair_polys, stair_centroids, separation_m, separation_ok)
        stair_polys     — list of Shapely Polygons in local metres
        stair_centroids — list of (l, s) centroid tuples
        separation_m    — distance between stair centroids
        separation_ok   — whether separation ≥ 1/3 diagonal
    """
    sw = config.stair_width
    sd = config.stair_depth
    n_stairs = max(config.min_fire_stairs, 2)

    # S-center of corridor (centred on short axis)
    s_center = footprint_width_m / 2.0

    if core_type == POINT_CORE:
        # Stairs already in core block — return their approximate positions
        # relative to core centre for graph construction
        cl, cs = core_positions_m[0]
        s0 = (cl - sw / 2, cs)
        s1 = (cl + sw / 2, cs)
        polys = [
            box(s0[0] - sw / 2, s0[1] - sd / 2, s0[0] + sw / 2, s0[1] + sd / 2),
            box(s1[0] - sw / 2, s1[1] - sd / 2, s1[0] + sw / 2, s1[1] + sd / 2),
        ]
        centroids = [s0, s1]

    elif core_type == SINGLE_CORRIDOR:
        # Stair 0: adjacent to core (at L ~ core_position)
        core_l = core_positions_m[0][0]
        s0_l = core_l
        s0_s = s_center + config.corridor_width / 2 + sw / 2

        # Stair 1: at far end of L axis
        s1_l = footprint_length_m - sw / 2
        s1_s = s_center + config.corridor_width / 2 + sw / 2

        polys = [
            box(s0_l - sw / 2, s0_s - sd / 2, s0_l + sw / 2, s0_s + sd / 2),
            box(s1_l - sw / 2, s1_s - sd / 2, s1_l + sw / 2, s1_s + sd / 2),
        ]
        centroids = [(s0_l, s0_s), (s1_l, s1_s)]

    elif core_type == DOUBLE_CORRIDOR:
        # Stair at each end of the L axis
        s0_l = sw / 2
        s1_l = footprint_length_m - sw / 2
        s_pos = s_center + config.corridor_width / 2 + sw / 2

        polys = [
            box(s0_l - sw / 2, s_pos - sd / 2, s0_l + sw / 2, s_pos + sd / 2),
            box(s1_l - sw / 2, s_pos - sd / 2, s1_l + sw / 2, s_pos + sd / 2),
        ]
        centroids = [(s0_l, s_pos), (s1_l, s_pos)]

    elif core_type == DOUBLE_CORE:
        # One stair per core block, on the corridor-facing side
        c0_l, c0_s = core_positions_m[0]
        c1_l, c1_s = core_positions_m[1]

        # Stair 0: just inward of core A
        s0_l = c0_l + core_depth_m / 2 + sw / 2
        s0_s = s_center + config.corridor_width / 2 + sw / 2

        # Stair 1: just inward of core B
        s1_l = c1_l - core_depth_m / 2 - sw / 2
        s1_s = s0_s

        polys = [
            box(s0_l - sw / 2, s0_s - sd / 2, s0_l + sw / 2, s0_s + sd / 2),
            box(s1_l - sw / 2, s1_s - sd / 2, s1_l + sw / 2, s1_s + sd / 2),
        ]
        centroids = [(s0_l, s0_s), (s1_l, s1_s)]

    else:
        polys = []
        centroids = []

    # Compute separation
    if len(centroids) >= 2:
        c0, c1 = centroids[0], centroids[1]
        separation_m = math.hypot(c1[0] - c0[0], c1[1] - c0[1])
    else:
        separation_m = 0.0

    diagonal = math.hypot(footprint_length_m, footprint_width_m)
    required_sep = diagonal * config.stair_sep_ratio
    separation_ok = separation_m >= required_sep

    return polys, centroids, separation_m, separation_ok
