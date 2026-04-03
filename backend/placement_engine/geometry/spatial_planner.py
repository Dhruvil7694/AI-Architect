"""
placement_engine/geometry/spatial_planner.py
---------------------------------------------
Constraint-driven spatial planner for site layout generation.

Replaces the rectangle-packing mindset with a 5-step pipeline:
    1. Carve fire-tender access loop (hard constraint)
    2. Place COP intelligently (adaptive to plot shape)
    3. Decompose remaining space into tower zones
    4. Place towers within zones (constrained orientation)
    5. Validate all hard constraints (fail-fast)

If the layout fails hard constraints, a relaxation cascade (levels 0→3)
progressively loosens non-safety constraints.  Level 4 falls back to the
legacy packer for backward compatibility.

Unit contract
-------------
All geometry in DXF feet (SRID=0).  Heights/widths in metres at the API
boundary, converted via METRES_TO_DXF internally.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from shapely.geometry import Polygon

from envelope_engine.geometry.edge_classifier import ROAD, EdgeSpec
from placement_engine.geometry import (
    METRES_TO_DXF,
    DXF_TO_METRES,
    FootprintCandidate,
    MIN_FOOTPRINT_AREA_SQFT,
)
from placement_engine.geometry.fire_loop import (
    FireLoopResult,
    carve_fire_loop,
)
from placement_engine.geometry.zone_decomposer import (
    TowerZone,
    ZoneResult,
    decompose_into_zones,
)
from placement_engine.constraints.hard_constraints import (
    ConstraintResult,
    check_hard_constraints,
)
from placement_engine.geometry.multipolygon_handler import find_top_n_in_components
from placement_engine.scoring.placement_scorer import select_best_candidate

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class SpatialPlanResult:
    """Result of the constraint-driven spatial planner."""
    status: str                           # "VALID" | "RELAXED" | "FALLBACK" | "INFEASIBLE"
    constraint_level: int                 # 0=full, 1-3=relaxed, 4=legacy
    fire_loop: Optional[FireLoopResult] = None
    zones: Optional[ZoneResult] = None
    cop_polygon: Optional[Polygon] = None
    cop_area_sqft: float = 0.0
    cop_centroid: Optional[tuple] = None  # NEW: (x, y) in DXF feet
    footprints: List[FootprintCandidate] = field(default_factory=list)
    constraint_check: Optional[ConstraintResult] = None
    packing_mode: str = "SPATIAL_PLANNER"
    n_placed: int = 0
    total_area_sqft: float = 0.0


# ── Cascade configuration ────────────────────────────────────────────────────


def _fire_width_for_level(level: int, height_m: float) -> float:
    """Fire-tender access width by constraint level."""
    if level == 0:
        return 4.5
    elif level <= 3:
        return 3.0 if height_m < 15.0 else 4.5
    return 0.0  # level 4 = legacy, no fire loop


def _orientation_tolerance_for_level(level: int) -> float:
    """Allowed deviation from road-aligned/orthogonal."""
    if level <= 2:
        return 5.0
    elif level == 3:
        return 15.0
    return 90.0  # level 4 = any angle


def _enforce_cop_dimensions_for_level(level: int) -> bool:
    """Whether to enforce COP minimum width/depth dimensions."""
    return level <= 1


# ── Constrained orientation helpers ───────────────────────────────────────────


def _compute_allowed_angles(
    road_edge_angles_deg: Optional[List[float]],
    tolerance_deg: float = 5.0,
) -> List[float]:
    """
    Compute the set of allowed tower rotation angles based on road direction.

    Returns angles for: road-aligned, orthogonal, and ±tolerance variants.
    If no road info, returns [0, 45, 90] as fallback.
    """
    if not road_edge_angles_deg:
        return [0.0, 45.0, 90.0]

    angles = set()
    for road_angle in road_edge_angles_deg:
        # Road-aligned and orthogonal
        angles.add(road_angle % 180)
        angles.add((road_angle + 90) % 180)
        # ±tolerance variants
        if tolerance_deg > 0:
            angles.add((road_angle + tolerance_deg) % 180)
            angles.add((road_angle - tolerance_deg) % 180)
            angles.add((road_angle + 90 + tolerance_deg) % 180)
            angles.add((road_angle + 90 - tolerance_deg) % 180)

    return sorted(angles)


def _place_tower_in_zone(
    zone: Polygon,
    min_width_dxf: float,
    min_depth_dxf: float,
    allowed_angles: List[float],
    road_edge_angles_deg: Optional[List[float]] = None,
    target_plate_area_sqft: Optional[float] = None,
    cop_polygon: Optional[Polygon] = None,
    cop_centroid: Optional[tuple] = None,
) -> Optional[FootprintCandidate]:
    """
    Place a single tower inside a zone using constrained orientation.

    Tries each allowed angle and selects the best candidate using the
    placement scorer (architectural quality, not just area).
    
    COP-aware: passes COP data to scorer for proximity scoring.
    """
    all_candidates: List[FootprintCandidate] = []

    for angle in allowed_angles:
        try:
            candidates = find_top_n_in_components(
                geom=zone,
                min_width_dxf=min_width_dxf,
                min_depth_dxf=min_depth_dxf,
                force_angle=angle,
                min_area_sqft=MIN_FOOTPRINT_AREA_SQFT,
                n=5,
            )
            all_candidates.extend(candidates)
        except Exception:
            continue

    if not all_candidates:
        return None

    # Use the existing placement scorer to select the best
    best = select_best_candidate(
        candidates=all_candidates,
        available_polygon=zone,
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
        cop_polygon=cop_polygon,  # NEW: pass COP for proximity scoring
        cop_centroid=cop_centroid,  # NEW
    )

    if best is None:
        return None

    # Clip footprint to zone boundary — inscribed rectangle rasterization can
    # produce polygons that slightly exceed the zone due to grid precision.
    from shapely.geometry import MultiPolygon as _MP
    clipped = best.footprint_polygon.intersection(zone)
    if clipped.is_empty:
        return None
    if isinstance(clipped, _MP):
        clipped = max(clipped.geoms, key=lambda g: g.area)
    if clipped.area < MIN_FOOTPRINT_AREA_SQFT:
        return None

    # Update the footprint with clipped geometry
    best.footprint_polygon = clipped
    best.area_sqft = clipped.area

    return best


# ── COP placement for spatial planner ────────────────────────────────────────


def _place_cop_for_layout(
    buildable_core: Polygon,
    plot_polygon: Polygon,
    edge_specs: List[EdgeSpec],
    cop_strategy: str,
    enforce_dimensions: bool,
    required_area_sqft: float,
    min_dimension_dxf: float,
) -> tuple:
    """
    Place COP using COP-FIRST planning approach.

    Returns (cop_polygon, cop_area_sqft, cop_status, cop_centroid).
    """
    # Use new COP-FIRST planner for intelligent strategy
    if cop_strategy == "intelligent":
        from placement_engine.geometry.cop_planner import (
            find_cop_candidate_regions,
            validate_cop_geometry,
        )

        max_aspect_ratio = 3.0 if enforce_dimensions else 5.0

        candidates = find_cop_candidate_regions(
            buildable_core=buildable_core,
            plot_polygon=plot_polygon,
            edge_specs=edge_specs,
            required_area_sqft=required_area_sqft,
            min_dimension_dxf=min_dimension_dxf,
            max_aspect_ratio=max_aspect_ratio,
        )

        if not candidates:
            logger.warning("COP-FIRST planner: no viable candidates found.")
            return None, 0.0, "NO_VIABLE_COP", None

        # Select best candidate
        best = candidates[0]
        cop_centroid = best.centroid

        logger.info(
            "COP-FIRST selected: %s (score=%.3f, area=%.0f sqft, min_dim=%.1fm, aspect=%.1f)",
            best.label, best.score, best.area_sqft, best.min_dimension_m, best.aspect_ratio,
        )

        return best.polygon, best.area_sqft, "CARVED", cop_centroid

    # Fallback to legacy carver for other strategies
    from envelope_engine.geometry.common_plot_carver import carve_common_plot

    effective_strategy = cop_strategy if cop_strategy != "intelligent" else "edge"

    cop_poly, cop_area, cop_status = carve_common_plot(
        plot_polygon=plot_polygon,
        envelope=buildable_core,
        edge_specs=edge_specs,
        cop_strategy=effective_strategy,
    )

    cop_centroid = (cop_poly.centroid.x, cop_poly.centroid.y) if cop_poly else None

    return cop_poly, cop_area, cop_status, cop_centroid


# ── Single attempt at a given constraint level ───────────────────────────────


def _attempt_layout(
    buildable_envelope: Polygon,
    plot_polygon: Polygon,
    n_towers: int,
    building_height_m: float,
    min_width_dxf: float,
    min_depth_dxf: float,
    edge_specs: List[EdgeSpec],
    road_edge_angles_deg: Optional[List[float]],
    cop_strategy: str,
    constraint_level: int,
    target_plate_area_sqft: Optional[float] = None,
) -> Optional[SpatialPlanResult]:
    """
    Single layout attempt at a given constraint relaxation level.
    Returns None if infeasible at this level.
    """
    # ── Step 1: Fire loop ────────────────────────────────────────────────────
    fire_width_m = _fire_width_for_level(constraint_level, building_height_m)
    fire = carve_fire_loop(buildable_envelope, fire_width_m, building_height_m)

    if fire.status == "COLLAPSED" or fire.buildable_core is None:
        logger.info("Level %d: fire loop collapsed — skipping.", constraint_level)
        return None

    core = fire.buildable_core
    if core.is_empty or core.area < MIN_FOOTPRINT_AREA_SQFT:
        logger.info("Level %d: buildable core too small after fire loop.", constraint_level)
        return None

    # ── Step 2: COP (COP-FIRST planning) ─────────────────────────────────────
    enforce_dims = _enforce_cop_dimensions_for_level(constraint_level)
    
    # Compute required COP area
    from architecture.regulatory_accessors import get_cop_required_fraction
    cop_fraction = get_cop_required_fraction()
    required_cop_area_sqft = cop_fraction * plot_polygon.area
    
    # Minimum COP dimension from GDCR
    from rules_engine.rules.loader import get_gdcr_config
    try:
        gdcr = get_gdcr_config()
        cop_cfg = gdcr.get("common_open_plot", {}) or {}
        geom_cfg = cop_cfg.get("geometry_constraints", {}) or {}
        min_cop_dim_m = float(geom_cfg.get("minimum_width_m", 10.0) or 10.0)
    except Exception:
        min_cop_dim_m = 10.0
    
    min_cop_dim_dxf = min_cop_dim_m * METRES_TO_DXF
    
    cop, cop_area, cop_status, cop_centroid = _place_cop_for_layout(
        core, plot_polygon, edge_specs, cop_strategy, enforce_dims,
        required_cop_area_sqft, min_cop_dim_dxf,
    )
    
    # Hard validation: COP must be viable (COP-FIRST requirement)
    if cop_status == "NO_VIABLE_COP":
        logger.info("Level %d: COP-FIRST planner found no viable COP — skipping.", constraint_level)
        return None
    
    if cop is None or cop.is_empty:
        logger.info("Level %d: COP placement failed — skipping.", constraint_level)
        return None
    
    # Validate COP geometry at strict levels
    if constraint_level <= 1:
        from placement_engine.geometry.cop_planner import validate_cop_geometry
        max_aspect = 3.0 if constraint_level == 0 else 4.0
        cop_valid, cop_fail_reason = validate_cop_geometry(cop, min_cop_dim_dxf, max_aspect)
        if not cop_valid:
            logger.info("Level %d: COP geometry invalid — %s", constraint_level, cop_fail_reason)
            return None

    # ── Step 3: Zone decomposition (COP-aware) ───────────────────────────────
    from placement_engine.geometry.spacing_enforcer import required_spacing_dxf as _req_sp_dxf
    spacing_gap = _req_sp_dxf(building_height_m) if n_towers > 1 else 0.0

    zones = decompose_into_zones(
        buildable_core=core,
        n_towers=n_towers,
        cop=cop,
        road_edge_specs=edge_specs,
        min_width_dxf=min_width_dxf,
        spacing_gap_dxf=spacing_gap,
        cop_centroid=cop_centroid,  # NEW: pass COP centroid for zone scoring
    )

    if not zones.zones:
        logger.info("Level %d: zone decomposition produced no viable zones.", constraint_level)
        return None

    # ── Step 4: Place towers in zones (COP-aware) ────────────────────────────
    orientation_tolerance = _orientation_tolerance_for_level(constraint_level)
    allowed_angles = _compute_allowed_angles(road_edge_angles_deg, orientation_tolerance)

    footprints: List[FootprintCandidate] = []
    placed_polygons: List[Polygon] = []

    for zone in zones.zones[:n_towers]:
        # Subtract exclusion zones from previously placed towers
        available = zone.polygon
        if placed_polygons:
            from placement_engine.geometry.spacing_enforcer import compute_exclusion_zone
            for placed_poly in placed_polygons:
                excl = compute_exclusion_zone(placed_poly, building_height_m)
                available = available.difference(excl)
                if available is None or available.is_empty:
                    break

        if available is None or available.is_empty or available.area < MIN_FOOTPRINT_AREA_SQFT:
            continue

        fp = _place_tower_in_zone(
            zone=available,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            allowed_angles=allowed_angles,
            road_edge_angles_deg=road_edge_angles_deg,
            target_plate_area_sqft=target_plate_area_sqft,
            cop_polygon=cop,  # NEW: pass COP for tower scoring
            cop_centroid=cop_centroid,  # NEW: pass COP centroid
        )

        if fp is not None:
            footprints.append(fp)
            placed_polygons.append(fp.footprint_polygon)

    if not footprints:
        logger.info("Level %d: no towers placed in any zone.", constraint_level)
        return None

    # ── Step 5: Hard constraint validation ───────────────────────────────────
    tower_angles = [fp.orientation_angle_deg for fp in footprints]
    constraint_check = check_hard_constraints(
        footprints=[fp.footprint_polygon for fp in footprints],
        fire_loop=fire.fire_loop_polygon,
        cop=cop,
        building_height_m=building_height_m,
        road_angles_deg=road_edge_angles_deg,
        tower_angles_deg=tower_angles,
        constraint_level=constraint_level,
    )

    if not constraint_check.is_valid:
        violation_names = [v.name for v in constraint_check.violations[:3]]
        logger.info(
            "Level %d: hard constraints failed — %s",
            constraint_level, ", ".join(violation_names),
        )
        return None

    # ── Success ──────────────────────────────────────────────────────────────
    total_area = sum(fp.area_sqft for fp in footprints)
    status = "VALID" if constraint_level == 0 else "RELAXED"

    level_suffix = f"_L{constraint_level}" if constraint_level > 0 else ""

    return SpatialPlanResult(
        status=status,
        constraint_level=constraint_level,
        fire_loop=fire,
        zones=zones,
        cop_polygon=cop,
        cop_area_sqft=cop_area,
        cop_centroid=cop_centroid,  # NEW
        footprints=footprints,
        constraint_check=constraint_check,
        packing_mode=f"SPATIAL_PLANNER{level_suffix}",
        n_placed=len(footprints),
        total_area_sqft=total_area,
    )


# ── Main entry point ─────────────────────────────────────────────────────────


def plan_site_layout(
    buildable_envelope: Polygon,
    plot_polygon: Polygon,
    n_towers: int,
    building_height_m: float,
    min_width_dxf: float,
    min_depth_dxf: float,
    edge_specs: List[EdgeSpec],
    road_edge_angles_deg: Optional[List[float]] = None,
    cop_strategy: str = "intelligent",
    target_plate_area_sqft: Optional[float] = None,
) -> SpatialPlanResult:
    """
    Main entry point for the constraint-driven spatial planner.

    Runs the 5-step pipeline with constraint relaxation cascade:
      Level 0: Full compliance (4.5m fire, 10m COP dims, ±5° orientation)
      Level 1: Relaxed fire for low-rise (3.0m if h<15m)
      Level 2: Relaxed COP (area-only, no dimension enforcement)
      Level 3: Relaxed orientation (±15°)
      Level 4: Legacy packer fallback

    Parameters
    ----------
    buildable_envelope    : Legal buildable envelope (DXF feet, post-setback).
    plot_polygon          : Original plot polygon (DXF feet).
    n_towers              : Number of towers to place.
    building_height_m     : Building height in metres.
    min_width_dxf         : Minimum tower footprint width (DXF feet).
    min_depth_dxf         : Minimum tower footprint depth (DXF feet).
    edge_specs            : Classified edge specs from envelope computation.
    road_edge_angles_deg  : Direction angles of road-facing edges (degrees).
    cop_strategy          : COP placement strategy ("intelligent", "edge", "center").
    target_plate_area_sqft: Target per-tower plate area (optional).

    Returns
    -------
    SpatialPlanResult — always returns (never raises).
    """
    # Try constraint levels 0→3
    for level in range(4):
        result = _attempt_layout(
            buildable_envelope=buildable_envelope,
            plot_polygon=plot_polygon,
            n_towers=n_towers,
            building_height_m=building_height_m,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            edge_specs=edge_specs,
            road_edge_angles_deg=road_edge_angles_deg,
            cop_strategy=cop_strategy,
            constraint_level=level,
            target_plate_area_sqft=target_plate_area_sqft,
        )
        if result is not None:
            logger.info(
                "Spatial planner succeeded at level %d: %d/%d towers placed, "
                "total_area=%.0f sqft, mode=%s",
                level, result.n_placed, n_towers,
                result.total_area_sqft, result.packing_mode,
            )
            return result

    # Level 4: Fall back to legacy packer
    logger.info(
        "Spatial planner failed at all levels (0-3) — falling back to legacy packer."
    )
    try:
        from placement_engine.geometry.packer import pack_towers

        packing = pack_towers(
            envelope=buildable_envelope,
            n_towers=n_towers,
            building_height_m=building_height_m,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            road_edge_angles_deg=road_edge_angles_deg,
            target_plate_area_sqft=target_plate_area_sqft,
        )

        return SpatialPlanResult(
            status="FALLBACK",
            constraint_level=4,
            footprints=packing.footprints,
            packing_mode="LEGACY_PACKER",
            n_placed=packing.n_placed,
            total_area_sqft=packing.total_area_sqft,
        )
    except Exception as exc:
        logger.error("Legacy packer fallback also failed: %s", exc)
        return SpatialPlanResult(
            status="INFEASIBLE",
            constraint_level=4,
            packing_mode="INFEASIBLE",
        )
