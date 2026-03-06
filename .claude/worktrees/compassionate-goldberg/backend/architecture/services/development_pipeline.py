from __future__ import annotations

"""
architecture.services.development_pipeline
------------------------------------------

Deterministic orchestration layer that takes the optimal multi-tower
development configuration for a plot and generates one representative
floor layout per tower by coordinating existing engines:

  - development_optimizer.solve_optimal_development_configuration
  - envelope_engine.services.compute_envelope
  - placement_engine.services.compute_placement
  - floor_skeleton.services.generate_floor_skeleton
  - residential_layout.floor_aggregation.build_floor_layout
  - residential_layout.building_aggregation.build_building_layout (optional)

This module:
  - Does NOT modify any geometry, skeleton, layout, or rules engines.
  - Does NOT perform any regulatory optimisation or re-check rules.
  - Exposes a DTO-first public contract, suitable for JSON/APIs.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from django.contrib.gis.geos import GEOSGeometry

from tp_ingestion.models import Plot

from envelope_engine.services.envelope_service import compute_envelope
from placement_engine.services.placement_service import compute_placement, PlacementResult
from placement_engine.geometry import FootprintCandidate

from floor_skeleton.services import generate_floor_skeleton
from floor_skeleton.models import FloorSkeleton, NO_SKELETON_PATTERN

from residential_layout.floor_aggregation import (
    build_floor_layout,
    FloorLayoutContract,
    FloorAggregationError,
    FloorAggregationValidationError,
)
from residential_layout.building_aggregation import (
    build_building_layout,
    BuildingLayoutContract,
    BuildingAggregationError,
)

from area_accounting.floor_area import (
    compute_floor_area_breakdown_detailed,
    FloorAreaBreakdown,
)
from detailed_layout.config import DetailingConfig

from architecture.spatial.road_edge_detector import detect_road_edges_with_meta
from architecture.regulatory.development_optimizer import (
    evaluate_development_configuration,
    OptimalDevelopmentSolution,
)


@dataclass
class TowerFloorLayoutDTO:
    tower_index: int
    floor_id: str
    total_units: int
    efficiency_ratio_floor: float
    unit_area_sum_sqm: float
    footprint_polygon_wkt: str
    core_polygon_wkt: Optional[str]
    corridor_polygon_wkt: Optional[str]
    # Internal use only; not for external APIs.
    raw_contract: Optional[FloorLayoutContract] = None
    # Optional detailed area accounting metrics for this floor layout.
    area_breakdown: Optional[FloorAreaBreakdown] = None


@dataclass
class PlacementSummaryDTO:
    n_towers: int
    per_tower_footprint_sqft: List[float]
    spacing_required_m: float
    spacing_provided_m: Optional[float]


@dataclass
class DevelopmentFloorPlanResult:
    """
    Canonical result of the development pipeline orchestrator.

    Logically partitioned into:
      - status / failure metadata
      - chosen configuration
      - regulatory metrics
      - geometry summaries
      - per-tower layouts
      - optional building-level layout
    """

    # Status / failure metadata
    status: str  # "OK" or one of the failure codes below
    failure_reason: Optional[str]
    failure_details: Optional[Dict[str, Any]]

    # Chosen configuration from development_optimizer
    n_towers: int
    floors: int
    height_m: float
    achieved_fsi: float
    fsi_utilization_pct: float
    total_bua_sqft: float
    gc_utilization_pct: float
    controlling_constraint: str

    # Geometry and layout artefacts
    envelope_wkt: Optional[str]
    placement_summary: Optional[PlacementSummaryDTO]
    tower_floor_layouts: List[TowerFloorLayoutDTO]

    # Optional: building-level contract when include_building_layout=True
    building_layout: Optional[BuildingLayoutContract]

    # COP metadata for the chosen configuration
    cop_strategy: Optional[str] = None
    cop_area_sqft: Optional[float] = None
    cop_margin_m: Optional[float] = None


def _error_result(
    status: str,
    reason: str,
    details: Optional[Dict[str, Any]] = None,
) -> DevelopmentFloorPlanResult:
    """
    Helper to build a failure result with zeroed configuration/metrics/layouts.
    """
    return DevelopmentFloorPlanResult(
        status=status,
        failure_reason=reason,
        failure_details=details or {},
        n_towers=0,
        floors=0,
        height_m=0.0,
        achieved_fsi=0.0,
        fsi_utilization_pct=0.0,
        total_bua_sqft=0.0,
        gc_utilization_pct=0.0,
        controlling_constraint=status,
        envelope_wkt=None,
        placement_summary=None,
        tower_floor_layouts=[],
        building_layout=None,
    )


def _footprint_centroid_key(fp: FootprintCandidate) -> tuple[float, float]:
    """
    Deterministic key for ordering towers based on footprint geometry.

    Uses the centroid of the Shapely footprint polygon (in DXF feet).
    """
    poly = fp.footprint_polygon
    c = poly.centroid
    return (float(c.x), float(c.y))


def _polygon_to_wkt(poly) -> Optional[str]:
    """
    Convert a Shapely polygon (or GEOSGeometry) to WKT string.
    Returns None when geometry is absent or empty.
    """
    if poly is None:
        return None
    try:
        wkt = poly.wkt  # Shapely polygons expose .wkt
    except Exception:
        # Fallback: if GEOSGeometry sneaks in
        if isinstance(poly, GEOSGeometry):
            return poly.wkt
        return None
    return wkt


def generate_optimal_development_floor_plans(
    plot: Plot,
    storey_height_m: float = 3.0,
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
    *,
    include_building_layout: bool = False,
    strict: bool = True,
) -> DevelopmentFloorPlanResult:
    """
    Orchestrate the full development pipeline for a Plot:

      1. Use solve_optimal_development_configuration() to pick the best
         (floors, height, n_towers) under GDCR + layout constraints.
      2. Recompute envelope and placement for that configuration.
      3. Generate one representative floor layout per tower.
      4. Optionally aggregate a building-level layout.

    This function is deterministic and side-effect free: it does not
    persist anything or mutate engine configuration.
    """
    if storey_height_m <= 0:
        raise ValueError("storey_height_m must be positive.")

    road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    if road_width <= 0.0:
        return _error_result(
            status="INFEASIBLE",
            reason="INFEASIBLE",
            details={"message": "Plot.road_width_m must be positive."},
        )

    # Step 1 — call development optimiser (no search here).
    # Use "development" mode so that base FSI is treated as soft for optimisation,
    # while maximum FSI and all other regulatory checks remain enforced.
    dev_sol: OptimalDevelopmentSolution = evaluate_development_configuration(
        plot=plot,
        storey_height_m=storey_height_m,
        min_width_m=min_width_m,
        min_depth_m=min_depth_m,
        mode="development",
    )

    if (
        dev_sol.controlling_constraint == "INFEASIBLE"
        or dev_sol.n_towers <= 0
        or dev_sol.floors <= 0
    ):
        return _error_result(
            status="INFEASIBLE",
            reason="INFEASIBLE",
            details={"message": "Development optimiser found no feasible configuration."},
        )

    n_towers = dev_sol.n_towers
    floors = dev_sol.floors

    # Canonical height decision: derive from floors and storey height.
    height_m = floors * storey_height_m

    # Optional sanity check: ensure solver height is consistent when present.
    solver_height = float(getattr(dev_sol, "height_m", 0.0) or 0.0)
    if solver_height > 0 and abs(solver_height - height_m) > 1e-3:
        # Programming/config mismatch: treat as hard error.
        if strict:
            return _error_result(
                status="INFEASIBLE",
                reason="INFEASIBLE",
                details={
                    "message": "Height mismatch between optimiser and pipeline.",
                    "solver_height_m": solver_height,
                    "derived_height_m": height_m,
                },
            )

    # Step 2 — recompute envelope at final height.
    plot_geom = plot.geom
    road_edges, _ = detect_road_edges_with_meta(plot_geom, None)

    env = compute_envelope(
        plot_wkt=plot_geom.wkt,
        building_height=height_m,
        road_width=road_width,
        road_facing_edges=road_edges,
        enforce_gc=True,
    )
    if env.status != "VALID" or env.envelope_polygon is None:
        return _error_result(
            status="ENVELOPE_INVALID",
            reason="ENVELOPE_INVALID",
            details={
                "message": "Envelope invalid at final height.",
                "height_m": height_m,
                "status": env.status,
            },
        )

    envelope_wkt = env.envelope_polygon.wkt

    # Step 3 — recompute placement for chosen n_towers.
    placement: PlacementResult = compute_placement(
        envelope_wkt=envelope_wkt,
        building_height_m=height_m,
        n_towers=n_towers,
        min_width_m=min_width_m,
        min_depth_m=min_depth_m,
    )
    if placement.status != "VALID" or not placement.footprints:
        return _error_result(
            status="PLACEMENT_INVALID",
            reason="PLACEMENT_INVALID",
            details={
                "message": "Placement invalid for chosen configuration.",
                "placement_status": placement.status,
                "n_towers_requested": n_towers,
                "n_towers_placed": placement.n_towers_placed,
            },
        )

    # Derive deterministic tower ordering based on footprint centroid.
    footprints: List[FootprintCandidate] = placement.footprints
    core_validations = placement.per_tower_core_validation or []
    if len(core_validations) < len(footprints):
        # Core validations should align with footprints for valid placements.
        if strict:
            return _error_result(
                status="PLACEMENT_INVALID",
                reason="PLACEMENT_INVALID",
                details={
                    "message": "per_tower_core_validation length mismatch.",
                    "n_footprints": len(footprints),
                    "n_core_validations": len(core_validations),
                },
            )

    indexed = list(enumerate(footprints))
    indexed.sort(key=lambda pair: _footprint_centroid_key(pair[1]))

    # Prepare placement summary from this fresh placement.
    per_tower_footprint_sqft = [float(fp.area_sqft or 0.0) for fp in footprints]
    placement_summary = PlacementSummaryDTO(
        n_towers=len(footprints),
        per_tower_footprint_sqft=per_tower_footprint_sqft,
        spacing_required_m=float(placement.spacing_required_m or 0.0),
        spacing_provided_m=None,  # could be derived from placement_audit if needed
    )

    # Step 4 — per-tower skeleton and floor layout.
    tower_layouts: List[TowerFloorLayoutDTO] = []
    detailing_config = DetailingConfig()

    for logical_index, (orig_idx, fp) in enumerate(indexed):
        core_validation = core_validations[orig_idx]

        # Generate floor skeleton.
        try:
            skeleton: FloorSkeleton = generate_floor_skeleton(
                footprint=fp,
                core_validation=core_validation,
            )
        except Exception as exc:  # noqa: BLE001
            if strict:
                return _error_result(
                    status="SKELETON_INVALID",
                    reason="SKELETON_INVALID",
                    details={
                        "message": "Skeleton generation failed.",
                        "tower_index": logical_index,
                        "exception": str(exc),
                    },
                )
            continue

        if (
            skeleton.pattern_used == NO_SKELETON_PATTERN
            or not skeleton.is_geometry_valid
            or not skeleton.passes_min_unit_guard
            or not skeleton.is_architecturally_viable
        ):
            if strict:
                return _error_result(
                    status="SKELETON_INVALID",
                    reason="SKELETON_INVALID",
                    details={
                        "message": "Skeleton not viable.",
                        "tower_index": logical_index,
                        "pattern_used": skeleton.pattern_used,
                        "is_geometry_valid": skeleton.is_geometry_valid,
                        "passes_min_unit_guard": skeleton.passes_min_unit_guard,
                        "is_architecturally_viable": skeleton.is_architecturally_viable,
                    },
                )
            continue

        # Build floor layout for this tower.
        floor_id = f"L0_T{logical_index}"
        try:
            floor_contract: FloorLayoutContract = build_floor_layout(
                skeleton=skeleton,
                floor_id=floor_id,
                module_width_m=None,
            )
        except (FloorAggregationError, FloorAggregationValidationError) as exc:
            if strict:
                return _error_result(
                    status="LAYOUT_INVALID",
                    reason="LAYOUT_INVALID",
                    details={
                        "message": "Floor layout generation failed.",
                        "tower_index": logical_index,
                        "exception": str(exc),
                    },
                )
            continue

        if floor_contract.total_units <= 0 or floor_contract.efficiency_ratio_floor <= 0.0:
            if strict:
                return _error_result(
                    status="LAYOUT_INVALID",
                    reason="LAYOUT_INVALID",
                    details={
                        "message": "Floor layout not viable (no units / zero efficiency).",
                        "tower_index": logical_index,
                        "total_units": floor_contract.total_units,
                        "efficiency_ratio_floor": floor_contract.efficiency_ratio_floor,
                    },
                )
            continue

        # Compute detailed area accounting for this floor layout.
        try:
            area_breakdown = compute_floor_area_breakdown_detailed(
                floor=floor_contract,
                units=list(floor_contract.all_units),
                config=detailing_config,
            )
        except Exception as exc:  # noqa: BLE001
            if strict:
                return _error_result(
                    status="AREA_ACCOUNTING_INVALID",
                    reason="AREA_ACCOUNTING_INVALID",
                    details={
                        "message": "Area accounting failed.",
                        "tower_index": logical_index,
                        "exception": str(exc),
                    },
                )
            area_breakdown = None

        # Build DTO from floor layout.
        footprint_wkt = _polygon_to_wkt(floor_contract.footprint_polygon)
        core_wkt = _polygon_to_wkt(floor_contract.core_polygon)
        corridor_wkt = _polygon_to_wkt(floor_contract.corridor_polygon)

        dto = TowerFloorLayoutDTO(
            tower_index=logical_index,
            floor_id=floor_id,
            total_units=int(floor_contract.total_units),
            efficiency_ratio_floor=float(floor_contract.efficiency_ratio_floor),
            unit_area_sum_sqm=float(floor_contract.unit_area_sum),
            footprint_polygon_wkt=footprint_wkt or "",
            core_polygon_wkt=core_wkt,
            corridor_polygon_wkt=corridor_wkt,
            raw_contract=floor_contract,
            area_breakdown=area_breakdown,
        )
        tower_layouts.append(dto)

    if strict and len(tower_layouts) != n_towers:
        # Under strict mode, require one layout per tower.
        return _error_result(
            status="LAYOUT_INVALID",
            reason="LAYOUT_INVALID",
            details={
                "message": "Not all towers produced a valid layout.",
                "expected_towers": n_towers,
                "actual_layouts": len(tower_layouts),
            },
        )

    # Step 5 — optional building aggregation.
    building_layout: Optional[BuildingLayoutContract] = None
    if include_building_layout and tower_layouts:
        # For now, aggregate based on the first tower's skeleton and floor layout.
        # Multi-tower building aggregation strategies can be added later.
        try:
            # Reconstruct skeleton reference from the raw_contract of the first DTO.
            first_contract = tower_layouts[0].raw_contract
            if first_contract is not None:
                # building_height_m is floors * storey_height_m by invariant.
                building_layout = build_building_layout(
                    skeleton=skeleton,  # last skeleton generated; adequate for uniform towers
                    height_limit_m=height_m,
                    storey_height_m=storey_height_m,
                    building_id="B0",
                    module_width_m=None,
                    first_floor_contract=first_contract,
                )
        except BuildingAggregationError as exc:
            if strict:
                return _error_result(
                    status="BUILDING_LAYOUT_INVALID",
                    reason="BUILDING_LAYOUT_INVALID",
                    details={"message": "Building layout aggregation failed.", "exception": str(exc)},
                )
            building_layout = None

    # Success: assemble final result using optimiser metrics and derived height.
    return DevelopmentFloorPlanResult(
        status="OK",
        failure_reason=None,
        failure_details=None,
        n_towers=n_towers,
        floors=floors,
        height_m=height_m,
        achieved_fsi=float(dev_sol.achieved_fsi),
        fsi_utilization_pct=float(dev_sol.fsi_utilization_pct),
        total_bua_sqft=float(dev_sol.total_bua_sqft),
        gc_utilization_pct=float(dev_sol.gc_utilization_pct),
        controlling_constraint=dev_sol.controlling_constraint,
        envelope_wkt=envelope_wkt,
        placement_summary=placement_summary,
        tower_floor_layouts=tower_layouts,
        building_layout=building_layout,
        cop_strategy=getattr(env, "cop_strategy", getattr(dev_sol, "cop_strategy", None)),
        cop_area_sqft=float(
            getattr(env, "common_plot_area_sqft", None)
            or getattr(dev_sol, "cop_area_sqft", 0.0)
        ),
        cop_margin_m=getattr(env, "cop_margin_m", None),
    )

