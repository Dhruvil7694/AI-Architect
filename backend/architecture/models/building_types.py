from __future__ import annotations

from dataclasses import dataclass
from typing import List

from rules_engine.rules.loader import get_gdcr_config
from architecture.regulatory_accessors import get_max_permissible_height_by_road_width


@dataclass(frozen=True)
class BuildingType:
    id: int
    label: str
    max_height_m: float
    max_floors: int
    lift_required: bool
    fire_stair_required: bool
    refuge_area_required: bool
    min_road_width_m: float
    cop_required: bool
    typical_efficiency_ratio: float
    notes: str
    effective_max_floors: int = 0


def _load_building_types() -> list[dict]:
    gdcr = get_gdcr_config() or {}
    return gdcr.get("building_types", [])


def get_building_type(type_id: int) -> BuildingType:
    for raw in _load_building_types():
        if int(raw.get("id", 0)) == type_id:
            return BuildingType(
                id=int(raw["id"]),
                label=str(raw.get("label", "")),
                max_height_m=float(raw.get("max_height_m", 0)),
                max_floors=int(raw.get("max_floors", 0)),
                lift_required=bool(raw.get("lift_required", False)),
                fire_stair_required=bool(raw.get("fire_stair_required", False)),
                refuge_area_required=bool(raw.get("refuge_area_required", False)),
                min_road_width_m=float(raw.get("min_road_width_m", 0)),
                cop_required=bool(raw.get("cop_required", False)),
                typical_efficiency_ratio=float(raw.get("typical_efficiency_ratio", 0.55)),
                notes=str(raw.get("notes", "")),
            )
    raise ValueError(f"Unknown building type: {type_id}")


def get_permissible_building_types(
    road_width_m: float,
    storey_height_m: float = 3.0,
) -> List[BuildingType]:
    road_height_cap = get_max_permissible_height_by_road_width(road_width_m)
    result = []
    for raw in _load_building_types():
        bt = get_building_type(int(raw["id"]))
        if road_width_m < bt.min_road_width_m:
            continue
        effective_height = min(bt.max_height_m, road_height_cap)
        effective_floors = min(bt.max_floors, int(effective_height / storey_height_m))
        if effective_floors < 1:
            continue
        result.append(BuildingType(
            id=bt.id,
            label=bt.label,
            max_height_m=effective_height,
            max_floors=bt.max_floors,
            lift_required=bt.lift_required,
            fire_stair_required=bt.fire_stair_required,
            refuge_area_required=bt.refuge_area_required,
            min_road_width_m=bt.min_road_width_m,
            cop_required=bt.cop_required,
            typical_efficiency_ratio=bt.typical_efficiency_ratio,
            notes=bt.notes,
            effective_max_floors=effective_floors,
        ))
    return result
