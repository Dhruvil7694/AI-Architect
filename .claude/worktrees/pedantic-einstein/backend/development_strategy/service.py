"""
development_strategy/service.py
---------------------------------
Orchestrate slab metrics, strategy generation, and evaluation. Returns
the best-ranked strategy or None when none feasible.
"""

from __future__ import annotations

import math
from typing import Optional

from architecture.feasibility.aggregate import FeasibilityAggregate
from floor_skeleton.models import FloorSkeleton

from development_strategy.slab_metrics import SlabMetrics, compute_slab_metrics
from development_strategy.strategy_generator import (
    generate_strategies,
    get_unit_templates,
    UnitType,
)
from development_strategy.evaluator import (
    StrategyEvaluation,
    evaluate_strategies,
    MixedStrategyEvaluation,
    evaluate_mixed_strategies,
    get_mixed_evaluator_weights,
)
from development_strategy.mixed_generator import generate_band_combinations
from development_strategy.mixed_resolver import (
    FloorCombination,
    MixedDevelopmentStrategy,
    resolve_floor_combinations,
)

# Max template area (3BHK) for luxury normalization
_MAX_TEMPLATE_AREA_SQM = 110.0


def _floor_combinations_to_strategies(
    floor_combos: list[FloorCombination],
    slab: SlabMetrics,
    floors: int,
    max_total_bua_sqm: float,
) -> list[MixedDevelopmentStrategy]:
    """FSI filter and map to MixedDevelopmentStrategy. FSI applied first (before Pareto)."""
    strategies = []
    templates = get_unit_templates()
    net_usable = slab.net_usable_area_sqm or 0.0

    for fc in floor_combos:
        total_bua_sqm = fc.bua_per_floor_sqm * floors
        if total_bua_sqm > max_total_bua_sqm:
            continue
        fsi_utilization = total_bua_sqm / max_total_bua_sqm if max_total_bua_sqm > 0 else 0.0
        total_units_building = fc.total_units * floors
        avg_unit_area = (
            total_bua_sqm / total_units_building if total_units_building > 0 else 0.0
        )
        efficiency_ratio = (
            min(1.0, max(0.0, fc.bua_per_floor_sqm / net_usable))
            if net_usable > 0
            else 0.0
        )
        k = sum(1 for c in fc.per_type_counts.values() if c > 0)
        k_max = min(3, len(UnitType))
        mix_diversity_score = (
            (k - 1) / (k_max - 1) if k_max > 1 else 0.0
        )
        luxury_bias_score = (
            min(1.0, avg_unit_area / _MAX_TEMPLATE_AREA_SQM)
            if _MAX_TEMPLATE_AREA_SQM > 0
            else 0.0
        )
        density_bias_score = float(fc.total_units)

        strategies.append(
            MixedDevelopmentStrategy(
                mix=dict(fc.per_type_counts),
                floors=floors,
                total_units=total_units_building,
                avg_unit_area_sqm=avg_unit_area,
                total_bua_sqm=total_bua_sqm,
                fsi_utilization=fsi_utilization,
                efficiency_ratio=efficiency_ratio,
                mix_diversity_score=mix_diversity_score,
                luxury_bias_score=luxury_bias_score,
                density_bias_score=density_bias_score,
                feasible=True,
                rejection_reason=None,
            )
        )
    return strategies


def resolve_mixed_development_strategy(
    skeleton: FloorSkeleton,
    feasibility: FeasibilityAggregate,
    height_limit_m: float,
    max_fsi: float,
    storey_height_m: float,
    top_k: Optional[int] = None,
) -> tuple[Optional[MixedStrategyEvaluation], list[MixedStrategyEvaluation]]:
    """
    Compute mixed unit strategies and return best plus optionally top_k ranked.
    FSI filter applied before any floor-level Pareto pruning.
    """
    slab = compute_slab_metrics(skeleton)
    plot_area_sqm = feasibility.plot_metrics.plot_area_sqm
    max_total_bua_sqm = plot_area_sqm * max_fsi if max_fsi > 0 else 0.0

    if feasibility.num_floors_estimated is not None:
        floors = max(1, feasibility.num_floors_estimated)
    else:
        if storey_height_m and storey_height_m > 0:
            floors = max(1, int(math.floor(height_limit_m / storey_height_m)))
        else:
            floors = 1

    n_bands = len(slab.band_widths_m)
    if n_bands == 0:
        return (None, [])

    band_combo_lists = [
        generate_band_combinations(slab, i) for i in range(n_bands)
    ]
    floor_combos = resolve_floor_combinations(band_combo_lists)

    feasible_strategies = _floor_combinations_to_strategies(
        floor_combos, slab, floors, max_total_bua_sqm
    )

    if not feasible_strategies:
        return (None, [])

    evaluations = evaluate_mixed_strategies(
        feasible_strategies, slab, get_mixed_evaluator_weights()
    )
    if not evaluations:
        return (None, [])

    best = evaluations[0]
    top_list = (
        evaluations[: top_k] if top_k is not None else evaluations
    )
    return (best, top_list)


def resolve_development_strategy(
    skeleton: FloorSkeleton,
    feasibility: FeasibilityAggregate,
    height_limit_m: float,
    max_fsi: float,
    storey_height_m: float,
) -> Optional[StrategyEvaluation]:
    """
    Compute slab metrics, generate strategies, evaluate, and return the
    best-ranked feasible strategy. Returns None when no strategy is feasible.

    Floors: prefer feasibility.num_floors_estimated when set; otherwise
    use theoretical max(1, floor(height_limit_m / storey_height_m)) (documented
    as non-regulatory capacity only).
    """
    slab = compute_slab_metrics(skeleton)
    plot_area_sqm = feasibility.plot_metrics.plot_area_sqm

    if feasibility.num_floors_estimated is not None:
        floors = max(1, feasibility.num_floors_estimated)
    else:
        if storey_height_m and storey_height_m > 0:
            floors = max(1, int(math.floor(height_limit_m / storey_height_m)))
        else:
            floors = 1

    strategies = generate_strategies(slab, plot_area_sqm, max_fsi, floors)
    evaluations = evaluate_strategies(strategies, slab)

    if not evaluations:
        return None
    return evaluations[0]
