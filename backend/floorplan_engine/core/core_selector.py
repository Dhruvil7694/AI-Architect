"""
floorplan_engine/core/core_selector.py
--------------------------------------
Select the core layout strategy based on footprint area.

Four types (R1-7):
    POINT_CORE       — compact towers (< 500 sqm)
    SINGLE_CORRIDOR  — small blocks  (500–900 sqm)
    DOUBLE_CORRIDOR  — mid-size      (900–1600 sqm)
    DOUBLE_CORE      — long slabs    (≥ 1600 sqm)
"""

from __future__ import annotations

from floorplan_engine.config import (
    DOUBLE_CORE,
    DOUBLE_CORRIDOR,
    POINT_CORE,
    SINGLE_CORRIDOR,
    CoreConfig,
)


def select_core_type(footprint_area_sqm: float, config: CoreConfig) -> str:
    """
    Deterministic core-type selection from footprint area.

    Returns one of the four core-type constants.
    """
    if footprint_area_sqm < config.point_core_max_area:
        return POINT_CORE
    if footprint_area_sqm < config.single_corridor_max_area:
        return SINGLE_CORRIDOR
    if footprint_area_sqm < config.double_corridor_max_area:
        return DOUBLE_CORRIDOR
    return DOUBLE_CORE
