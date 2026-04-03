from __future__ import annotations

"""
planning.tower_plate_estimator
------------------------------

Estimate a realistic residential tower plate size from a ProgramSpec.

This module is purely heuristic and does NOT generate or modify geometry.
It is intended to provide a soft preference for tower footprints whose
areas align with the housing program (unit mix) selected by the user.
"""

import logging
from typing import Dict, Any

from ai_planner.program_generator import ProgramSpec
from planning.unit_library import UNIT_LIBRARY

logger = logging.getLogger(__name__)


DEPTH_RULES_M = {
    "1bhk_compact": 8.0,
    "2bhk_compact": 9.0,
    "2bhk_luxury": 10.0,
    "3bhk_luxury": 11.0,
}


def estimate_tower_plate(program_spec: ProgramSpec) -> Dict[str, Any]:
    """
    Estimate tower plate characteristics from ProgramSpec.

    Returns a dict:
      {
        "avg_unit_area_sqm": float,
        "units_per_floor": int,
        "plate_area_sqm": float,
        "preferred_depth_m": float,
        "preferred_width_m": float,
      }

    All values are approximate and used only for scoring hints.
    """
    # 1) Weighted average unit area from UNIT_LIBRARY.
    avg_unit_area = 0.0
    total_ratio = 0.0
    for unit_key, ratio in program_spec.unit_mix.items():
        if not ratio:
            continue
        info = UNIT_LIBRARY.get(unit_key)
        if not info:
            continue
        r = float(ratio)
        if r <= 0.0:
            continue
        total_ratio += r
        avg_unit_area += float(info["unit_area_sqm"]) * r

    if total_ratio > 0:
        avg_unit_area /= total_ratio

    # Fallback: generic mid-size unit if mix is empty.
    if avg_unit_area <= 0:
        avg_unit_area = 80.0

    # 2) Units per floor heuristic based on average unit size.
    if avg_unit_area >= 120.0:
        units_per_floor = 3
    elif avg_unit_area >= 95.0:
        units_per_floor = 4
    elif avg_unit_area >= 70.0:
        units_per_floor = 5
    else:
        units_per_floor = 6

    # 3) Plate area.
    plate_area_sqm = avg_unit_area * units_per_floor

    # 4) Clamp to a realistic residential band.
    plate_area_sqm = max(250.0, min(plate_area_sqm, 900.0))

    # 5) Preferred depth/width shape based on dominant unit type.
    preferred_depth_m = 9.0
    if program_spec.unit_mix:
        dominant_unit = max(
            program_spec.unit_mix.items(),
            key=lambda kv: float(kv[1] or 0.0),
        )[0]
        preferred_depth_m = float(DEPTH_RULES_M.get(dominant_unit, 9.0))

    preferred_width_m = plate_area_sqm / preferred_depth_m if preferred_depth_m > 0 else plate_area_sqm ** 0.5

    logger.info(
        "Tower plate estimated: avg_unit_area=%.2f sqm, units_per_floor=%d, plate_area=%.2f sqm, depth=%.2f m, width=%.2f m",
        avg_unit_area,
        units_per_floor,
        plate_area_sqm,
        preferred_depth_m,
        preferred_width_m,
    )

    return {
        "avg_unit_area_sqm": float(avg_unit_area),
        "units_per_floor": int(units_per_floor),
        "plate_area_sqm": float(plate_area_sqm),
        "preferred_depth_m": float(preferred_depth_m),
        "preferred_width_m": float(preferred_width_m),
    }


__all__ = ["estimate_tower_plate"]

