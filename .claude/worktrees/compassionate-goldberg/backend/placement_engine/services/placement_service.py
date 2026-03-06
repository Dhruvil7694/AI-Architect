"""
placement_engine/services/placement_service.py
-----------------------------------------------
Orchestrates the full placement pipeline:

  1. Validate inputs.
  2. Parse envelope WKT to a Shapely Polygon.
  3. Pre-check envelope size.
  4. Call pack_towers() — runs both ROW_WISE and COL_WISE strategies.
  5. Determine final status.
  6. Return a PlacementResult dataclass (pure Python, no ORM).

A separate save_placement() function persists the result to the database
using BuildingPlacement + FootprintRecord models.

Unit contract
-------------
- envelope_wkt is in DXF feet (SRID=0), identical to PlotEnvelope.envelope_geom.
- building_height_m is always in metres.
- All DXF dimensions in PlacementResult are in feet.
- All _m dimensions in PlacementResult are in metres.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from django.contrib.gis.geos import GEOSGeometry
from shapely.wkt import loads as shapely_loads
from shapely.geometry import Polygon

from placement_engine.geometry import (
    METRES_TO_DXF,
    DXF_TO_METRES,
    MIN_FOOTPRINT_AREA_SQFT,
    MIN_FOOTPRINT_WIDTH_M,
    MIN_FOOTPRINT_DEPTH_M,
    FootprintCandidate,
)
from placement_engine.geometry.orientation_finder import find_orientation
from placement_engine.geometry.packer import pack_towers, PackingResult
from placement_engine.geometry.spacing_enforcer import (
    required_spacing_m,
    required_spacing_dxf,
)
from placement_engine.geometry.core_fit import (
    validate_core_fit,
    CoreDimensions,
    CoreValidationResult,
    NO_CORE_FIT,
)
from placement_engine.models import BuildingPlacement, FootprintRecord


# ── PlacementResult dataclass ──────────────────────────────────────────────────

@dataclass
class PlacementResult:
    """
    Pure-Python result of a placement computation.

    This dataclass is independent of Django ORM — it can be used in tests,
    serialised to JSON, or persisted via save_placement().
    """
    status:                  str
    n_towers_requested:      int
    n_towers_placed:         int
    building_height_m:       float
    spacing_required_m:      float
    spacing_required_dxf:    float

    # Orientation (from envelope's MBR)
    orientation_primary_deg:   Optional[float]
    orientation_secondary_deg: Optional[float]

    # Which packing strategy won
    packing_mode: Optional[str]       # "ROW_WISE" | "COL_WISE" | None

    # Grid resolution used for the first tower (informational)
    grid_resolution_dxf: Optional[float]

    # Placed footprints
    footprints:           list[FootprintCandidate] = field(default_factory=list)

    # Spacing audit entries
    placement_audit:      list[dict] = field(default_factory=list)

    # Core fit validation — one entry per placed tower
    per_tower_core_validation: list[CoreValidationResult] = field(default_factory=list)

    error_message:        str = ""


# ── Main compute function ──────────────────────────────────────────────────────

def compute_placement(
    envelope_wkt:       str,
    building_height_m:  float,
    n_towers:           int,
    min_width_m:        float = MIN_FOOTPRINT_WIDTH_M,
    min_depth_m:        float = MIN_FOOTPRINT_DEPTH_M,
) -> PlacementResult:
    """
    Compute building placement(s) inside the given envelope.

    Parameters
    ----------
    envelope_wkt      : WKT of the buildable envelope polygon (DXF feet).
    building_height_m : Proposed building height in metres.
    n_towers          : Number of towers requested.
    min_width_m       : Minimum acceptable footprint width in metres (default 5 m).
    min_depth_m       : Minimum acceptable footprint depth in metres (default 4 m).

    Returns
    -------
    PlacementResult — fully populated, ready for display or persistence.
    """
    # ── Input validation ───────────────────────────────────────────────────────
    if n_towers < 1:
        return _error_result("INVALID_INPUT", "n_towers must be >= 1",
                             building_height_m, n_towers)
    if building_height_m <= 0:
        return _error_result("INVALID_INPUT", "building_height_m must be > 0",
                             building_height_m, n_towers)
    if not envelope_wkt or not envelope_wkt.strip():
        return _error_result("INVALID_INPUT", "envelope_wkt is empty",
                             building_height_m, n_towers)

    # ── Parse geometry ─────────────────────────────────────────────────────────
    try:
        envelope: Polygon = shapely_loads(envelope_wkt)
    except Exception as exc:
        return _error_result("INVALID_INPUT", f"Cannot parse envelope WKT: {exc}",
                             building_height_m, n_towers)

    if not envelope.is_valid or envelope.is_empty:
        return _error_result("INVALID_INPUT", "Envelope polygon is invalid or empty",
                             building_height_m, n_towers)

    # ── Pre-check envelope size ────────────────────────────────────────────────
    if envelope.area < MIN_FOOTPRINT_AREA_SQFT:
        return PlacementResult(
            status="NO_FIT",
            n_towers_requested=n_towers,
            n_towers_placed=0,
            building_height_m=building_height_m,
            spacing_required_m=required_spacing_m(building_height_m),
            spacing_required_dxf=required_spacing_dxf(building_height_m),
            orientation_primary_deg=None,
            orientation_secondary_deg=None,
            packing_mode=None,
            grid_resolution_dxf=None,
            error_message=(
                f"Envelope area {envelope.area:.1f} sq.ft < "
                f"minimum {MIN_FOOTPRINT_AREA_SQFT} sq.ft"
            ),
        )

    # ── Compute orientation for audit ──────────────────────────────────────────
    orient = find_orientation(envelope)

    # ── Convert min dimensions to DXF ─────────────────────────────────────────
    min_width_dxf = min_width_m * METRES_TO_DXF
    min_depth_dxf = min_depth_m * METRES_TO_DXF

    # ── Run packing ────────────────────────────────────────────────────────────
    try:
        packing: PackingResult = pack_towers(
            envelope=envelope,
            n_towers=n_towers,
            building_height_m=building_height_m,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
        )
    except Exception as exc:
        return _error_result("ERROR", f"Packing failed: {exc}",
                             building_height_m, n_towers)

    # ── Determine geometric status ─────────────────────────────────────────────
    if packing.n_placed == 0:
        status = "NO_FIT"
    elif packing.n_placed < n_towers or packing.has_spacing_fail:
        status = "TOO_TIGHT"
    else:
        status = "VALID"

    grid_res = (
        packing.footprints[0].grid_resolution_dxf
        if packing.footprints else None
    )

    # ── Core fit validation (per placed tower) ─────────────────────────────────
    core_validations: list[CoreValidationResult] = []
    if packing.footprints:
        for fp in packing.footprints:
            cv = validate_core_fit(fp.width_m, fp.depth_m, building_height_m)
            core_validations.append(cv)

        # Upgrade status if any tower cannot fit a compliant core
        if status not in ("NO_FIT",) and any(
            cv.core_fit_status == NO_CORE_FIT for cv in core_validations
        ):
            status = "NO_FIT_CORE"

    return PlacementResult(
        status=status,
        n_towers_requested=n_towers,
        n_towers_placed=packing.n_placed,
        building_height_m=building_height_m,
        spacing_required_m=required_spacing_m(building_height_m),
        spacing_required_dxf=required_spacing_dxf(building_height_m),
        orientation_primary_deg=orient.angle_primary_deg,
        orientation_secondary_deg=orient.angle_secondary_deg,
        packing_mode=packing.mode,
        grid_resolution_dxf=grid_res,
        footprints=packing.footprints,
        placement_audit=packing.spacing_audit,
        per_tower_core_validation=core_validations,
        error_message="",
    )


# ── Database persistence ───────────────────────────────────────────────────────

def save_placement(
    result:      PlacementResult,
    envelope_db, # PlotEnvelope ORM instance
) -> BuildingPlacement:
    """
    Persist a PlacementResult to the database.

    Parameters
    ----------
    result      : PlacementResult from compute_placement().
    envelope_db : PlotEnvelope ORM instance.

    Returns
    -------
    The saved BuildingPlacement instance.
    """
    bp = BuildingPlacement.objects.create(
        envelope=envelope_db,
        status=result.status,
        error_message=result.error_message,
        n_towers_requested=result.n_towers_requested,
        n_towers_placed=result.n_towers_placed,
        building_height_m=result.building_height_m,
        spacing_required_m=result.spacing_required_m,
        spacing_required_dxf=result.spacing_required_dxf,
        orientation_primary_deg=result.orientation_primary_deg,
        orientation_secondary_deg=result.orientation_secondary_deg,
        packing_mode=result.packing_mode,
        grid_resolution_dxf=result.grid_resolution_dxf,
        placement_audit=result.placement_audit,
    )

    # Build per-tower spacing lookup from audit entries
    spacing_by_tower: dict[int, list[float]] = {}
    for entry in result.placement_audit:
        gap_dxf = entry["gap_dxf"]
        for idx in entry["pair"]:
            spacing_by_tower.setdefault(idx, []).append(gap_dxf)

    for i, fp in enumerate(result.footprints):
        # Convert Shapely polygon to GEOS for Django
        geos_geom = GEOSGeometry(fp.footprint_polygon.wkt, srid=0)

        gaps = spacing_by_tower.get(i, [])
        min_gap_dxf = min(gaps) if gaps else None
        min_gap_m   = min_gap_dxf * DXF_TO_METRES if min_gap_dxf is not None else None

        # Determine spacing status for this tower
        if len(result.footprints) == 1:
            sp_status = "NA"
        else:
            req_dxf = result.spacing_required_dxf
            sp_status = "PASS" if (min_gap_dxf is not None and min_gap_dxf >= req_dxf - 1e-6) else "FAIL"

        # Core validation dict for this tower (empty dict if not computed)
        core_dict = {}
        if i < len(result.per_tower_core_validation):
            core_dict = result.per_tower_core_validation[i].to_dict()

        FootprintRecord.objects.create(
            placement=bp,
            tower_index=i,
            footprint_geom=geos_geom,
            footprint_area_sqft=fp.area_sqft,
            footprint_width_dxf=fp.width_dxf,
            footprint_depth_dxf=fp.depth_dxf,
            footprint_width_m=fp.width_m,
            footprint_depth_m=fp.depth_m,
            orientation_angle_deg=fp.orientation_angle_deg,
            orientation_label=fp.orientation_label,
            source_component_index=fp.source_component_index,
            grid_resolution_dxf=fp.grid_resolution_dxf,
            min_spacing_to_adjacent_dxf=min_gap_dxf,
            min_spacing_to_adjacent_m=min_gap_m,
            spacing_status=sp_status,
            core_validation=core_dict,
        )

    return bp


# ── Helpers ────────────────────────────────────────────────────────────────────

def _error_result(
    status:           str,
    message:          str,
    building_height_m: float,
    n_towers:         int,
) -> PlacementResult:
    return PlacementResult(
        status=status,
        n_towers_requested=n_towers,
        n_towers_placed=0,
        building_height_m=building_height_m,
        spacing_required_m=required_spacing_m(max(building_height_m, 0.1)),
        spacing_required_dxf=required_spacing_dxf(max(building_height_m, 0.1)),
        orientation_primary_deg=None,
        orientation_secondary_deg=None,
        packing_mode=None,
        grid_resolution_dxf=None,
        error_message=message,
    )
