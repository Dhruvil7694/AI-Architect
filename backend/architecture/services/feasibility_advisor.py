"""
architecture.services.feasibility_advisor
------------------------------------------

Lightweight pre-computation that determines what's feasible for a given plot
BEFORE the user commits to a full pipeline run.

Returns a FeasibilityMap:
  - For each tower count (1-N): min/max feasible floors, estimated footprint
  - Max feasible tower count
  - Floor plan compatibility per tower count
  - Regulatory limits (height cap, FSI cap, GC cap)

Design constraint: must complete in < 2 seconds. Skips skeleton/layout/rules
pipeline; only runs envelope + placement checks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from tp_ingestion.models import Plot

from envelope_engine.services.envelope_service import compute_envelope
from placement_engine.services.placement_service import compute_placement
from placement_engine.geometry import (
    METRES_TO_DXF,
    DXF_TO_METRES,
    MIN_FOOTPRINT_WIDTH_M,
    MIN_FOOTPRINT_DEPTH_M,
)
from architecture.regulatory_accessors import (
    get_max_permissible_height_by_road_width,
    get_max_fsi,
    get_max_ground_coverage_pct,
)
from architecture.spatial.road_edge_detector import (
    detect_road_edges_with_meta,
    select_governing_road_edges,
)
from common.units import sqft_to_sqm

logger = logging.getLogger(__name__)

# ── Height-adaptive min widths (same as development_optimizer) ────────────────
_LIFT_THRESHOLD_M = 10.0
_HIGHRISE_THRESHOLD_M = 15.0
_NO_LIFT_ARCH_MIN_W = 4.65
_LIFT_ARCH_MIN_W = 6.36
_HIGHRISE_ARCH_MIN_W = 7.36
_ARCH_MIN_DEPTH = 3.7


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class TowerFeasibility:
    """Feasibility assessment for a specific tower count."""
    n_towers: int
    is_feasible: bool
    min_floors: int = 0
    max_floors: int = 0
    estimated_footprint_sqm: float = 0.0  # per tower
    estimated_fsi_at_max: float = 0.0     # capped at max_fsi
    height_band: str = ""  # LOW_RISE / MID_RISE / HIGH_RISE at max floors
    floor_plan_notes: List[str] = field(default_factory=list)
    floor_plan_compat: Optional[FloorPlanCompatibility] = None
    reason: str = ""  # why infeasible, if not feasible
    # Actual footprint dimensions from placement (not estimated from sqrt)
    footprint_width_m: float = 0.0
    footprint_depth_m: float = 0.0


@dataclass
class FloorPlanCompatibility:
    """What floor plan configurations are possible for a footprint."""
    can_fit_1bhk: bool = False
    can_fit_2bhk: bool = False
    can_fit_3bhk: bool = False
    can_fit_4bhk: bool = False
    can_fit_5bhk: bool = False
    estimated_units_per_floor: int = 0
    min_unit_width_m: float = 0.0
    footprint_width_m: float = 0.0
    footprint_depth_m: float = 0.0
    core_type: str = ""  # "END_CORE" / "SINGLE_CORE" / "DOUBLE_CORE"
    notes: List[str] = field(default_factory=list)


@dataclass
class FeasibilityMap:
    """Complete feasibility analysis for a plot."""
    plot_id: str
    plot_area_sqm: float

    # Regulatory limits
    max_height_m: float
    max_floors: int
    max_fsi: float
    max_gc_pct: float
    road_width_m: float

    # Per-tower-count feasibility
    tower_options: List[TowerFeasibility] = field(default_factory=list)
    max_feasible_towers: int = 0

    # Best recommendation
    recommended_towers: int = 0
    recommended_floors: int = 0
    recommendation_reason: str = ""

    # AI-generated suggestions (populated separately)
    suggestions: List[str] = field(default_factory=list)

    # Floor plan compatibility for the recommended config
    floor_plan_compat: Optional[FloorPlanCompatibility] = None

    # New input constraints
    permissible_building_types: List[dict] = field(default_factory=list)
    core_configs: List[dict] = field(default_factory=list)
    sellable_estimate: Optional[dict] = None


# ── Floor plan compatibility estimation ───────────────────────────────────────

# Approximate unit widths (metres along corridor) from the unit library
_UNIT_MIN_WIDTHS = {
    "1BHK": 3.0,
    "2BHK": 4.0,
    "3BHK": 5.5,
    "4BHK": 7.0,
    "5BHK": 9.0,
}

# Approximate minimum unit depths (metres perpendicular to corridor)
_UNIT_MIN_DEPTHS = {
    "1BHK": 3.0,
    "2BHK": 3.5,
    "3BHK": 4.0,
    "4BHK": 4.5,
    "5BHK": 5.0,
}

# Approximate unit areas (sqm) from the unit library
_UNIT_AREAS = {
    "1BHK": 30.0,
    "2BHK": 55.0,
    "3BHK": 85.0,
    "4BHK": 120.0,
    "5BHK": 160.0,
}


def _estimate_floor_plan_compat(
    footprint_width_m: float,
    footprint_depth_m: float,
    height_m: float,
) -> FloorPlanCompatibility:
    """Estimate what floor plan configurations fit in a footprint."""
    # Ensure width is the shorter dimension (perpendicular to corridor)
    # and depth is the longer dimension (corridor runs along it)
    short = min(footprint_width_m, footprint_depth_m)
    long = max(footprint_width_m, footprint_depth_m)

    # Core type depends on height
    if height_m <= _LIFT_THRESHOLD_M:
        core_type = "END_CORE"
        core_width = 1.53  # no lift
        core_depth = 3.6
    elif height_m <= _HIGHRISE_THRESHOLD_M:
        core_type = "SINGLE_CORE"
        core_width = 3.26  # 1 stair + lift
        core_depth = 3.6
    else:
        core_type = "DOUBLE_CORE"
        core_width = 4.26  # 2 stairs + lift
        core_depth = 3.6

    # Corridor runs along the long axis; core is at one end
    corridor_length = long - core_depth
    if corridor_length < 0:
        corridor_length = 0

    # For END_CORE: units on one side of corridor only
    # For SINGLE/DOUBLE: units on both sides
    has_two_sides = core_type != "END_CORE"

    # Unit depth = (short - corridor_width) / sides
    # Corridor is typically 1.5-2.0m wide
    corridor_width_m = 1.5 if core_type == "END_CORE" else 1.8
    if has_two_sides:
        unit_depth = (short - corridor_width_m) / 2.0
    else:
        unit_depth = short - core_width - corridor_width_m

    # Effective corridor length for placing units
    effective_corridor = corridor_length * (2.0 if has_two_sides else 1.0)

    notes: list[str] = []
    can_fit: dict[str, bool] = {}

    for unit_type, min_w in _UNIT_MIN_WIDTHS.items():
        min_d = _UNIT_MIN_DEPTHS[unit_type]
        can_fit[unit_type] = (
            corridor_length >= min_w  # enough room along corridor for one unit
            and unit_depth >= min_d   # enough depth for the unit type
            and short >= (core_width + 2.0)  # footprint wide enough for core + some space
        )

    # Estimate total units per floor using 2BHK as baseline
    if effective_corridor > 0 and unit_depth >= 3.0:
        avg_unit_width = 4.0  # 2BHK baseline
        est_units = max(1, int(effective_corridor / avg_unit_width))
    else:
        est_units = 0
        notes.append("Footprint too narrow for standard unit layouts")

    if short < 8.0:
        notes.append(f"Footprint width {short:.1f}m limits unit mix to compact types")
    if long < 12.0:
        notes.append(f"Footprint depth {long:.1f}m limits corridor and unit count")

    return FloorPlanCompatibility(
        can_fit_1bhk=can_fit.get("1BHK", False),
        can_fit_2bhk=can_fit.get("2BHK", False),
        can_fit_3bhk=can_fit.get("3BHK", False),
        can_fit_4bhk=can_fit.get("4BHK", False),
        can_fit_5bhk=can_fit.get("5BHK", False),
        estimated_units_per_floor=est_units,
        min_unit_width_m=min(_UNIT_MIN_WIDTHS.values()),
        footprint_width_m=round(short, 1),
        footprint_depth_m=round(long, 1),
        core_type=core_type,
        notes=notes,
    )


# ── Main feasibility computation ─────────────────────────────────────────────


def compute_feasibility_map(
    plot: Plot,
    storey_height_m: float = 3.0,
    max_tower_check: int = 4,
) -> FeasibilityMap:
    """
    Compute a lightweight feasibility map for a plot.

    This is designed to be FAST (< 2s) — no skeleton, layout, or rules checks.
    Only envelope + placement geometry is tested.
    """
    road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    plot_area_sqm = float(plot.plot_area_sqm)
    plot_area_sqft = float(plot.plot_area_sqft)
    plot_geom = plot.geom

    max_fsi = get_max_fsi()

    result = FeasibilityMap(
        plot_id=f"{plot.tp_scheme}-{plot.fp_number}",
        plot_area_sqm=plot_area_sqm,
        max_height_m=0.0,
        max_floors=0,
        max_fsi=max_fsi,
        max_gc_pct=get_max_ground_coverage_pct(),
        road_width_m=road_width,
    )

    if road_width <= 0.0:
        result.suggestions = ["Plot has no road width data — cannot compute feasibility."]
        return result

    # Regulatory height cap
    h_road_cap = get_max_permissible_height_by_road_width(road_width)
    if h_road_cap <= 0:
        result.suggestions = [
            f"No height cap found for road width {road_width}m — plot may not be developable."
        ]
        return result

    max_floors = int(h_road_cap / storey_height_m)
    result.max_height_m = h_road_cap
    result.max_floors = max_floors

    # Detect road edges
    road_edges, _ = detect_road_edges_with_meta(plot_geom, None)
    road_edges, _ = select_governing_road_edges(plot_geom, road_edges)

    # Test feasibility at a few representative heights
    test_heights = set()
    test_heights.add(max_floors)

    for threshold_m in [_LIFT_THRESHOLD_M, _HIGHRISE_THRESHOLD_M]:
        threshold_floors = int(threshold_m / storey_height_m)
        if 1 <= threshold_floors <= max_floors:
            test_heights.add(threshold_floors)
            if threshold_floors + 1 <= max_floors:
                test_heights.add(threshold_floors + 1)

    test_heights.add(min(3, max_floors))
    test_heights.add(max(1, max_floors // 2))

    sorted_test_floors = sorted(test_heights, reverse=True)

    # For each tower count, find feasibility across tested heights
    best_solution = None
    best_fsi = -1.0

    for n_towers in range(1, max_tower_check + 1):
        tower_feas = TowerFeasibility(
            n_towers=n_towers,
            is_feasible=False,
        )

        feasible_floors: list[int] = []
        best_footprint_sqm = 0.0
        best_fsi_for_n = 0.0
        best_fp_width_m = 0.0
        best_fp_depth_m = 0.0

        for test_floor_count in sorted_test_floors:
            if test_floor_count < 1:
                continue

            height_m = test_floor_count * storey_height_m

            # Height-adaptive min dimensions
            if height_m <= _LIFT_THRESHOLD_M:
                eff_min_width = min(MIN_FOOTPRINT_WIDTH_M, _NO_LIFT_ARCH_MIN_W)
            elif height_m <= _HIGHRISE_THRESHOLD_M:
                eff_min_width = max(MIN_FOOTPRINT_WIDTH_M, _LIFT_ARCH_MIN_W)
            else:
                eff_min_width = max(MIN_FOOTPRINT_WIDTH_M, _HIGHRISE_ARCH_MIN_W)
            eff_min_depth = max(MIN_FOOTPRINT_DEPTH_M, _ARCH_MIN_DEPTH)

            # Envelope check
            try:
                env = compute_envelope(
                    plot_wkt=plot_geom.wkt,
                    building_height=height_m,
                    road_width=road_width,
                    road_facing_edges=road_edges,
                    enforce_gc=True,
                )
            except Exception:
                continue

            if env.status != "VALID" or env.envelope_polygon is None:
                continue

            # Placement check (quick — no spatial planner, just legacy packer)
            try:
                placement = compute_placement(
                    envelope_wkt=env.envelope_polygon.wkt,
                    building_height_m=height_m,
                    n_towers=n_towers,
                    min_width_m=eff_min_width,
                    min_depth_m=eff_min_depth,
                    use_spatial_planner=False,  # fast path
                )
            except Exception:
                continue

            if placement.status == "VALID" and placement.n_towers_placed >= n_towers:
                feasible_floors.append(test_floor_count)

                # Track best footprint — use ACTUAL dimensions from placement
                if placement.footprints:
                    avg_fp = sum(
                        sqft_to_sqm(float(fp.area_sqft or 0.0))
                        for fp in placement.footprints
                    ) / len(placement.footprints)

                    # Get actual width/depth from the first footprint
                    fp0 = placement.footprints[0]
                    fp_w = float(getattr(fp0, "width_m", 0.0) or 0.0)
                    fp_d = float(getattr(fp0, "depth_m", 0.0) or 0.0)

                    if avg_fp > best_footprint_sqm:
                        best_footprint_sqm = avg_fp
                        best_fp_width_m = fp_w
                        best_fp_depth_m = fp_d

                # Estimate FSI — CAPPED at regulatory max
                total_fp_sqft = sum(
                    float(fp.area_sqft or 0.0) for fp in placement.footprints
                )
                est_bua_sqft = total_fp_sqft * test_floor_count
                est_fsi = est_bua_sqft / plot_area_sqft if plot_area_sqft > 0 else 0.0
                est_fsi = min(est_fsi, max_fsi)  # CAP at regulatory max FSI

                if est_fsi > best_fsi_for_n:
                    best_fsi_for_n = est_fsi

        if feasible_floors:
            tower_feas.is_feasible = True
            tower_feas.min_floors = min(feasible_floors)
            tower_feas.max_floors = max(feasible_floors)
            tower_feas.estimated_footprint_sqm = round(best_footprint_sqm, 1)
            tower_feas.estimated_fsi_at_max = round(best_fsi_for_n, 2)
            tower_feas.footprint_width_m = round(best_fp_width_m, 1)
            tower_feas.footprint_depth_m = round(best_fp_depth_m, 1)

            max_h = tower_feas.max_floors * storey_height_m
            if max_h <= _LIFT_THRESHOLD_M:
                tower_feas.height_band = "LOW_RISE"
            elif max_h <= _HIGHRISE_THRESHOLD_M:
                tower_feas.height_band = "MID_RISE"
            else:
                tower_feas.height_band = "HIGH_RISE"

            # Floor plan compatibility using ACTUAL footprint dimensions
            fp_w = best_fp_width_m if best_fp_width_m > 0 else (math.sqrt(best_footprint_sqm) * 0.8 if best_footprint_sqm > 0 else 0)
            fp_d = best_fp_depth_m if best_fp_depth_m > 0 else (math.sqrt(best_footprint_sqm) * 1.2 if best_footprint_sqm > 0 else 0)

            fp_compat = _estimate_floor_plan_compat(
                footprint_width_m=fp_w,
                footprint_depth_m=fp_d,
                height_m=max_h,
            )
            tower_feas.floor_plan_compat = fp_compat
            tower_feas.floor_plan_notes = fp_compat.notes

            # Track overall best (by FSI)
            if best_fsi_for_n > best_fsi:
                best_fsi = best_fsi_for_n
                best_solution = (n_towers, tower_feas.max_floors)
        else:
            tower_feas.reason = (
                f"Cannot fit {n_towers} tower(s) within envelope at any tested height"
            )

        result.tower_options.append(tower_feas)

    # Determine max feasible towers
    result.max_feasible_towers = max(
        (t.n_towers for t in result.tower_options if t.is_feasible),
        default=0,
    )

    # Set recommendation
    if best_solution:
        result.recommended_towers = best_solution[0]
        result.recommended_floors = best_solution[1]
        best_opt = next(
            (t for t in result.tower_options if t.n_towers == best_solution[0]),
            None,
        )
        if best_opt:
            result.recommendation_reason = (
                f"{best_solution[0]} tower(s) at {best_solution[1]} floors "
                f"(estimated FSI: {best_opt.estimated_fsi_at_max:.2f}, "
                f"footprint: ~{best_opt.estimated_footprint_sqm:.0f} sqm/tower)"
            )
            result.floor_plan_compat = best_opt.floor_plan_compat

    # ── Populate new input constraints ───────────────────────────────────
    from architecture.models.building_types import get_permissible_building_types
    from architecture.models.core_config import get_core_configs
    from architecture.models.sellable_area import compute_sellable_area

    pbt = get_permissible_building_types(road_width_m=road_width, storey_height_m=storey_height_m)
    result.permissible_building_types = [
        {
            "id": bt.id,
            "label": bt.label,
            "effectiveMaxFloors": bt.effective_max_floors,
            "maxHeightM": bt.max_height_m,
            "liftRequired": bt.lift_required,
            "fireStairRequired": bt.fire_stair_required,
            "copRequired": bt.cop_required,
            "typicalEfficiency": bt.typical_efficiency_ratio,
        }
        for bt in pbt
    ]

    result.core_configs = [
        {
            "unitsPerCore": cc.units_per_core,
            "segment": cc.segment,
            "label": cc.label,
            "preferredPattern": cc.preferred_pattern,
        }
        for cc in get_core_configs()
    ]

    # Sellable estimate using best FSI
    if best_fsi > 0:
        plot_area_yards = plot_area_sqm * 1.19599  # sqm to sq yards
        sellable = compute_sellable_area(
            plot_area_sq_yards=plot_area_yards,
            achieved_fsi=best_fsi,
        )
        result.sellable_estimate = {
            "achievedFsi": best_fsi,
            "sellablePerYard": sellable.sellable_per_yard,
            "totalSellableSqft": sellable.total_sellable_sqft,
            "efficiencyRatio": sellable.efficiency_ratio,
        }

    return result


def validate_user_request(
    feasibility: FeasibilityMap,
    requested_towers: int | str,
    requested_min_floors: int | None = None,
    requested_max_floors: int | None = None,
    requested_unit_mix: list[str] | None = None,
) -> dict:
    """
    Validate a user's development request against computed feasibility.

    Returns a dict with:
      - is_valid: bool
      - warnings: List[str]  — non-blocking issues
      - errors: List[str]    — blocking issues (request is infeasible)
      - suggestions: List[str] — constructive alternatives
    """
    warnings: list[str] = []
    errors: list[str] = []
    suggestions: list[str] = []

    # Handle "auto" tower count
    if requested_towers == "auto" or requested_towers is None:
        return {
            "is_valid": True,
            "warnings": [],
            "errors": [],
            "suggestions": [
                f"Optimal configuration: {feasibility.recommended_towers} tower(s), "
                f"{feasibility.recommended_floors} floors"
            ] if feasibility.recommended_towers > 0 else [],
        }

    n_towers = int(requested_towers)

    # Check tower count feasibility
    tower_opt = next(
        (t for t in feasibility.tower_options if t.n_towers == n_towers),
        None,
    )

    if tower_opt is None or not tower_opt.is_feasible:
        errors.append(
            f"{n_towers} tower(s) is not feasible for this plot."
        )
        feasible_options = [t for t in feasibility.tower_options if t.is_feasible]
        if feasible_options:
            best_alt = max(feasible_options, key=lambda t: t.estimated_fsi_at_max)
            suggestions.append(
                f"Maximum feasible: {feasibility.max_feasible_towers} tower(s). "
                f"Recommended: {best_alt.n_towers} tower(s) at "
                f"{best_alt.max_floors} floors (FSI ~{best_alt.estimated_fsi_at_max:.2f})"
            )
        else:
            suggestions.append(
                "This plot may not be developable under current GDCR constraints."
            )

        return {
            "is_valid": False,
            "warnings": warnings,
            "errors": errors,
            "suggestions": suggestions,
        }

    # Tower count is feasible — check floor range
    if requested_min_floors and requested_min_floors > tower_opt.max_floors:
        errors.append(
            f"Minimum {requested_min_floors} floors exceeds maximum feasible "
            f"({tower_opt.max_floors} floors) for {n_towers} tower(s)."
        )
        suggestions.append(
            f"Maximum floors for {n_towers} tower(s): {tower_opt.max_floors}"
        )

    if requested_max_floors and requested_max_floors > feasibility.max_floors:
        warnings.append(
            f"Requested max {requested_max_floors} floors exceeds regulatory "
            f"cap of {feasibility.max_floors} floors "
            f"(height cap: {feasibility.max_height_m:.0f}m for "
            f"{feasibility.road_width_m:.0f}m road)."
        )
        suggestions.append(
            f"Height cap for {feasibility.road_width_m:.0f}m road: "
            f"{feasibility.max_height_m:.0f}m = {feasibility.max_floors} floors"
        )

    # Check unit mix compatibility using per-tower compat
    compat = tower_opt.floor_plan_compat or feasibility.floor_plan_compat
    if requested_unit_mix and compat:
        unit_compat_map = {
            "1BHK": compat.can_fit_1bhk,
            "2BHK": compat.can_fit_2bhk,
            "3BHK": compat.can_fit_3bhk,
            "4BHK": compat.can_fit_4bhk,
            "5BHK": compat.can_fit_5bhk,
        }
        for unit_type in requested_unit_mix:
            if not unit_compat_map.get(unit_type, True):
                warnings.append(
                    f"{unit_type} units may not fit in the estimated "
                    f"{compat.footprint_width_m:.1f}m x {compat.footprint_depth_m:.1f}m "
                    f"footprint."
                )

    is_valid = len(errors) == 0
    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "errors": errors,
        "suggestions": suggestions,
    }
