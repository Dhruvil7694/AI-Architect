"""
residential_layout/floor_aggregation.py — Phase 4 Floor Aggregation Engine.

Takes a FloorSkeleton, runs Phase 3 (repeat_band) for every band, aggregates
BandLayoutContracts into a single FloorLayoutContract. Deterministic; no
skeleton mutation; no strategy or AI. Mandatory skeleton assertions (band-overlap,
band inside footprint) run before any band work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shapely.geometry import Polygon

from floor_skeleton.models import FloorSkeleton, UnitZone

from residential_layout.frames import derive_unit_local_frame
from residential_layout.models import UnitLayoutContract
from residential_layout.repetition import (
    BandLayoutContract,
    BandRepetitionError,
    DEFAULT_MODULE_WIDTH_M,
    repeat_band,
)
from ai_planner.program_generator import ProgramSpec

_TOL = 1e-6


# ── Exceptions ────────────────────────────────────────────────────────────────


class FloorAggregationError(Exception):
    """Raised when a band fails (e.g. BandRepetitionError). Wraps cause for floor context."""

    def __init__(
        self,
        message: str,
        band_id: int,
        slice_index: int,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.band_id = band_id
        self.slice_index = slice_index
        self.cause = cause


class FloorAggregationValidationError(Exception):
    """Raised when floor-level or skeleton assertions fail."""

    def __init__(self, message: str, reason: Optional[str] = None):
        super().__init__(message)
        self.reason = reason


# ── Output contract ───────────────────────────────────────────────────────────


@dataclass
class FloorLayoutContract:
    """
    Phase 4 output: full floor layout from all bands.

    unit polygons: separate (one UnitLayoutContract per slice).
    room geometries: slice-local (Phase 2/3); not transformed.
    unit_id format: "{floor_id}_{band_id}_{slice_index}".
    """

    floor_id: str
    band_layouts: list[BandLayoutContract]
    all_units: list[UnitLayoutContract]
    core_polygon: Polygon
    corridor_polygon: Optional[Polygon]
    footprint_polygon: Polygon
    total_units: int
    total_residual_area: float
    unit_area_sum: float
    average_unit_area: float
    corridor_area: float
    efficiency_ratio_floor: float


# ── Skeleton assertions (plan Section 7a) ─────────────────────────────────────


def _assert_band_overlap(skeleton: FloorSkeleton) -> None:
    """For all pairs (i, j) with i < j: intersection area <= tol. Raises FloorAggregationValidationError."""
    zones = skeleton.unit_zones
    for i in range(len(zones)):
        for j in range(i + 1, len(zones)):
            inter = zones[i].polygon.intersection(zones[j].polygon)
            if inter.is_empty:
                continue
            if inter.area > _TOL:
                raise FloorAggregationValidationError(
                    f"Band overlap: zones {i} and {j} intersect with area {inter.area}",
                    reason="band_overlap",
                )


def _assert_band_inside_footprint(skeleton: FloorSkeleton) -> None:
    """For every unit zone: zone.polygon contained in footprint. Raises FloorAggregationValidationError."""
    footprint = skeleton.footprint_polygon
    for i, zone in enumerate(skeleton.unit_zones):
        # Zone must be fully inside footprint (Shapely: footprint contains zone).
        if not footprint.contains(zone.polygon):
            raise FloorAggregationValidationError(
                f"Band {i} not contained in footprint",
                reason="band_not_in_footprint",
            )


def _run_skeleton_assertions(skeleton: FloorSkeleton) -> None:
    """Run mandatory band-overlap and band-inside-footprint checks. Fail fast before band loop."""
    _assert_band_overlap(skeleton)
    _assert_band_inside_footprint(skeleton)


# ── Post-aggregation validation ─────────────────────────────────────────────


def _validate_floor(
    band_layouts: list[BandLayoutContract],
    all_units: list[UnitLayoutContract],
    total_units: int,
) -> None:
    """total_units consistency: total_units == sum(b.n_units) == len(all_units)."""
    n_from_bands = sum(b.n_units for b in band_layouts)
    if total_units != n_from_bands:
        raise FloorAggregationValidationError(
            f"total_units={total_units} != sum(b.n_units)={n_from_bands}",
            reason="total_units_consistency",
        )
    if total_units != len(all_units):
        raise FloorAggregationValidationError(
            f"total_units={total_units} != len(all_units)={len(all_units)}",
            reason="total_units_consistency",
        )


# ── Public API ────────────────────────────────────────────────────────────────


def build_floor_layout(
    skeleton: FloorSkeleton,
    floor_id: str = "",
    module_width_m: Optional[float] = None,
    program_spec: Optional[ProgramSpec] = None,
) -> FloorLayoutContract:
    """
    Phase 4 entry point: run repeat_band for every unit zone, aggregate into FloorLayoutContract.

    Skeleton assertions (band-overlap, band inside footprint) run first. On BandRepetitionError
    from any band, re-raise (abort entire floor). No partial result.
    """
    if module_width_m is None:
        module_width_m = DEFAULT_MODULE_WIDTH_M

    band_layouts: list[BandLayoutContract] = []
    all_units: list[UnitLayoutContract] = []

    # Step 2: Mandatory skeleton assertions (before any band work)
    if skeleton.unit_zones:
        _run_skeleton_assertions(skeleton)

    # Step 3: Iterate bands
    for zone_index in range(len(skeleton.unit_zones)):
        zone = skeleton.unit_zones[zone_index]
        frame = derive_unit_local_frame(skeleton, zone_index)
        try:
            band_contract = repeat_band(
                zone,
                frame,
                module_width_m,
                program_spec=program_spec,
            )
        except BandRepetitionError as e:
            raise FloorAggregationError(
                f"Band {e.band_id} failed at slice {e.slice_index}: {e}",
                band_id=e.band_id,
                slice_index=e.slice_index,
                cause=e,
            ) from e
        band_layouts.append(band_contract)
        # Mutate unit_id in-place: repeat_band does not cache contracts elsewhere; these
        # are the only references. Same objects live in band_layouts[].units and all_units.
        for slice_i, unit in enumerate(band_contract.units):
            unit.unit_id = f"{floor_id}_{band_contract.band_id}_{slice_i}"
            all_units.append(unit)

    # Step 4: Geometry (no recomputation)
    core_polygon = skeleton.core_polygon
    corridor_polygon = skeleton.corridor_polygon
    footprint_polygon = skeleton.footprint_polygon

    # Step 5: Totals and metrics
    total_units = len(all_units)
    total_residual_area = sum(
        b.residual_width_m * skeleton.unit_zones[b.band_id].zone_depth_m
        for b in band_layouts
    )
    unit_area_sum = sum(
        b.n_units * module_width_m * skeleton.unit_zones[b.band_id].zone_depth_m
        for b in band_layouts
    )
    corridor_area = (
        skeleton.corridor_polygon.area if skeleton.corridor_polygon else 0.0
    )
    fp_area = footprint_polygon.area
    average_unit_area = unit_area_sum / total_units if total_units > 0 else 0.0
    efficiency_ratio_floor = (
        unit_area_sum / fp_area if fp_area > 0 else 0.0
    )

    # Step 6: Build contract
    contract = FloorLayoutContract(
        floor_id=floor_id,
        band_layouts=band_layouts,
        all_units=all_units,
        core_polygon=core_polygon,
        corridor_polygon=corridor_polygon,
        footprint_polygon=footprint_polygon,
        total_units=total_units,
        total_residual_area=total_residual_area,
        unit_area_sum=unit_area_sum,
        average_unit_area=average_unit_area,
        corridor_area=corridor_area,
        efficiency_ratio_floor=efficiency_ratio_floor,
    )

    # Step 7: Validation (after aggregation)
    _validate_floor(band_layouts, all_units, total_units)

    return contract
