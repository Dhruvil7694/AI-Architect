from __future__ import annotations

"""
ai_planner.scenario_generator
-----------------------------

Generate a small set of high-level planning scenarios from a ProgramSpec.

These scenarios are PARAMETER-ONLY descriptors (tower counts, FSI targets,
labels). They never contain or influence raw geometry directly; geometry is
always produced by the deterministic development pipeline.
"""

from typing import Any, Dict, List

from ai_planner.program_generator import ProgramSpec
from planning.unit_library import UNIT_LIBRARY
from planning.tower_plate_estimator import estimate_tower_plate


def _estimate_fsi(program: ProgramSpec, site_area_sqm: float) -> float:
    """
    Very coarse FSI estimate based on unit mix and target units.

    This is used only for picking relative low/balanced/high density targets.
    The regulatory engines still own the true achievable FSI.
    """
    if site_area_sqm <= 0:
        return 1.5

    avg_unit_area = 0.0
    for key, fraction in program.unit_mix.items():
        info = UNIT_LIBRARY.get(key)
        if not info:
            continue
        avg_unit_area += float(info["unit_area_sqm"]) * float(fraction or 0.0)

    if avg_unit_area <= 0:
        avg_unit_area = 80.0

    total_unit_area = avg_unit_area * max(program.target_units, 1)
    fsi = total_unit_area / site_area_sqm
    # Clamp to a reasonable urban band.
    return max(0.8, min(fsi, 4.0))


def generate_scenarios(program_spec: ProgramSpec, *, site_area_sqm: float) -> List[Dict[str, Any]]:
    """
    Generate three labelled scenarios (balanced, high-density, landmark).

    Each scenario is a dict with:
      - label: human-readable name
      - tower_count: suggested number of towers (used as a hint only)
      - fsi_target: coarse target FSI for that scenario
      - meta: copy of key program fields for the frontend
    """
    base_fsi = _estimate_fsi(program_spec, site_area_sqm)

    # Adjust base FSI range based on priorities.
    if program_spec.density_priority == "high":
        base_fsi *= 1.1
    elif program_spec.density_priority == "low":
        base_fsi *= 0.85

    # Derive a default tower count band.
    towers = program_spec.preferred_towers or 2
    towers = max(1, min(towers, 5))

    # Tower plate estimate for scoring / visualisation hints.
    plate_estimate = estimate_tower_plate(program_spec)
    target_plate_area_sqm = plate_estimate["plate_area_sqm"]

    scenarios: List[Dict[str, Any]] = []

    # Scenario A — balanced courtyard
    scenarios.append(
        {
            "id": "balanced",
            "label": "Balanced Courtyard",
            "tower_count": max(1, towers),
            "fsi_target": round(base_fsi, 2),
            "target_plate_area_sqm": target_plate_area_sqm,
            "meta": {
                "open_space_bias": "balanced",
                "open_space_priority": program_spec.open_space_priority,
                "density_priority": program_spec.density_priority,
            },
        }
    )

    # Scenario B — high density
    scenarios.append(
        {
            "id": "high_density",
            "label": "High Density",
            "tower_count": max(2, towers + 1),
            "fsi_target": round(base_fsi * 1.2, 2),
            "target_plate_area_sqm": target_plate_area_sqm,
            "meta": {
                "open_space_bias": "reduced_open_space",
                "open_space_priority": program_spec.open_space_priority,
                "density_priority": "high",
            },
        }
    )

    # Scenario C — landmark tower with more open space
    scenarios.append(
        {
            "id": "landmark",
            "label": "Landmark Tower",
            "tower_count": 1,
            "fsi_target": round(base_fsi * 0.8, 2),
            "target_plate_area_sqm": target_plate_area_sqm,
            "meta": {
                "open_space_bias": "large_central_open_space",
                "open_space_priority": "high",
                "density_priority": program_spec.density_priority,
            },
        }
    )

    return scenarios


__all__ = ["generate_scenarios"]

