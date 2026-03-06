"""
development_strategy/mixed_generator.py
---------------------------------------
Per-band discrete packing of multiple unit types for Phase 1 mixed strategies.
Template area treated as BUA proxy in Phase 1. Combination depth = max depth
of units in mix; enforced by only combining allowed types.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from floor_skeleton.models import AXIS_WIDTH_DOMINANT

from development_strategy.slab_metrics import SlabMetrics
from development_strategy.strategy_generator import UnitType, get_unit_templates

# Caps (configurable constants). On large slabs MAX_UNITS_PER_BAND suppresses
# extreme studio density; document as strategic constraint.
MAX_UNITS_PER_BAND = 6
MAX_UNIT_TYPES_PER_BAND = 3
MAX_COMBINATIONS_PER_BAND = 20


@dataclass
class BandCombination:
    """
    Single-band mixed packing result. BUA from template areas (BUA proxy in Phase 1).
    """

    units: dict  # UnitType -> int, only positive counts, max 3 distinct keys
    total_units: int
    used_length_m: float
    remainder_m: float
    bua_per_floor_sqm: float
    band_index: int
    orientation_axis: str
    allowed_unit_types: list  # list[UnitType], cached for traceability


def _repeat_and_depth_for_band(slab: SlabMetrics, i: int) -> tuple[float, float]:
    """Return (repeat_len_m, depth_avail_m) for band i. Same convention as strategy_generator."""
    w = slab.band_widths_m[i] if i < len(slab.band_widths_m) else 0.0
    d = slab.band_lengths_m[i] if i < len(slab.band_lengths_m) else 0.0
    axis = (
        slab.band_orientation_axes[i]
        if i < len(slab.band_orientation_axes)
        else AXIS_WIDTH_DOMINANT
    )
    if axis == AXIS_WIDTH_DOMINANT:
        return (w, d)
    return (d, w)


def _allowed_types_and_max_counts(
    slab: SlabMetrics, band_index: int
) -> tuple[list[UnitType], dict[UnitType, int]]:
    """
    Return (allowed_unit_types, max_count_per_type) for this band.
    Depth: unit_depth_m <= depth_avail_m. Frontage: max_n = floor(repeat_len / frontage), cap by MAX_UNITS_PER_BAND.
    """
    repeat_len_m, depth_avail_m = _repeat_and_depth_for_band(slab, band_index)
    templates = get_unit_templates()
    allowed = []
    max_counts = {}
    for ut in UnitType:
        t = templates[ut]
        unit_depth_m = t["unit_depth_m"]
        unit_frontage_m = t["unit_frontage_m"]
        if depth_avail_m < unit_depth_m or unit_frontage_m <= 0:
            continue
        max_by_frontage = int(repeat_len_m // unit_frontage_m)
        if max_by_frontage <= 0:
            continue
        max_n = min(MAX_UNITS_PER_BAND, max_by_frontage)
        allowed.append(ut)
        max_counts[ut] = max_n
    return (allowed, max_counts)


def _is_dominated(a: BandCombination, b: BandCombination) -> bool:
    """True if b dominates a (b has >= bua and >= units, at least one strict)."""
    if b.bua_per_floor_sqm >= a.bua_per_floor_sqm and b.total_units >= a.total_units:
        if b.bua_per_floor_sqm > a.bua_per_floor_sqm or b.total_units > a.total_units:
            return True
    return False


def _sort_key_bc(bc: BandCombination) -> tuple:
    """Deterministic sort: bua desc, total_units desc, remainder asc, then lexicographic units."""
    units_list = sorted((k.name, v) for k, v in bc.units.items())
    return (
        -bc.bua_per_floor_sqm,
        -bc.total_units,
        bc.remainder_m,
        tuple(units_list),
    )


def generate_band_combinations(
    slab: SlabMetrics, band_index: int
) -> list[BandCombination]:
    """
    Generate valid BandCombination list for one band. Pareto-pruned, sorted, capped.
    Only combinations whose types are all in allowed_unit_types (depth enforced per type).
    """
    allowed, max_counts = _allowed_types_and_max_counts(slab, band_index)
    repeat_len_m, depth_avail_m = _repeat_and_depth_for_band(slab, band_index)
    axis = (
        slab.band_orientation_axes[band_index]
        if band_index < len(slab.band_orientation_axes)
        else AXIS_WIDTH_DOMINANT
    )
    templates = get_unit_templates()

    if not allowed:
        return [
            BandCombination(
                units={},
                total_units=0,
                used_length_m=0.0,
                remainder_m=repeat_len_m,
                bua_per_floor_sqm=0.0,
                band_index=band_index,
                orientation_axis=axis,
                allowed_unit_types=[],
            )
        ]

    combos: list[BandCombination] = []

    # 1) One-type
    for t in allowed:
        frontage = templates[t]["unit_frontage_m"]
        area = templates[t]["unit_min_area_sqm"]
        max_n = max_counts[t]
        for n in range(1, max_n + 1):
            used_len = n * frontage
            if used_len > repeat_len_m + 1e-6:
                break
            remainder = repeat_len_m - used_len
            bua = n * area
            combos.append(
                BandCombination(
                    units={t: n},
                    total_units=n,
                    used_length_m=used_len,
                    remainder_m=max(0.0, remainder),
                    bua_per_floor_sqm=bua,
                    band_index=band_index,
                    orientation_axis=axis,
                    allowed_unit_types=allowed,
                )
            )
            if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                break
        if len(combos) >= MAX_COMBINATIONS_PER_BAND:
            break

    # 2) Two-type (t1 < t2 in enum order)
    unit_list = list(UnitType)
    for i1, t1 in enumerate(unit_list):
        if t1 not in allowed:
            continue
        for t2 in unit_list[i1 + 1 :]:
            if t2 not in allowed:
                continue
            if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                break
            f1 = templates[t1]["unit_frontage_m"]
            f2 = templates[t2]["unit_frontage_m"]
            a1 = templates[t1]["unit_min_area_sqm"]
            a2 = templates[t2]["unit_min_area_sqm"]
            max_n1 = max_counts[t1]
            max_n2 = max_counts[t2]
            for n1 in range(0, max_n1 + 1):
                if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                    break
                L1 = repeat_len_m - n1 * f1
                if L1 < f2 - 1e-9:
                    break
                n2_max = min(MAX_UNITS_PER_BAND - n1, int(L1 // f2))
                for n2 in range(1, n2_max + 1):
                    if n1 == 0 and n2 == 0:
                        continue
                    used_len = n1 * f1 + n2 * f2
                    if used_len > repeat_len_m + 1e-6:
                        continue
                    remainder = repeat_len_m - used_len
                    bua = n1 * a1 + n2 * a2
                    units_dict = {}
                    if n1:
                        units_dict[t1] = n1
                    if n2:
                        units_dict[t2] = n2
                    combos.append(
                        BandCombination(
                            units=units_dict,
                            total_units=n1 + n2,
                            used_length_m=used_len,
                            remainder_m=max(0.0, remainder),
                            bua_per_floor_sqm=bua,
                            band_index=band_index,
                            orientation_axis=axis,
                            allowed_unit_types=allowed,
                        )
                    )
                    if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                        break
        if len(combos) >= MAX_COMBINATIONS_PER_BAND:
            break

    # 3) Three-type (t1 < t2 < t3)
    for i1, t1 in enumerate(unit_list):
        if t1 not in allowed:
            continue
        for i2, t2 in enumerate(unit_list[i1 + 1 :], start=i1 + 1):
            if t2 not in allowed:
                continue
            for t3 in unit_list[i2 + 1 :]:
                if t3 not in allowed:
                    continue
                if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                    break
                f1, f2, f3 = (
                    templates[t1]["unit_frontage_m"],
                    templates[t2]["unit_frontage_m"],
                    templates[t3]["unit_frontage_m"],
                )
                a1, a2, a3 = (
                    templates[t1]["unit_min_area_sqm"],
                    templates[t2]["unit_min_area_sqm"],
                    templates[t3]["unit_min_area_sqm"],
                )
                max_n1 = max_counts[t1]
                max_n2 = max_counts[t2]
                max_n3 = max_counts[t3]
                for n1 in range(0, max_n1 + 1):
                    if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                        break
                    L1 = repeat_len_m - n1 * f1
                    if L1 < min(f2, f3) - 1e-9:
                        break
                    for n2 in range(0, max_n2 + 1):
                        if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                            break
                        L2 = L1 - n2 * f2
                        if L2 < f3 - 1e-9:
                            break
                        n3_max = min(
                            MAX_UNITS_PER_BAND - (n1 + n2), int(L2 // f3)
                        )
                        for n3 in range(1, n3_max + 1):
                            if n1 + n2 + n3 > MAX_UNITS_PER_BAND:
                                continue
                            used_len = n1 * f1 + n2 * f2 + n3 * f3
                            if used_len > repeat_len_m + 1e-6:
                                continue
                            remainder = repeat_len_m - used_len
                            bua = n1 * a1 + n2 * a2 + n3 * a3
                            units_dict = {}
                            if n1:
                                units_dict[t1] = n1
                            if n2:
                                units_dict[t2] = n2
                            if n3:
                                units_dict[t3] = n3
                            combos.append(
                                BandCombination(
                                    units=units_dict,
                                    total_units=n1 + n2 + n3,
                                    used_length_m=used_len,
                                    remainder_m=max(0.0, remainder),
                                    bua_per_floor_sqm=bua,
                                    band_index=band_index,
                                    orientation_axis=axis,
                                    allowed_unit_types=allowed,
                                )
                            )
                            if len(combos) >= MAX_COMBINATIONS_PER_BAND:
                                break
        if len(combos) >= MAX_COMBINATIONS_PER_BAND:
            break

    # Pareto pruning: keep non-dominated
    non_dominated = []
    for c in combos:
        dominated = False
        for other in combos:
            if other is c:
                continue
            if _is_dominated(c, other):
                dominated = True
                break
        if not dominated:
            non_dominated.append(c)

    # Sort: bua desc, total_units desc, remainder asc, lexicographic units
    non_dominated.sort(key=_sort_key_bc)

    # Cap
    if len(non_dominated) > MAX_COMBINATIONS_PER_BAND:
        non_dominated = non_dominated[: MAX_COMBINATIONS_PER_BAND]

    return non_dominated
