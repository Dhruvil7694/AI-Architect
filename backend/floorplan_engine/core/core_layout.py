"""
floorplan_engine/core/core_layout.py
------------------------------------
Assemble a core block from lifts + lobby (and optionally stairs for
POINT_CORE).

R2-7: core_width = max(lifts_width + 2 * wall_t, lobby_min_width)
       ensures adequate clearance even with a single lift.
"""

from __future__ import annotations

from shapely.geometry import box

from floorplan_engine.config import POINT_CORE, CoreConfig


def assemble_core_block(
    n_lifts_in_block: int,
    include_stairs: bool,
    config: CoreConfig,
) -> tuple:
    """
    Build a core block in a local (0, 0) frame.

    Parameters
    ----------
    n_lifts_in_block : int
        Number of lift shafts in this block.
    include_stairs : bool
        True only for POINT_CORE — places stairs flanking the lifts.
    config : CoreConfig
        Dimensional constants.

    Returns
    -------
    tuple of (core_poly, lift_polys, lobby_poly, stair_polys, core_w, core_d)
        All Shapely Polygons in local metres.
    """
    w = config.lift_shaft_w
    d = config.lift_shaft_d
    lifts_width = n_lifts_in_block * w

    stair_polys = []

    if include_stairs:
        # POINT_CORE: stairs flank the lifts
        # [ Stair | wall | Lifts... | wall | Stair ]
        sw = config.stair_width
        sd = config.stair_depth
        wt = config.wall_t

        core_width = sw + wt + lifts_width + wt + sw
        element_depth = max(sd, d)
        core_depth = config.lobby_min_depth + element_depth

        # Lobby at bottom, full width
        lobby_poly = box(0, 0, core_width, config.lobby_min_depth)

        # Stair 0 (left)
        stair_x0 = 0
        stair_y0 = config.lobby_min_depth
        stair_polys.append(box(stair_x0, stair_y0, stair_x0 + sw, stair_y0 + sd))

        # Lifts (centered vertically in element zone)
        lift_x0 = sw + wt
        lift_y0 = config.lobby_min_depth + (element_depth - d) / 2
        lift_polys = []
        for i in range(n_lifts_in_block):
            x = lift_x0 + i * w
            lift_polys.append(box(x, lift_y0, x + w, lift_y0 + d))

        # Stair 1 (right)
        stair_x1 = sw + wt + lifts_width + wt
        stair_polys.append(box(stair_x1, stair_y0, stair_x1 + sw, stair_y0 + sd))

    else:
        # Standard core: lifts above lobby, no stairs in block
        # R2-7: wall clearance around lifts
        core_width = max(lifts_width + 2 * config.wall_t, config.lobby_min_width)
        core_depth = config.lobby_min_depth + d

        # Lobby at bottom
        lobby_poly = box(0, 0, core_width, config.lobby_min_depth)

        # Lifts centered above lobby
        lift_x0 = (core_width - lifts_width) / 2
        lift_y0 = config.lobby_min_depth
        lift_polys = []
        for i in range(n_lifts_in_block):
            x = lift_x0 + i * w
            lift_polys.append(box(x, lift_y0, x + w, lift_y0 + d))

    # Core bounding box
    core_poly = box(0, 0, core_width, core_depth)

    return core_poly, lift_polys, lobby_poly, stair_polys, core_width, core_depth
