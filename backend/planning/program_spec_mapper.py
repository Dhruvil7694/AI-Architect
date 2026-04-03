from __future__ import annotations

"""
planning.program_spec_mapper
----------------------------

Deterministic mapping from PlannerInputs (frontend) to ProgramSpec.

This layer ensures that changes to:
  - unitMix
  - segment
  - towerCount
  - preferredFloors
  - vastu

always produce a predictable ProgramSpec before any AI refinement.
"""

from typing import Any, Dict

from ai_planner.program_generator import ProgramSpec


def _base_program_spec() -> ProgramSpec:
    # Neutral defaults; will be overwritten by mappings below.
    return ProgramSpec(
        unit_mix={
            "1bhk_compact": 0.25,
            "2bhk_compact": 0.35,
            "2bhk_luxury": 0.25,
            "3bhk_luxury": 0.15,
        },
        target_units=0,
        preferred_towers=0,
        max_floors=0,
        open_space_priority="medium",
        density_priority="medium",
    )


def _apply_unit_mix_from_inputs(program: ProgramSpec, inputs: Dict[str, Any]) -> None:
    """
    Map frontend unit-mix checkboxes to ProgramSpec.unit_mix fractions.

    Supported keys (must match planning.unit_library.UNIT_LIBRARY):
        1bhk_compact, 2bhk_compact, 2bhk_luxury, 3bhk_luxury

    Strategy: split weight equally across selected BHK tiers; within each tier
    the segment field (applied later) drives the compact/luxury split.
    Handles all combinations — single, double, triple, or all four BHK types
    selected simultaneously.
    """
    raw = [str(u).upper() for u in inputs.get("unitMix", [])]
    has = {k: k in raw for k in ("1BHK", "2BHK", "3BHK", "4BHK", "5BHK")}

    # Map each selected BHK to the two library variants (compact + luxury).
    # 4BHK/5BHK not in the library yet — fold into 3bhk_luxury.
    selected: list[str] = []
    if has["1BHK"]:
        selected.append("1bhk_compact")
    if has["2BHK"]:
        selected += ["2bhk_compact", "2bhk_luxury"]
    if has["3BHK"] or has["4BHK"] or has["5BHK"]:
        selected.append("3bhk_luxury")

    if not selected:
        # Nothing checked — keep the default balanced mix.
        return

    # Distribute weight equally; duplicates are merged by summing.
    per_unit = 1.0 / len(selected)
    mix: Dict[str, float] = {}
    for k in selected:
        mix[k] = round(mix.get(k, 0.0) + per_unit, 4)

    # Normalise so fractions sum to exactly 1.0.
    total = sum(mix.values())
    if total > 0:
        mix = {k: round(v / total, 4) for k, v in mix.items()}

    program.unit_mix = mix


def _apply_segment_from_inputs(program: ProgramSpec, inputs: Dict[str, Any]) -> None:
    segment = str(inputs.get("segment") or "").lower()

    if segment == "budget":
        program.density_priority = "high"
        program.open_space_priority = "low"
    elif segment == "mid":
        program.density_priority = "medium"
        program.open_space_priority = "medium"
    elif segment == "premium":
        program.density_priority = "medium"
        program.open_space_priority = "high"
    elif segment == "luxury":
        program.density_priority = "low"
        program.open_space_priority = "high"


def _apply_tower_count_from_inputs(program: ProgramSpec, inputs: Dict[str, Any]) -> None:
    tower_count = inputs.get("towerCount", "auto")
    if isinstance(tower_count, (int, float)):
        try:
            program.preferred_towers = max(1, int(tower_count))
        except (TypeError, ValueError):
            pass
    elif isinstance(tower_count, str) and tower_count != "auto":
        try:
            program.preferred_towers = max(1, int(tower_count))
        except (TypeError, ValueError):
            pass


def _apply_preferred_floors_from_inputs(program: ProgramSpec, inputs: Dict[str, Any]) -> None:
    preferred_floors = inputs.get("preferredFloors") or {}
    max_floors = preferred_floors.get("max")
    try:
        if max_floors is not None:
            program.max_floors = max(0, int(max_floors))
    except (TypeError, ValueError):
        pass


def build_program_spec_from_inputs(inputs: Dict[str, Any]) -> ProgramSpec:
    """
    Deterministically map PlannerInputs into a ProgramSpec.

    This function never calls AI and can be used as a hard baseline that an
    LLM may optionally refine later.
    """
    program = _base_program_spec()

    _apply_unit_mix_from_inputs(program, inputs)
    _apply_segment_from_inputs(program, inputs)
    _apply_tower_count_from_inputs(program, inputs)
    _apply_preferred_floors_from_inputs(program, inputs)

    # TODO: optional future use of `vastu` to influence downstream choices.
    return program


__all__ = ["build_program_spec_from_inputs"]

