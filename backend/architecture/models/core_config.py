from __future__ import annotations

from dataclasses import dataclass
from typing import List

# Approximate unit widths along corridor (metres) — from feasibility_advisor
_UNIT_WIDTHS = {
    "1BHK": 3.0, "2BHK": 4.0, "3BHK": 5.5, "4BHK": 7.0, "5BHK": 9.0,
}
_UNIT_DEPTHS = {
    "1BHK": 3.0, "2BHK": 3.5, "3BHK": 4.0, "4BHK": 4.5, "5BHK": 5.0,
}
_UNIT_AREAS = {
    "1BHK": 30.0, "2BHK": 55.0, "3BHK": 85.0, "4BHK": 120.0, "5BHK": 160.0,
}

_CORE_CONFIGS = [
    {"units_per_core": 2, "segment": "premium", "label": "2 Units/Core (Premium)",
     "preferred_pattern": "END_CORE", "corridor_sides": 1},
    {"units_per_core": 4, "segment": "mid", "label": "4 Units/Core (Mid-Market)",
     "preferred_pattern": "DOUBLE_LOADED", "corridor_sides": 2},
    {"units_per_core": 6, "segment": "budget", "label": "6 Units/Core (Budget)",
     "preferred_pattern": "DOUBLE_LOADED", "corridor_sides": 2},
]

# Core package widths by height band (from core_fit.py logic)
_CORE_PKG_W = {
    "no_lift": 1.53,       # 1 stair, no lift (h <= 10m)
    "single_stair": 3.26,  # 1 stair + lift (10m < h <= 15m)
    "dual_stair": 4.26,    # 2 stairs + lift (h > 15m)
}
_CORE_PKG_D = 3.6  # stair run
_CORRIDOR_W = 1.5  # minimum corridor width


@dataclass(frozen=True)
class CoreConfig:
    units_per_core: int
    segment: str
    label: str
    preferred_pattern: str
    corridor_sides: int  # 1 for END_CORE/SINGLE, 2 for DOUBLE


@dataclass(frozen=True)
class CoreFootprintRequirement:
    units_per_core: int
    unit_type: str
    core_pattern: str
    min_footprint_width_m: float
    min_footprint_depth_m: float
    estimated_floor_area_sqm: float
    estimated_unit_area_sqm: float


def get_core_configs() -> List[CoreConfig]:
    return [CoreConfig(**c) for c in _CORE_CONFIGS]


def get_core_config(units_per_core: int) -> CoreConfig:
    for c in _CORE_CONFIGS:
        if c["units_per_core"] == units_per_core:
            return CoreConfig(**c)
    raise ValueError(
        f"No core config for {units_per_core} units/core. "
        f"Valid: {[c['units_per_core'] for c in _CORE_CONFIGS]}"
    )


def _core_pkg_width(height_m: float) -> float:
    if height_m <= 10.0:
        return _CORE_PKG_W["no_lift"]
    elif height_m <= 15.0:
        return _CORE_PKG_W["single_stair"]
    return _CORE_PKG_W["dual_stair"]


def compute_required_footprint_for_core(
    units_per_core: int,
    unit_type: str,
    building_height_m: float,
) -> CoreFootprintRequirement:
    cc = get_core_config(units_per_core)
    unit_w = _UNIT_WIDTHS.get(unit_type, 4.0)
    unit_d = _UNIT_DEPTHS.get(unit_type, 3.5)
    unit_area = _UNIT_AREAS.get(unit_type, 55.0)
    core_w = _core_pkg_width(building_height_m)

    if cc.corridor_sides == 2:
        # DOUBLE_LOADED: units on both sides
        units_per_side = units_per_core // 2
        corridor_length = units_per_side * unit_w
        footprint_depth = corridor_length + _CORE_PKG_D
        footprint_width = 2 * unit_d + _CORRIDOR_W
        pattern = "DOUBLE_LOADED"
    else:
        # END_CORE or SINGLE_LOADED
        corridor_length = units_per_core * unit_w
        footprint_depth = corridor_length + _CORE_PKG_D
        footprint_width = unit_d + _CORRIDOR_W + core_w
        pattern = "END_CORE" if units_per_core <= 2 else "SINGLE_LOADED"

    floor_area = footprint_width * footprint_depth

    return CoreFootprintRequirement(
        units_per_core=units_per_core,
        unit_type=unit_type,
        core_pattern=pattern,
        min_footprint_width_m=round(footprint_width, 2),
        min_footprint_depth_m=round(footprint_depth, 2),
        estimated_floor_area_sqm=round(floor_area, 1),
        estimated_unit_area_sqm=round(unit_area, 1),
    )
