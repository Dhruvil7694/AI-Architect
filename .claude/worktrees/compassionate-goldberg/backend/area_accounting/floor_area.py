"""
area_accounting/floor_area.py
-----------------------------

Phase 1 DTOs for floor-level area accounting.

This module intentionally contains only dataclasses and simple derived
fields. No geometry or wall/RERA accounting logic lives here; that is
added in later steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Tuple

from detailed_layout.config import DetailingConfig
from detailed_layout.models import DetailedWall
from detailed_layout.wall_engine import build_walls_for_floor
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import UnitLayoutContract


@dataclass(frozen=True)
class FloorAreaBreakdown:
    """
    Deterministic floor-level area breakdown anchored to FloorLayoutContract.

    All areas are in square metres. Ratios are dimensionless and derived
    from the base areas on construction.
    """

    gross_built_up_sqm: float
    core_area_sqm: float
    corridor_area_sqm: float
    shaft_area_sqm: float
    common_area_total_sqm: float

    unit_envelope_area_sqm: float

    internal_wall_area_sqm: float
    external_wall_area_sqm: float

    rera_carpet_area_total_sqm: float
    carpet_per_unit: tuple[float, ...]

    # Derived ratios -----------------------------------------------------------
    common_area_percentage: float = field(init=False)
    carpet_to_bua_ratio: float = field(init=False)
    efficiency_ratio_recomputed: float = field(init=False)

    def __post_init__(self) -> None:
        gb = float(self.gross_built_up_sqm)
        common = float(self.common_area_total_sqm)
        carpet = float(self.rera_carpet_area_total_sqm)
        unit_env = float(self.unit_envelope_area_sqm)

        # Ensure carpet_per_unit is fully immutable even if constructed from a list.
        object.__setattr__(self, "carpet_per_unit", tuple(self.carpet_per_unit))

        common_pct = common / gb if gb > 0.0 else 0.0
        carpet_ratio = carpet / gb if gb > 0.0 else 0.0
        eff_ratio = unit_env / gb if gb > 0.0 else 0.0

        object.__setattr__(self, "common_area_percentage", common_pct)
        object.__setattr__(self, "carpet_to_bua_ratio", carpet_ratio)
        object.__setattr__(self, "efficiency_ratio_recomputed", eff_ratio)


class SharedWallAllocationPolicy(Enum):
    HALF = "half"
    NONE = "none"


def compute_floor_base_areas(floor: FloorLayoutContract) -> dict:
    """
    Compute base footprint/core/corridor/unit areas from a FloorLayoutContract.

    This helper is geometry-only and does not touch walls or RERA; it is
    the foundation for both basic and detailed area accounting.
    """
    gross_built_up_sqm = float(floor.footprint_polygon.area)
    core_area_sqm = float(floor.core_polygon.area) if floor.core_polygon else 0.0
    corridor_area_sqm = (
        float(floor.corridor_polygon.area) if floor.corridor_polygon else 0.0
    )
    shaft_area_sqm = 0.0  # reserved for detailed Phase D accounting

    unit_envelope_area_sqm = float(floor.unit_area_sum or 0.0)

    common_area_total_sqm = core_area_sqm + corridor_area_sqm + shaft_area_sqm

    return {
        "gross_built_up_sqm": gross_built_up_sqm,
        "core_area_sqm": core_area_sqm,
        "corridor_area_sqm": corridor_area_sqm,
        "shaft_area_sqm": shaft_area_sqm,
        "common_area_total_sqm": common_area_total_sqm,
        "unit_envelope_area_sqm": unit_envelope_area_sqm,
    }


def compute_floor_area_breakdown_basic(floor: FloorLayoutContract) -> FloorAreaBreakdown:
    """
    Build a FloorAreaBreakdown using only FloorLayoutContract geometry.

    Wall areas and RERA metrics are set to zero; they are populated only
    by the detailed Phase D-aware accounting layer.
    """
    base = compute_floor_base_areas(floor)

    return FloorAreaBreakdown(
        gross_built_up_sqm=base["gross_built_up_sqm"],
        core_area_sqm=base["core_area_sqm"],
        corridor_area_sqm=base["corridor_area_sqm"],
        shaft_area_sqm=base["shaft_area_sqm"],
        common_area_total_sqm=base["common_area_total_sqm"],
        unit_envelope_area_sqm=base["unit_envelope_area_sqm"],
        internal_wall_area_sqm=0.0,
        external_wall_area_sqm=0.0,
        rera_carpet_area_total_sqm=0.0,
        carpet_per_unit=(),
    )


def _build_wall_index(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
) -> Tuple[
    List[DetailedWall],
    Dict[str, List[DetailedWall]],
    Dict[str, List[DetailedWall]],
    Dict[int, List[str]],
    Dict[str, str],
]:
    """
    Build walls and adjacency indices:
      - all_walls
      - walls_ext_by_room / walls_int_by_room (from wall_engine)
      - wall_id_to_rooms: id(wall) -> [room_id,...]
      - room_id_to_unit_id: room_id -> unit_id
    """
    all_walls, walls_ext_by_room, walls_int_by_room = build_walls_for_floor(
        floor, units, config
    )

    # Derive room_id -> unit_id mapping from the room_id strings actually
    # produced by the wall engine, instead of re-deriving the convention.
    #
    # Convention (shared with detailed_layout.service):
    #   room_id = f"{unit_id or floor_id}_{idx}"
    #
    # We recover unit_id by stripping the last underscore + index segment.
    room_id_to_unit_id: Dict[str, str] = {}

    def _unit_id_from_room_id(room_id: str) -> str:
        if "_" not in room_id:
            return floor.floor_id
        prefix, _ = room_id.rsplit("_", 1)
        return prefix or floor.floor_id

    for mapping in (walls_ext_by_room, walls_int_by_room):
        for room_id in mapping.keys():
            if room_id not in room_id_to_unit_id:
                room_id_to_unit_id[room_id] = _unit_id_from_room_id(room_id)

    # Invert room->walls mappings to wall_id->rooms.
    wall_id_to_rooms: Dict[int, List[str]] = {}

    def _add_rooms(mapping: Dict[str, List[DetailedWall]]) -> None:
        for room_id, walls in mapping.items():
            for wall in walls:
                wid = id(wall)
                wall_id_to_rooms.setdefault(wid, []).append(room_id)

    _add_rooms(walls_ext_by_room)
    _add_rooms(walls_int_by_room)

    return all_walls, walls_ext_by_room, walls_int_by_room, wall_id_to_rooms, room_id_to_unit_id


def _sum_wall_areas_by_type(walls: Iterable[DetailedWall]) -> Tuple[float, float, float]:
    internal = 0.0
    external = 0.0
    shaft = 0.0
    for w in walls:
        if w.wall_type == "INTERNAL":
            internal += float(w.polygon.area)
        elif w.wall_type == "EXTERNAL":
            external += float(w.polygon.area)
        elif w.wall_type == "SHAFT":
            shaft += float(w.polygon.area)
    return internal, external, shaft


def compute_rera_carpet_for_units(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
    shared_policy: SharedWallAllocationPolicy = SharedWallAllocationPolicy.HALF,
) -> Tuple[float, Tuple[float, ...], float, float, float]:
    """
    Compute RERA carpet per unit using room areas and wall allocations.

    Returns:
      - total_carpet
      - carpet_per_unit (tuple, ordered by unit_id)
      - internal_wall_area_sqm
      - external_wall_area_sqm
      - shaft_area_sqm
    """
    (
        all_walls,
        walls_ext_by_room,
        walls_int_by_room,
        wall_id_to_rooms,
        room_id_to_unit_id,
    ) = _build_wall_index(floor, units, config)

    internal_wall_area_sqm, external_wall_area_sqm, shaft_area_sqm = _sum_wall_areas_by_type(
        all_walls
    )

    # Allocate internal wall area to units.
    internal_alloc_per_unit: Dict[str, float] = {}

    # Build quick lookup: id(wall) -> wall object
    id_to_wall: Dict[int, DetailedWall] = {id(w): w for w in all_walls}

    for wid, room_ids in wall_id_to_rooms.items():
        wall = id_to_wall[wid]
        if wall.wall_type != "INTERNAL":
            continue
        unit_ids = {
            room_id_to_unit_id.get(rid, floor.floor_id) for rid in room_ids
        }
        unit_ids = {uid for uid in unit_ids if uid is not None}
        area = float(wall.polygon.area)

        if len(unit_ids) <= 1:
            # Internal partition within a single unit.
            uid = next(iter(unit_ids)) if unit_ids else floor.floor_id
            internal_alloc_per_unit[uid] = internal_alloc_per_unit.get(uid, 0.0) + area
        elif len(unit_ids) == 2:
            # Shared wall between two units.
            if shared_policy is SharedWallAllocationPolicy.HALF:
                share = area / 2.0
                for uid in unit_ids:
                    internal_alloc_per_unit[uid] = internal_alloc_per_unit.get(uid, 0.0) + share
            elif shared_policy is SharedWallAllocationPolicy.NONE:
                # No allocation to either unit.
                continue
        else:
            # More than two units sharing a wall is exotic and indicates an
            # unexpected topology (e.g. junctions not modelled as separate
            # walls). Rather than silently under-allocating, raise so that
            # such cases are made explicit and can be modelled as COMMON in
            # a future refinement.
            raise RuntimeError(
                f"Internal wall shared by >2 units not supported (unit_ids={unit_ids})"
            )

    # Compute carpet per unit: sum(room internal areas) + internal wall allocation.
    unit_id_to_rooms_area: Dict[str, float] = {}
    for unit in units:
        uid = unit.unit_id or floor.floor_id
        total = 0.0
        for room in unit.rooms:
            total += float(room.area_sqm)
        unit_id_to_rooms_area[uid] = total

    ordered_unit_ids = sorted(unit_id_to_rooms_area.keys())
    carpet_per_unit_list: List[float] = []
    for uid in ordered_unit_ids:
        rooms_area = unit_id_to_rooms_area.get(uid, 0.0)
        wall_alloc = internal_alloc_per_unit.get(uid, 0.0)
        carpet_per_unit_list.append(rooms_area + wall_alloc)

    total_carpet = sum(carpet_per_unit_list)
    return (
        total_carpet,
        tuple(carpet_per_unit_list),
        internal_wall_area_sqm,
        external_wall_area_sqm,
        shaft_area_sqm,
    )


def compute_floor_area_breakdown_detailed(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
    shared_policy: SharedWallAllocationPolicy = SharedWallAllocationPolicy.HALF,
) -> FloorAreaBreakdown:
    """
    Full detailed FloorAreaBreakdown using walls + RERA from Phase D.
    """
    base = compute_floor_base_areas(floor)

    (
        rera_total,
        carpet_per_unit,
        internal_wall_area_sqm,
        external_wall_area_sqm,
        shaft_area_sqm,
    ) = compute_rera_carpet_for_units(
        floor=floor,
        units=units,
        config=config,
        shared_policy=shared_policy,
    )

    # Recompute common area total as core + corridor + shaft walls.
    common_area = (
        base["core_area_sqm"]
        + base["corridor_area_sqm"]
        + float(shaft_area_sqm)
    )

    return FloorAreaBreakdown(
        gross_built_up_sqm=base["gross_built_up_sqm"],
        core_area_sqm=base["core_area_sqm"],
        corridor_area_sqm=base["corridor_area_sqm"],
        shaft_area_sqm=float(shaft_area_sqm),
        common_area_total_sqm=common_area,
        unit_envelope_area_sqm=base["unit_envelope_area_sqm"],
        internal_wall_area_sqm=float(internal_wall_area_sqm),
        external_wall_area_sqm=float(external_wall_area_sqm),
        rera_carpet_area_total_sqm=float(rera_total),
        carpet_per_unit=carpet_per_unit,
    )


def build_floor_layout_with_area(
    floor: FloorLayoutContract,
    *,
    config: DetailingConfig,
    shared_policy: SharedWallAllocationPolicy = SharedWallAllocationPolicy.HALF,
    detailed: bool = True,
) -> Tuple[FloorLayoutContract, FloorAreaBreakdown]:
    """
    Convenience helper that pairs an existing FloorLayoutContract with
    a FloorAreaBreakdown.

    Does not modify FloorLayoutContract; callers can choose whether to
    include detailed wall/RERA accounting (detailed=True) or only the
    base geometry metrics (detailed=False).
    """
    units = list(floor.all_units)
    if detailed:
        area = compute_floor_area_breakdown_detailed(
            floor=floor,
            units=units,
            config=config,
            shared_policy=shared_policy,
        )
    else:
        area = compute_floor_area_breakdown_basic(floor)
    return floor, area

