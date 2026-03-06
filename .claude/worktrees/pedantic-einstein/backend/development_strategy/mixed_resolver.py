"""
development_strategy/mixed_resolver.py
--------------------------------------
Cross-band combination and assembly of FloorCombination. Deduplicate by
mix_signature before FSI/evaluation. FSI filtering is applied in service layer
before Pareto pruning (FSI first, then Pareto).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from development_strategy.strategy_generator import UnitType, get_unit_templates
from development_strategy.mixed_generator import BandCombination

MAX_FLOOR_COMBINATIONS = 100


@dataclass
class FloorCombination:
    """Per-floor mixed configuration, possibly across two bands."""

    band_a: BandCombination
    band_b: Optional[BandCombination]
    total_units: int
    bua_per_floor_sqm: float
    mix_signature: str
    per_type_counts: dict  # UnitType -> int


@dataclass
class MixedDevelopmentStrategy:
    """
    Phase 1 mixed strategy. Template area treated as BUA proxy in Phase 1.
    """

    mix: dict  # UnitType -> int (units per floor by type)
    floors: int
    total_units: int
    avg_unit_area_sqm: float
    total_bua_sqm: float
    fsi_utilization: float
    efficiency_ratio: float
    mix_diversity_score: float
    luxury_bias_score: float
    density_bias_score: float
    feasible: bool
    rejection_reason: Optional[str] = None


def _mix_signature_from_counts(per_type_counts: dict) -> str:
    """Canonical string: types in UnitType enum order, e.g. '2x1BHK+1x2BHK'."""
    parts = []
    for ut in UnitType:
        n = per_type_counts.get(ut, 0)
        if n > 0:
            parts.append(f"{n}x{ut.value}")
    return "+".join(parts) if parts else ""


def _add_counts(a: dict, b: dict) -> dict:
    """Sum counts per UnitType."""
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def resolve_floor_combinations(
    band_combo_lists: list[list[BandCombination]],
) -> list[FloorCombination]:
    """
    Assemble FloorCombination from per-band lists. Single-band: each combo -> one
    FloorCombination. Two-band: cross-product, deduplicate by (total_units,
    bua_per_floor_sqm, mix_signature), cap at MAX_FLOOR_COMBINATIONS.
    """
    if not band_combo_lists:
        return []

    if len(band_combo_lists) == 1:
        # Single-band
        combos = []
        for bc in band_combo_lists[0]:
            per_type = dict(bc.units)
            sig = _mix_signature_from_counts(per_type)
            combos.append(
                FloorCombination(
                    band_a=bc,
                    band_b=None,
                    total_units=bc.total_units,
                    bua_per_floor_sqm=bc.bua_per_floor_sqm,
                    mix_signature=sig,
                    per_type_counts=per_type,
                )
            )
        return combos

    # Two-band: cross-product with cap
    A, B = band_combo_lists[0], band_combo_lists[1]
    seen: set[tuple[int, float, str]] = set()
    floor_combos = []
    count = 0
    for comb_a in A:
        for comb_b in B:
            if count >= MAX_FLOOR_COMBINATIONS:
                break
            total_units = comb_a.total_units + comb_b.total_units
            bua = comb_a.bua_per_floor_sqm + comb_b.bua_per_floor_sqm
            per_type = _add_counts(comb_a.units, comb_b.units)
            sig = _mix_signature_from_counts(per_type)
            key = (total_units, round(bua, 6), sig)
            if key in seen:
                continue
            seen.add(key)
            floor_combos.append(
                FloorCombination(
                    band_a=comb_a,
                    band_b=comb_b,
                    total_units=total_units,
                    bua_per_floor_sqm=bua,
                    mix_signature=sig,
                    per_type_counts=per_type,
                )
            )
            count += 1
        if count >= MAX_FLOOR_COMBINATIONS:
            break
    return floor_combos
