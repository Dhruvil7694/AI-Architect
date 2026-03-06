"""
development_strategy/strategy_generator.py
--------------------------------------------
Generate feasible single-type development strategies from slab metrics.
Band-aware, orientation-aware; no area-only feasibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from placement_engine.geometry.core_fit import CoreDimensions
from floor_skeleton.models import AXIS_WIDTH_DOMINANT

from development_strategy.slab_metrics import SlabMetrics


class UnitType(Enum):
    """Single unit type per strategy (Phase 0: no mixed strategies)."""

    STUDIO = "STUDIO"
    BHK1 = "1BHK"
    BHK2 = "2BHK"
    BHK3 = "3BHK"


# Unit template: strategy-level minimum super BUA (assumed for strategy modeling;
# real BUA includes walls, common area distribution, core share, balcony loading).
# unit_min_area_sqm must be >= unit_frontage_m * unit_depth_m (geometry–area consistency).
_CORE = CoreDimensions()

_UNIT_TEMPLATES = {
    UnitType.STUDIO: {
        "unit_min_area_sqm": 35.0,
        "unit_frontage_m": max(3.0, _CORE.min_unit_width_m),
        "unit_depth_m": max(4.5, _CORE.min_unit_depth_m),
    },
    UnitType.BHK1: {
        "unit_min_area_sqm": 50.0,
        "unit_frontage_m": max(3.0, _CORE.min_unit_width_m),
        "unit_depth_m": max(4.5, _CORE.min_unit_depth_m),
    },
    UnitType.BHK2: {
        "unit_min_area_sqm": 75.0,
        "unit_frontage_m": 4.0,
        "unit_depth_m": 6.0,
    },
    UnitType.BHK3: {
        "unit_min_area_sqm": 110.0,
        "unit_frontage_m": 4.5,
        "unit_depth_m": 7.5,
    },
}

# Validate at import: unit_min_area_sqm >= unit_frontage_m * unit_depth_m
for _ut, _t in _UNIT_TEMPLATES.items():
    _carpet = _t["unit_frontage_m"] * _t["unit_depth_m"]
    assert _t["unit_min_area_sqm"] >= _carpet - 0.01, (
        f"{_ut}: unit_min_area_sqm {_t['unit_min_area_sqm']} < frontage*depth {_carpet}"
    )


def get_unit_templates():
    """Return unit templates for Phase 1 mixed strategy (read-only). Template area treated as BUA proxy in Phase 1."""
    return _UNIT_TEMPLATES


@dataclass
class DevelopmentStrategy:
    """One single-type strategy (e.g. 2BHK only)."""

    unit_type: UnitType
    units_per_floor: int
    floors: int
    total_units: int
    avg_unit_area_sqm: float
    total_bua_sqm: float
    fsi_utilization: float
    efficiency_ratio: float
    feasible: bool
    rejection_reason: Optional[str] = None


def _repeat_and_depth_for_band(
    slab: SlabMetrics, i: int
) -> tuple[float, float]:
    """
    Return (repeat_len_m, depth_avail_m) for band i using orientation rule.
    If orientation_axes[i] == AXIS_WIDTH_DOMINANT: repeat along width, depth = lengths.
    Else: repeat along length, depth = widths.
    """
    w = slab.band_widths_m[i] if i < len(slab.band_widths_m) else 0.0
    d = slab.band_lengths_m[i] if i < len(slab.band_lengths_m) else 0.0
    axis = slab.band_orientation_axes[i] if i < len(slab.band_orientation_axes) else AXIS_WIDTH_DOMINANT
    if axis == AXIS_WIDTH_DOMINANT:
        return (w, d)
    return (d, w)


def generate_strategies(
    slab: SlabMetrics,
    plot_area_sqm: float,
    max_fsi: float,
    floors: int,
) -> list[DevelopmentStrategy]:
    """
    Generate one strategy per UnitType. Feasibility is band-aware and
    orientation-aware. Remainder space along the repeat axis after tiling
    is ignored in Phase 0 (no partial or mixed units).
    """
    strategies: list[DevelopmentStrategy] = []
    floors = max(1, int(floors))

    if plot_area_sqm <= 0 or max_fsi <= 0:
        max_total_bua_sqm = 0.0
        for ut in UnitType:
            t = _UNIT_TEMPLATES[ut]
            strategies.append(
                DevelopmentStrategy(
                    unit_type=ut,
                    units_per_floor=0,
                    floors=floors,
                    total_units=0,
                    avg_unit_area_sqm=t["unit_min_area_sqm"],
                    total_bua_sqm=0.0,
                    fsi_utilization=0.0,
                    efficiency_ratio=0.0,
                    feasible=False,
                    rejection_reason="plot_area_or_max_fsi_zero",
                )
            )
        return strategies

    max_total_bua_sqm = plot_area_sqm * max_fsi
    n_bands = len(slab.band_widths_m)

    for unit_type in UnitType:
        t = _UNIT_TEMPLATES[unit_type]
        unit_min_area_sqm = t["unit_min_area_sqm"]
        unit_frontage_m = t["unit_frontage_m"]
        unit_depth_m = t["unit_depth_m"]

        if unit_frontage_m <= 0:
            strategies.append(
                DevelopmentStrategy(
                    unit_type=unit_type,
                    units_per_floor=0,
                    floors=floors,
                    total_units=0,
                    avg_unit_area_sqm=unit_min_area_sqm,
                    total_bua_sqm=0.0,
                    fsi_utilization=0.0,
                    efficiency_ratio=0.0,
                    feasible=False,
                    rejection_reason="invalid_template_frontage",
                )
            )
            continue

        units_in_bands = 0
        for i in range(n_bands):
            repeat_len_i, depth_avail_i = _repeat_and_depth_for_band(slab, i)
            if depth_avail_i < unit_depth_m:
                continue
            # Units tiled along repeat axis; remainder ignored (Phase 0).
            units_in_bands += int(repeat_len_i // unit_frontage_m)

        units_per_floor = units_in_bands

        if units_per_floor == 0:
            strategies.append(
                DevelopmentStrategy(
                    unit_type=unit_type,
                    units_per_floor=0,
                    floors=floors,
                    total_units=0,
                    avg_unit_area_sqm=unit_min_area_sqm,
                    total_bua_sqm=0.0,
                    fsi_utilization=0.0,
                    efficiency_ratio=0.0,
                    feasible=False,
                    rejection_reason="no_band_can_host_unit_type",
                )
            )
            continue

        total_units = units_per_floor * floors
        total_bua_sqm = units_per_floor * unit_min_area_sqm * floors

        if total_bua_sqm > max_total_bua_sqm:
            strategies.append(
                DevelopmentStrategy(
                    unit_type=unit_type,
                    units_per_floor=units_per_floor,
                    floors=floors,
                    total_units=total_units,
                    avg_unit_area_sqm=unit_min_area_sqm,
                    total_bua_sqm=total_bua_sqm,
                    fsi_utilization=min(1.0, total_bua_sqm / max_total_bua_sqm),
                    efficiency_ratio=0.0,
                    feasible=False,
                    rejection_reason="fsi_exceeds_max",
                )
            )
            continue

        fsi_utilization = total_bua_sqm / max_total_bua_sqm
        strategies.append(
            DevelopmentStrategy(
                unit_type=unit_type,
                units_per_floor=units_per_floor,
                floors=floors,
                total_units=total_units,
                avg_unit_area_sqm=unit_min_area_sqm,
                total_bua_sqm=total_bua_sqm,
                fsi_utilization=fsi_utilization,
                efficiency_ratio=0.0,  # filled by evaluator
                feasible=True,
                rejection_reason=None,
            )
        )

    return strategies
