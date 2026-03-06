"""
floor_skeleton/skeleton_builder.py
------------------------------------
Builds a FloorSkeleton for one CoreCandidate × pattern combination.

Pattern dispatch rules (plan §Step 2):

    DOUBLE_LOADED  — vertical core candidates only
                     Corridor centred at D/2; two symmetric unit bands.

    SINGLE_LOADED  — vertical core candidates only
                     Corridor adjacent to core at near edge (y=0 side);
                     single unit band above.

    END_CORE       — vertical OR horizontal core candidates
                     No corridor; single unit band fills remaining zone.

    Horizontal candidates (is_horizontal=True) are ALWAYS built as END_CORE
    regardless of the selected_pattern argument (plan §Improvement 3).

All polygons are Shapely boxes in the local metres frame (0,0)→(W,D).
Feasibility flags (is_geometry_valid, passes_min_unit_guard,
is_architecturally_viable) are left as False placeholders — they are
populated by skeleton_evaluator.py after the skeleton is built.
"""

from __future__ import annotations

from shapely.geometry import box as shapely_box

from placement_engine.geometry.core_fit import CoreDimensions
from floor_skeleton.models import (
    CoreCandidate,
    FloorSkeleton,
    UnitZone,
    AXIS_DEPTH_DOMINANT,
    AXIS_WIDTH_DOMINANT,
    NO_SKELETON_PATTERN,
    NO_SKELETON_LABEL,
)

# Pattern constants (mirror core_fit.py to avoid circular import)
PATTERN_DOUBLE = "DOUBLE_LOADED"
PATTERN_SINGLE = "SINGLE_LOADED"
PATTERN_END    = "END_CORE"


def build_skeleton(
    candidate:        CoreCandidate,
    selected_pattern: str,
    W:                float,
    D:                float,
    dims:             CoreDimensions,
) -> FloorSkeleton:
    """
    Build a FloorSkeleton for one CoreCandidate under the given pattern.

    Horizontal candidates always use END_CORE logic regardless of
    selected_pattern.

    Parameters
    ----------
    candidate        : CoreCandidate from core_placement_candidates.
    selected_pattern : Pattern from CoreValidationResult.selected_pattern.
    W                : Footprint width in metres.
    D                : Footprint depth in metres.
    dims             : CoreDimensions instance.

    Returns
    -------
    FloorSkeleton with geometry populated and feasibility flags all False
    (flags are set by skeleton_evaluator after build).
    """
    footprint = shapely_box(0, 0, W, D)

    if candidate.is_horizontal:
        return _build_horizontal_end_core(candidate, footprint, W, D)

    # Vertical core candidates
    if selected_pattern == PATTERN_DOUBLE:
        return _build_double_loaded(candidate, footprint, W, D, dims)
    if selected_pattern == PATTERN_SINGLE:
        return _build_single_loaded(candidate, footprint, W, D, dims)
    # END_CORE (default for any other pattern value)
    return _build_vertical_end_core(candidate, footprint, W, D)


# ── Pattern builders ───────────────────────────────────────────────────────────

def _build_vertical_end_core(
    candidate: CoreCandidate,
    footprint: object,
    W:         float,
    D:         float,
) -> FloorSkeleton:
    """
    END_CORE — vertical core strip, no corridor, single unit band.

    Core occupies one end of the width dimension (cpw × D).
    Unit zone fills the remaining width.
    """
    core_box = candidate.core_box
    cpw      = core_box.bounds[2] - core_box.bounds[0]   # xmax - xmin
    cx0      = core_box.bounds[0]
    cx1      = core_box.bounds[2]

    # Unit zone is on the opposite side of the core
    if cx0 == 0.0:
        # Core on left → unit zone on right
        unit_poly = shapely_box(cx1, 0, W, D)
    else:
        # Core on right or centre → unit zone on left (and right if CENTER_CORE)
        # CENTER_CORE is also passed here for END_CORE pattern — units split
        if cx0 > 0 and cx1 < W:
            # Centre: two unit zones
            unit_left  = shapely_box(0,   0, cx0, D)
            unit_right = shapely_box(cx1, 0, W,   D)
            unit_zones = [
                UnitZone(
                    band_id=0,
                    polygon=unit_left,
                    orientation_axis=AXIS_DEPTH_DOMINANT,
                    zone_width_m=round(cx0, 6),
                    zone_depth_m=round(D, 6),
                ),
                UnitZone(
                    band_id=1,
                    polygon=unit_right,
                    orientation_axis=AXIS_DEPTH_DOMINANT,
                    zone_width_m=round(W - cx1, 6),
                    zone_depth_m=round(D, 6),
                ),
            ]
        else:
            unit_poly = shapely_box(0, 0, cx0, D)
            unit_zones = [UnitZone(
                band_id=0,
                polygon=unit_poly,
                orientation_axis=AXIS_DEPTH_DOMINANT,
                zone_width_m=round(cx0, 6),
                zone_depth_m=round(D, 6),
            )]
        return _skeleton(candidate, footprint, core_box, None, unit_zones,
                         PATTERN_END, W, D)

    unit_zones = [UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_DEPTH_DOMINANT,
        zone_width_m=round(W - cpw, 6),
        zone_depth_m=round(D, 6),
    )]
    return _skeleton(candidate, footprint, core_box, None, unit_zones,
                     PATTERN_END, W, D)


def _build_single_loaded(
    candidate: CoreCandidate,
    footprint: object,
    W:         float,
    D:         float,
    dims:      CoreDimensions,
) -> FloorSkeleton:
    """
    SINGLE_LOADED — vertical core, corridor adjacent to core, single unit band.

    Layout (Y axis):
        y=0        corridor_m        D
        |--corridor--|----unit zone----|
    """
    core_box   = candidate.core_box
    cpw        = core_box.bounds[2] - core_box.bounds[0]
    cx0        = core_box.bounds[0]
    cx1        = core_box.bounds[2]
    corr       = dims.corridor_m

    # Corridor: x = [non-core start, W], y = [0, corr]
    if cx0 == 0.0:
        nc_x0 = cx1
    else:
        nc_x0 = 0.0

    corridor_poly = shapely_box(nc_x0, 0, W if cx0 == 0 else cx0, corr)
    unit_poly     = shapely_box(nc_x0, corr, W if cx0 == 0 else cx0, D)
    unit_w        = (W - cpw) if cx0 == 0 else cx0
    unit_d        = D - corr

    unit_zones = [UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_DEPTH_DOMINANT,
        zone_width_m=round(unit_w, 6),
        zone_depth_m=round(unit_d, 6),
    )]
    return _skeleton(candidate, footprint, core_box, corridor_poly, unit_zones,
                     PATTERN_SINGLE, W, D)


def _build_double_loaded(
    candidate: CoreCandidate,
    footprint: object,
    W:         float,
    D:         float,
    dims:      CoreDimensions,
) -> FloorSkeleton:
    """
    DOUBLE_LOADED — vertical core, corridor centred, two symmetric unit bands.

    Layout (Y axis):
        y=0    unit_A_depth    y0    y1    unit_B_depth    D
        |--Unit Zone A--|--Corridor--|--Unit Zone B--|
    where y0 = (D - corr)/2, y1 = y0 + corr.
    """
    core_box  = candidate.core_box
    cpw       = core_box.bounds[2] - core_box.bounds[0]
    cx0       = core_box.bounds[0]
    cx1       = core_box.bounds[2]
    corr      = dims.corridor_m

    y0 = (D - corr) / 2.0
    y1 = y0 + corr

    if cx0 == 0.0:
        nc_x0, nc_x1 = cx1, W
    else:
        nc_x0, nc_x1 = 0.0, cx0

    unit_w = nc_x1 - nc_x0
    unit_d = y0    # each half = (D - corr) / 2

    corridor_poly = shapely_box(nc_x0, y0, nc_x1, y1)
    unit_a        = shapely_box(nc_x0, 0,  nc_x1, y0)
    unit_b        = shapely_box(nc_x0, y1, nc_x1, D)

    unit_zones = [
        UnitZone(
            band_id=0,
            polygon=unit_a,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=round(unit_w, 6),
            zone_depth_m=round(unit_d, 6),
        ),
        UnitZone(
            band_id=1,
            polygon=unit_b,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=round(unit_w, 6),
            zone_depth_m=round(D - y1, 6),
        ),
    ]
    return _skeleton(candidate, footprint, core_box, corridor_poly, unit_zones,
                     PATTERN_DOUBLE, W, D)


def _build_horizontal_end_core(
    candidate: CoreCandidate,
    footprint: object,
    W:         float,
    D:         float,
) -> FloorSkeleton:
    """
    END_CORE (horizontal) — core strip at bottom or top, no corridor.

    Layout (Y axis, bottom-core variant):
        y=0   cpd          D
        |--CORE--|--UNIT ZONE--|
    """
    core_box = candidate.core_box
    cy0      = core_box.bounds[1]
    cy1      = core_box.bounds[3]
    cpd      = cy1 - cy0

    if cy0 == 0.0:
        # Core at bottom → unit zone above
        unit_poly  = shapely_box(0, cy1, W, D)
        zone_depth = D - cpd
    else:
        # Core at top → unit zone below
        unit_poly  = shapely_box(0, 0, W, cy0)
        zone_depth = cy0

    unit_zones = [UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_WIDTH_DOMINANT,
        zone_width_m=round(W, 6),
        zone_depth_m=round(zone_depth, 6),
    )]
    return _skeleton(candidate, footprint, core_box, None, unit_zones,
                     PATTERN_END, W, D)


# ── Assembly helper ────────────────────────────────────────────────────────────

def _skeleton(
    candidate:    CoreCandidate,
    footprint:    object,
    core_polygon: object,
    corridor:     object | None,
    unit_zones:   list[UnitZone],
    pattern:      str,
    W:            float,
    D:            float,
) -> FloorSkeleton:
    """Assemble a FloorSkeleton with all flags initialised to False."""
    return FloorSkeleton(
        footprint_polygon=footprint,
        core_polygon=core_polygon,
        corridor_polygon=corridor,
        unit_zones=unit_zones,
        pattern_used=pattern,
        placement_label=candidate.label,
        area_summary={},        # populated by skeleton_evaluator
        efficiency_ratio=0.0,   # populated by skeleton_evaluator
        is_geometry_valid=False,
        passes_min_unit_guard=False,
        is_architecturally_viable=False,
        audit_log=[],
    )
