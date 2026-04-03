from __future__ import annotations

"""
planning.unit_library
---------------------

Central catalogue of residential unit archetypes used by the AI planner.

Values are intentionally coarse — they are NOT used for geometry generation.
They only inform high-level program sizing and density heuristics.
"""

from typing import Dict, TypedDict


class UnitTypeInfo(TypedDict):
    unit_area_sqm: float
    units_per_floor: int


UNIT_LIBRARY: Dict[str, UnitTypeInfo] = {
    "1bhk_compact": {
        "unit_area_sqm": 45.0,
        "units_per_floor": 8,
    },
    "2bhk_compact": {
        "unit_area_sqm": 70.0,
        "units_per_floor": 6,
    },
    "2bhk_luxury": {
        "unit_area_sqm": 110.0,
        "units_per_floor": 4,
    },
    "3bhk_luxury": {
        "unit_area_sqm": 140.0,
        "units_per_floor": 3,
    },
}


__all__ = ["UNIT_LIBRARY", "UnitTypeInfo"]

