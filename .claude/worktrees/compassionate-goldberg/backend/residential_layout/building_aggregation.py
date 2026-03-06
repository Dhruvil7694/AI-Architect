"""
residential_layout/building_aggregation.py — Phase 5 Building Aggregation Layer.

Consumes Phase 4 (FloorLayoutContract) only. Takes one FloorSkeleton, height_limit_m,
storey_height_m; determines num_floors; calls build_floor_layout once per floor (or reuses
first_floor_contract for floor 0); aggregates into BuildingLayoutContract.
Deterministic; no geometry recomputation; abort on first floor failure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from floor_skeleton.models import FloorSkeleton

from residential_layout.floor_aggregation import (
    FloorAggregationError,
    FloorAggregationValidationError,
    FloorLayoutContract,
    build_floor_layout,
)

_VALIDATION_TOL = 1e-6


# ── Exceptions ────────────────────────────────────────────────────────────────


class BuildingAggregationError(Exception):
    """Raised when build_floor_layout fails for a floor. Wraps floor index and cause."""

    def __init__(
        self,
        message: str,
        floor_index: int,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.floor_index = floor_index
        self.cause = cause


class BuildingAggregationValidationError(Exception):
    """Raised when _validate_building detects invariant violation."""

    def __init__(self, message: str, reason: Optional[str] = None):
        super().__init__(message)
        self.reason = reason


# ── Output contract ───────────────────────────────────────────────────────────


@dataclass
class BuildingLayoutContract:
    """
    Phase 5 output: stacked floor contracts and building-level metrics.

    Assumes identical slab footprint for all floors for building_efficiency.
    Assumes Phase 4 unit_id format (floor_id prefix) for uniqueness across building.
    """

    building_id: str
    floors: list[FloorLayoutContract]
    total_floors: int
    total_units: int
    total_unit_area: float
    total_residual_area: float
    building_efficiency: float
    building_height_m: float


# ── Validation ─────────────────────────────────────────────────────────────────


def _validate_building(
    contract: BuildingLayoutContract,
    storey_height_m: float,
) -> None:
    """
    Optional validation: total_units, total_floors, building_height_m consistency.
    Raises BuildingAggregationValidationError on failure.
    """
    summed_units = sum(f.total_units for f in contract.floors)
    if contract.total_units != summed_units:
        raise BuildingAggregationValidationError(
            f"total_units={contract.total_units} != sum(floor.total_units)={summed_units}",
            reason="total_units_consistency",
        )
    if contract.total_floors != len(contract.floors):
        raise BuildingAggregationValidationError(
            f"total_floors={contract.total_floors} != len(floors)={len(contract.floors)}",
            reason="total_floors_consistency",
        )
    expected_height = contract.total_floors * storey_height_m
    if abs(contract.building_height_m - expected_height) > _VALIDATION_TOL:
        raise BuildingAggregationValidationError(
            f"building_height_m={contract.building_height_m} != "
            f"total_floors*storey_height_m={expected_height}",
            reason="building_height_consistency",
        )


# ── Public API ─────────────────────────────────────────────────────────────────


def build_building_layout(
    skeleton: FloorSkeleton,
    height_limit_m: float,
    storey_height_m: float,
    building_id: str = "",
    module_width_m: Optional[float] = None,
    first_floor_contract: Optional[FloorLayoutContract] = None,
) -> BuildingLayoutContract:
    """
    Phase 5 entry point: resolve num_floors, build or reuse floor layouts, aggregate.

    When first_floor_contract is provided (e.g. from pipeline Step 5b), it is used
    as floor 0 and build_floor_layout is called only for floors 1..num_floors-1.
    On any FloorAggregationError or FloorAggregationValidationError, wraps in
    BuildingAggregationError and re-raises; no partial building returned.
    """
    num_floors = max(0, math.floor(height_limit_m / storey_height_m))
    if num_floors == 0:
        return BuildingLayoutContract(
            building_id=building_id,
            floors=[],
            total_floors=0,
            total_units=0,
            total_unit_area=0.0,
            total_residual_area=0.0,
            building_efficiency=0.0,
            building_height_m=0.0,
        )

    floors: list[FloorLayoutContract] = []

    if first_floor_contract is not None:
        floors.append(first_floor_contract)
        floor_range = range(1, num_floors)
    else:
        floor_range = range(num_floors)

    for i in floor_range:
        floor_id = f"L{i}"
        try:
            floor_contract = build_floor_layout(
                skeleton,
                floor_id=floor_id,
                module_width_m=module_width_m,
            )
        except (FloorAggregationError, FloorAggregationValidationError) as e:
            raise BuildingAggregationError(
                f"Floor {i} failed: {e}",
                floor_index=i,
                cause=e,
            ) from e
        floors.append(floor_contract)

    total_floors = len(floors)
    total_units = sum(f.total_units for f in floors)
    total_unit_area = sum(f.unit_area_sum for f in floors)
    total_residual_area = sum(f.total_residual_area for f in floors)
    footprint_area_sqm = skeleton.footprint_polygon.area
    if total_floors > 0 and footprint_area_sqm > 0:
        building_efficiency = total_unit_area / (footprint_area_sqm * total_floors)
    else:
        building_efficiency = 0.0
    building_height_m = total_floors * storey_height_m

    contract = BuildingLayoutContract(
        building_id=building_id,
        floors=floors,
        total_floors=total_floors,
        total_units=total_units,
        total_unit_area=total_unit_area,
        total_residual_area=total_residual_area,
        building_efficiency=building_efficiency,
        building_height_m=building_height_m,
    )

    _validate_building(contract, storey_height_m)
    return contract
