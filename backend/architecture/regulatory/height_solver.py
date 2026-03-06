from __future__ import annotations

"""
architecture.regulatory.height_solver
-------------------------------------

Deterministic solver for the maximum legally feasible building height
under GDCR constraints for a *single-tower* scenario.

This module:
  - Does NOT modify envelope, placement, skeleton, or layout engines.
  - Uses GDCR.yaml via architecture.regulatory_accessors.
  - Reuses existing envelope and placement services.
  - Reuses feasibility/regulatory metrics to avoid duplicating FSI/GC math.
"""

from dataclasses import dataclass
from math import floor
from typing import Optional, Tuple

import logging
from django.contrib.gis.geos import GEOSGeometry

from tp_ingestion.models import Plot
from common.units import dxf_to_metres

from envelope_engine.services.envelope_service import compute_envelope
from placement_engine.services.placement_service import compute_placement

from architecture.feasibility.buildability_metrics import build_buildability_metrics
from architecture.feasibility.regulatory_metrics import build_regulatory_metrics
from architecture.regulatory_accessors import (
    get_max_permissible_height_by_road_width,
    get_max_fsi,
    get_max_ground_coverage_pct,
)
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta

from rules_engine.services.evaluator import build_inputs_from_dict, evaluate_all
from rules_engine.rules.base import FAIL

from floor_skeleton.services import generate_floor_skeleton
from floor_skeleton.models import NO_SKELETON_PATTERN
from residential_layout import build_floor_layout


logger = logging.getLogger(__name__)


@dataclass
class HeightSolution:
    max_height_m: float
    controlling_constraint: str
    floors: int
    footprint_area_sqft: float
    achieved_fsi: float
    fsi_utilization_pct: float
    gc_utilization_pct: float
    spacing_required_m: float
    spacing_provided_m: Optional[float]


def _spacing_provided_m_from_audit(placement_result) -> Optional[float]:
    """Compute minimum spacing (m) from placement_audit entries, if any."""
    gaps_m = []
    for entry in getattr(placement_result, "placement_audit", []) or []:
        gap_dxf = entry.get("gap_dxf")
        if gap_dxf is None:
            continue
        gaps_m.append(dxf_to_metres(float(gap_dxf)))
    return min(gaps_m) if gaps_m else None


def _side_rear_margins_from_audit(edge_margin_audit: list) -> Tuple[Optional[float], Optional[float]]:
    """Extract first SIDE and REAR margins (m) from edge_margin_audit."""
    side_m = None
    rear_m = None
    for e in edge_margin_audit:
        etype = e.get("edge_type")
        m = e.get("margin_m")
        if m is None:
            continue
        if etype == "SIDE" and side_m is None:
            side_m = float(m)
        if etype == "REAR" and rear_m is None:
            rear_m = float(m)
        if side_m is not None and rear_m is not None:
            break
    return side_m, rear_m


def _is_feasible_height(
    plot: Plot,
    height_m: float,
    storey_height_m: float,
    min_width_m: float,
    min_depth_m: float,
    max_fsi: float,
    max_gc_pct: float,
) -> Tuple[bool, Optional[dict]]:
    """
    Check whether a given height is geometrically and regulatorily feasible.

    Returns (feasible_flag, context_dict or None). The context dict contains
    the artefacts needed to build the final HeightSolution when feasible.
    """
    # Basic guard: non-positive height is never a meaningful building
    if height_m <= 0.0:
        return False, None

    plot_geom = plot.geom
    plot_wkt = plot_geom.wkt
    plot_area_sqft = plot.plot_area_sqft

    # Detect road-facing edges (using road layer if present; None -> fallback)
    road_edges, _fallback_used = detect_road_edges_with_meta(plot_geom, None)
    road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    if road_width <= 0.0:
        # Without a road width, we cannot reliably apply height vs road logic
        return False, None

    # Envelope
    env = compute_envelope(
        plot_wkt=plot_wkt,
        building_height=height_m,
        road_width=road_width,
        road_facing_edges=road_edges,
        enforce_gc=True,
    )
    if env.status != "VALID" or env.envelope_polygon is None:
        return False, None

    # Placement (single tower)
    envelope_wkt = env.envelope_polygon.wkt
    placement = compute_placement(
        envelope_wkt=envelope_wkt,
        building_height_m=height_m,
        n_towers=1,
        min_width_m=min_width_m,
        min_depth_m=min_depth_m,
    )
    if placement.status != "VALID" or not placement.footprints:
        return False, None

    # Footprint and buildability metrics
    fp = placement.footprints[0]
    footprint_area_sqft = fp.area_sqft
    if footprint_area_sqft <= 0.0 or plot_area_sqft <= 0.0:
        return False, None

    buildability = build_buildability_metrics(
        envelope_area_sqft=env.envelope_area_sqft or 0.0,
        footprint_width_m=fp.width_m,
        footprint_depth_m=fp.depth_m,
        footprint_area_sqft=footprint_area_sqft,
        core_area_sqm=placement.per_tower_core_validation[0].core_area_estimate_sqm
        if placement.per_tower_core_validation
        else 0.0,
        remaining_usable_sqm=placement.per_tower_core_validation[0].remaining_usable_sqm
        if placement.per_tower_core_validation
        else 0.0,
    )

    # FSI limit: max floors from max_fsi (no forced minimum — GDCR: if allowed_bua < footprint, zero floors is correct)
    allowed_bua_sqft = max_fsi * plot_area_sqft
    max_floors_fsi = floor(allowed_bua_sqft / footprint_area_sqft)
    if max_floors_fsi <= 0:
        return False, None
    h_fsi_limit = max_floors_fsi * storey_height_m
    # Candidate height cannot exceed FSI-derived limit
    if height_m - h_fsi_limit > 1e-6:
        return False, None

    # GC: achieved from built footprint / plot area (to match feasibility logic)
    achieved_gc_pct = 100.0 * buildability.footprint_area_sqft / plot_area_sqft
    if achieved_gc_pct - max_gc_pct > 1e-6:
        return False, None

    # Spacing: for single tower, no spacing_provided_m; spacing_required_m is still defined
    spacing_required_m = placement.spacing_required_m
    spacing_provided_m = _spacing_provided_m_from_audit(placement)
    # For n_towers == 1, spacing_provided_m is None and the spacing constraint is vacuous.

    # Floors for this candidate: limited by height and by FSI (max_floors_fsi >= 1 here)
    floors_by_height = max(1, floor(height_m / storey_height_m))
    floors = min(floors_by_height, max_floors_fsi)

    # Compute regulatory metrics once for this candidate (FSI, GC, spacing)
    cop_provided_sqft = env.common_plot_area_sqft or 0.0
    regulatory = build_regulatory_metrics(
        plot_area_sqft=plot_area_sqft,
        total_bua_sqft=buildability.footprint_area_sqft * floors,
        achieved_gc_pct=achieved_gc_pct,
        cop_provided_sqft=cop_provided_sqft,
        spacing_required_m=spacing_required_m,
        spacing_provided_m=spacing_provided_m,
    )

    ctx = {
        "height_m": height_m,
        "floors": floors,
        "footprint_area_sqft": buildability.footprint_area_sqft,
        "spacing_required_m": spacing_required_m,
        "spacing_provided_m": spacing_provided_m,
        "regulatory": regulatory,
        "envelope": env,
        "placement": placement,
    }
    return True, ctx


def _is_compliant_via_rules(plot: Plot, ctx: dict) -> bool:
    """
    Run the rules engine for the candidate context and ensure no FAIL items.
    """
    pm = plot
    env = ctx["envelope"]
    placement = ctx["placement"]
    regulatory = ctx["regulatory"]

    plot_area_sqft = pm.plot_area_sqft
    height_m = ctx["height_m"]
    floors = ctx["floors"]
    footprint_area_sqft = ctx["footprint_area_sqft"]
    total_bua_sqft = footprint_area_sqft * floors
    road_width = float(getattr(pm, "road_width_m", 0.0) or 0.0)

    # Ground coverage: use built footprint to match feasibility assumptions
    ground_coverage_sqft = footprint_area_sqft

    # Side/rear margins from envelope audit
    side_m, rear_m = _side_rear_margins_from_audit(env.edge_margin_audit or [])

    # Road-side margin from envelope audit (first ROAD edge margin)
    road_margin_m = None
    for e in env.edge_margin_audit or []:
        if e.get("edge_type") == "ROAD":
            m = e.get("margin_m")
            if m is not None:
                road_margin_m = float(m)
                break

    rule_params = {
        "road_width": road_width,
        "building_height": height_m,
        "total_bua": total_bua_sqft,
        "num_floors": floors,
        "ground_coverage": ground_coverage_sqft,
        "has_basement": False,
        "is_sprinklered": False,
        "has_lift": bool(
            placement.per_tower_core_validation
            and placement.per_tower_core_validation[0].lift_required
        ),
    }
    if side_m is not None:
        rule_params["side_margin"] = side_m
    if rear_m is not None:
        rule_params["rear_margin"] = rear_m
    if road_margin_m is not None:
        rule_params["road_margin"] = road_margin_m

    inputs = build_inputs_from_dict(plot_area_sqft, rule_params)
    results = evaluate_all(inputs)
    return all(r.status != FAIL for r in results)


def _is_layout_viable(
    plot: Plot,
    height_m: float,
    placement_ctx: dict,
    storey_height_m: float,
) -> bool:
    """
    Post-solver viability: at least one valid FloorLayoutContract exists at this height.

    Uses placement from placement_ctx (footprint + core validation). Does not persist;
    uses DEFAULT configuration only. Exceptions are treated as not viable.
    """
    try:
        skeleton = generate_floor_skeleton(
            footprint=placement_ctx["placement"].footprints[0],
            core_validation=placement_ctx["placement"].per_tower_core_validation[0],
        )
    except Exception:
        return False

    if (
        skeleton.pattern_used == NO_SKELETON_PATTERN
        or not skeleton.is_geometry_valid
        or not skeleton.passes_min_unit_guard
        or not skeleton.is_architecturally_viable
    ):
        return False

    try:
        floor_layout = build_floor_layout(skeleton, floor_id="L0", module_width_m=None)
    except Exception:
        return False

    return (
        floor_layout.total_units > 0
        and floor_layout.efficiency_ratio_floor > 0
    )


def solve_max_legal_height(
    plot: Plot,
    building_height_upper_bound: Optional[float] = None,
    storey_height_m: float = 3.0,
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
) -> HeightSolution:
    """
    Solve for the maximum GDCR-compliant building height for a single tower.

    Does not modify any geometry engines or existing CLIs. Uses binary search
    over height in [0, H_cap], where H_cap is derived from GDCR road-width
    limits and an optional explicit upper bound.
    """
    if storey_height_m <= 0:
        raise ValueError("storey_height_m must be positive.")

    road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    if road_width <= 0.0:
        raise ValueError("Plot.road_width_m must be set for height solving.")

    # Absolute cap from GDCR road-width logic
    h_road = get_max_permissible_height_by_road_width(road_width)
    if building_height_upper_bound is not None:
        h_cap = min(h_road, float(building_height_upper_bound))
    else:
        h_cap = h_road

    if not (h_cap > 0.0):
        # Nothing feasible above zero height
        return HeightSolution(
            max_height_m=0.0,
            controlling_constraint="ROAD_WIDTH_CAP",
            floors=0,
            footprint_area_sqft=0.0,
            achieved_fsi=0.0,
            fsi_utilization_pct=0.0,
            gc_utilization_pct=0.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

    max_fsi = get_max_fsi()
    max_gc_pct = get_max_ground_coverage_pct()

    # Binary search over height
    lo, hi = 0.0, h_cap
    best_ctx: Optional[dict] = None
    tol = 0.01

    for _ in range(40):  # enough for sub-centimetre precision
        mid = (lo + hi) / 2.0
        feasible, ctx = _is_feasible_height(
            plot=plot,
            height_m=mid,
            storey_height_m=storey_height_m,
            min_width_m=min_width_m,
            min_depth_m=min_depth_m,
            max_fsi=max_fsi,
            max_gc_pct=max_gc_pct,
        )
        if feasible and ctx and _is_compliant_via_rules(plot, ctx):
            lo = mid
            best_ctx = ctx
        else:
            hi = mid
        if hi - lo < tol:
            break

    if best_ctx is None:
        # No feasible/compliant height found; return zeroed solution.
        return HeightSolution(
            max_height_m=0.0,
            controlling_constraint="INFEASIBLE",
            floors=0,
            footprint_area_sqft=0.0,
            achieved_fsi=0.0,
            fsi_utilization_pct=0.0,
            gc_utilization_pct=0.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

    # ── Stage 2: Post-solver layout viability (discrete floor levels only) ─────
    # Layout feasibility changes only when floor count changes; test per-floor heights only.
    max_height_m_legal = best_ctx["height_m"]
    height_candidate = max_height_m_legal
    floors = floor(height_candidate / storey_height_m)
    final_height: Optional[float] = None
    final_ctx: Optional[dict] = None

    while floors > 0:
        adjusted_height = floors * storey_height_m
        feasible, ctx = _is_feasible_height(
            plot=plot,
            height_m=adjusted_height,
            storey_height_m=storey_height_m,
            min_width_m=min_width_m,
            min_depth_m=min_depth_m,
            max_fsi=max_fsi,
            max_gc_pct=max_gc_pct,
        )
        if feasible and ctx and _is_compliant_via_rules(plot, ctx) and _is_layout_viable(plot, adjusted_height, ctx, storey_height_m):
            final_height = adjusted_height
            final_ctx = ctx
            break
        floors -= 1

    if final_height is None:
        return HeightSolution(
            max_height_m=0.0,
            controlling_constraint="LAYOUT_INFEASIBLE",
            floors=0,
            footprint_area_sqft=0.0,
            achieved_fsi=0.0,
            fsi_utilization_pct=0.0,
            gc_utilization_pct=0.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

    # Final height and metrics from final_ctx
    max_height_m = final_height
    floors = final_ctx["floors"]
    footprint_area_sqft = final_ctx["footprint_area_sqft"]
    regulatory = final_ctx["regulatory"]
    spacing_required_m = final_ctx["spacing_required_m"]
    spacing_provided_m = final_ctx["spacing_provided_m"]

    # GC utilisation is the achieved GC percentage
    gc_utilization_pct = regulatory.achieved_gc_pct

    # Controlling constraint: LAYOUT_LIMIT if legal height > layout-viable height
    h_road_cap = h_road
    allowed_bua_sqft = max_fsi * plot.plot_area_sqft
    max_floors_fsi = floor(allowed_bua_sqft / footprint_area_sqft) if footprint_area_sqft > 0 else 0
    h_fsi_limit = max_floors_fsi * storey_height_m if max_floors_fsi > 0 else 0.0

    if final_height < max_height_m_legal - 0.05:
        controlling = "LAYOUT_LIMIT"
    elif abs(max_height_m - h_road_cap) <= 0.05:
        controlling = "ROAD_WIDTH_CAP"
    elif max_height_m >= h_fsi_limit - 0.05 and h_fsi_limit < h_road_cap:
        controlling = "FSI_LIMIT"
    else:
        controlling = "PLACEMENT_GEOMETRY"

    # ── Debug logging for height solver diagnostics ─────────────────────────────
    try:
        height_from_road_width = h_road_cap
        height_from_fsi_limit = h_fsi_limit
        # These components are not modelled explicitly in the current solver;
        # we log them as None to make that clear in diagnostics.
        height_from_margin = None
        height_from_fire_access = None
        height_from_other_constraints = max_height_m_legal

        logger.warning(
            "HEIGHT_SOLVER_DEBUG: plot_id=%s road_width_m=%.3f "
            "height_from_road_width=%.3f height_from_fsi_limit=%.3f "
            "height_from_margin=%s height_from_fire_access=%s "
            "height_from_other_constraints=%.3f final_height=%.3f floors=%d controlling=%s",
            getattr(plot, "public_id", getattr(plot, "id", None)),
            road_width,
            height_from_road_width,
            height_from_fsi_limit,
            str(height_from_margin),
            str(height_from_fire_access),
            height_from_other_constraints,
            max_height_m,
            floors,
            controlling,
        )
    except Exception:
        # Debug logging must never break the solver.
        pass

    return HeightSolution(
        max_height_m=max_height_m,
        controlling_constraint=controlling,
        floors=floors,
        footprint_area_sqft=footprint_area_sqft,
        achieved_fsi=regulatory.achieved_fsi,
        fsi_utilization_pct=regulatory.fsi_utilization_pct,
        gc_utilization_pct=gc_utilization_pct,
        spacing_required_m=spacing_required_m,
        spacing_provided_m=spacing_provided_m,
    )

