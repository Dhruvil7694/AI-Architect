"""
detailed_layout/service.py — orchestration entrypoints for Phase D.

Provides:
  - detail_floor_layout(FloorLayoutContract, DetailingConfig)
  - detail_building_layout(BuildingLayoutContract, DetailingConfig)
"""

from __future__ import annotations

from typing import Dict

from detailed_layout.config import DetailingConfig
from detailed_layout.door_engine import build_doors_for_floor
from detailed_layout.models import (
    DetailedBuildingLayoutContract,
    DetailedFloorLayoutContract,
    DetailedRoomGeometry,
    DetailedUnitGeometry,
)
from detailed_layout.wet_area_engine import build_wet_areas_for_floor
from detailed_layout.furniture_engine import build_furniture_for_floor
from detailed_layout.core_stair_engine import build_core_for_floor
from detailed_layout.balcony_engine import build_balconies_for_floor
from detailed_layout.annotation_engine import annotate_floor_global, annotate_rooms
from detailed_layout.validation import validate_detailed_floor
from detailed_layout.wall_engine import build_walls_for_floor
from detailed_layout.window_engine import build_windows_for_floor
from residential_layout.building_aggregation import BuildingLayoutContract
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import UnitLayoutContract


def detail_floor_layout(
    floor: FloorLayoutContract,
    config: DetailingConfig,
) -> DetailedFloorLayoutContract:
    """
    Convert a FloorLayoutContract into a DetailedFloorLayoutContract.

    Phase D is read-only with respect to engine contracts.
    """
    units: list[UnitLayoutContract] = list(floor.all_units)

    # Walls
    all_walls, walls_ext_by_room, walls_int_by_room = build_walls_for_floor(
        floor, units, config
    )

    # Doors and windows
    doors_by_room, entry_by_unit = build_doors_for_floor(floor, units, config)
    windows_by_room = build_windows_for_floor(floor, units, config)

    # Wet areas and furniture
    fixtures_by_room = build_wet_areas_for_floor(floor, units, config)
    # For furniture, use combined walls for collision tests
    walls_by_room: Dict[str, list] = {}
    for room_id, lst in walls_ext_by_room.items():
        walls_by_room.setdefault(room_id, []).extend(lst)
    for room_id, lst in walls_int_by_room.items():
        walls_by_room.setdefault(room_id, []).extend(lst)
    furniture_by_room = build_furniture_for_floor(
        floor, units, walls_by_room, doors_by_room, config
    )

    # Core/stair and balconies (shared elements)
    cores, stairs = build_core_for_floor(floor)
    balconies_by_room = build_balconies_for_floor(floor, units)

    # Build room and unit structures
    detailed_units: Dict[str, DetailedUnitGeometry] = {}
    room_index: Dict[str, DetailedRoomGeometry] = {}

    for unit in units:
        unit_id = unit.unit_id or ""
        rooms: Dict[str, DetailedRoomGeometry] = {}
        for idx, room in enumerate(unit.rooms):
            room_id = f"{unit_id}_{idx}"
            dr = DetailedRoomGeometry(
                room_id=room_id,
                room_type=room.room_type,
                footprint=room.polygon,
            )
            dr.walls_ext = list(walls_ext_by_room.get(room_id, []))
            dr.walls_int = list(walls_int_by_room.get(room_id, []))
            dr.doors = list(doors_by_room.get(room_id, []))
            dr.windows = list(windows_by_room.get(room_id, []))
            dr.fixtures = list(fixtures_by_room.get(room_id, []))
            dr.furniture = list(furniture_by_room.get(room_id, []))
            rooms[room_id] = dr
            room_index[room_id] = dr

        detailed_units[unit_id] = DetailedUnitGeometry(
            unit_id=unit_id,
            rooms=rooms,
            entry_door=entry_by_unit.get(unit_id),
            unit_outline=floor.footprint_polygon,  # approximation; can refine later
        )

    detailed_floor = DetailedFloorLayoutContract(
        floor_id=floor.floor_id,
        units=detailed_units,
    )
    # Attach shared core/stairs/balconies
    detailed_floor.cores = list(cores)
    detailed_floor.stairs = list(stairs)
    for room_id, bals in balconies_by_room.items():
        detailed_floor.balconies.extend(bals)

    # Annotations and validation
    if config.annotation_enabled:
        annotate_rooms(detailed_floor, config)
        annotate_floor_global(detailed_floor, config)
    validate_detailed_floor(detailed_floor, config)
    return detailed_floor


def detail_building_layout(
    building: BuildingLayoutContract,
    config: DetailingConfig,
) -> DetailedBuildingLayoutContract:
    """Detail every floor in a BuildingLayoutContract."""
    detailed_floors = [
        detail_floor_layout(floor, config) for floor in building.floors
    ]
    return DetailedBuildingLayoutContract(
        building_id=building.building_id,
        floors=detailed_floors,
    )

