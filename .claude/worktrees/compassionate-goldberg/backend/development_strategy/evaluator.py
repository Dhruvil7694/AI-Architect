"""
development_strategy/evaluator.py
----------------------------------
Score and rank feasible strategies. Weights are configurable (defaults only).
Phase 1 is FSI-maximizing by design (triple-counting BUA); do not present as neutral.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from development_strategy.slab_metrics import SlabMetrics
from development_strategy.strategy_generator import DevelopmentStrategy, UnitType
from development_strategy.mixed_resolver import MixedDevelopmentStrategy

# Default weights (not business truths); expose via get_evaluator_weights() for tuning.
W_FSI = 0.4
W_EFFICIENCY = 0.3
W_UNIT_AREA = 0.2
W_TOTAL_UNITS = 0.1

# Phase 1 mixed-strategy defaults (w_fsi + w_efficiency + w_total_units + w_mix_diversity + w_luxury_bias = 1.0)
W_MIX_FSI = 0.35
W_MIX_EFFICIENCY = 0.25
W_MIX_TOTAL_UNITS = 0.15
W_MIX_DIVERSITY = 0.10
W_MIX_LUXURY = 0.15


@dataclass
class EvaluatorWeights:
    """Configurable scoring weights. Phase 1 mixed adds w_mix_diversity, w_luxury_bias."""

    w_fsi: float = W_FSI
    w_efficiency: float = W_EFFICIENCY
    w_unit_area: float = W_UNIT_AREA
    w_total_units: float = W_TOTAL_UNITS
    w_mix_diversity: float = W_MIX_DIVERSITY
    w_luxury_bias: float = W_MIX_LUXURY


def get_evaluator_weights() -> EvaluatorWeights:
    """Return default weights; callers can override for per-project tuning."""
    return EvaluatorWeights()


def get_mixed_evaluator_weights() -> EvaluatorWeights:
    """Phase 1 mixed-strategy weights: FSI 0.35, efficiency 0.25, units 0.15, diversity 0.10, luxury 0.15."""
    return EvaluatorWeights(
        w_fsi=W_MIX_FSI,
        w_efficiency=W_MIX_EFFICIENCY,
        w_unit_area=0.0,
        w_total_units=W_MIX_TOTAL_UNITS,
        w_mix_diversity=W_MIX_DIVERSITY,
        w_luxury_bias=W_MIX_LUXURY,
    )


@dataclass
class StrategyEvaluation:
    """One strategy with score and rank."""

    strategy: DevelopmentStrategy
    score: float
    rank: int


def _normalize(values: list[float], tol: float = 1e-9) -> list[float]:
    """Min-max normalize to [0,1]. If max - min < tol, return all 1.0 (degenerate case)."""
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v - min_v < tol:
        return [1.0] * len(values)
    return [(v - min_v) / (max_v - min_v) for v in values]


def evaluate_strategies(
    strategies: list[DevelopmentStrategy],
    slab: SlabMetrics,
    weights: Optional[EvaluatorWeights] = None,
) -> list[StrategyEvaluation]:
    """
    Score only feasible strategies. Computes per-strategy effective_efficiency
    (bua_per_floor / net_usable_area_sqm), clamped to 1.0. Returns list sorted
    by score descending with ranks 1, 2, ...
    """
    feasible = [s for s in strategies if s.feasible]
    if not feasible:
        return []

    w = weights or get_evaluator_weights()
    net_usable = slab.net_usable_area_sqm

    for s in feasible:
        bua_per_floor = s.units_per_floor * s.avg_unit_area_sqm
        if net_usable and net_usable > 0:
            raw = bua_per_floor / net_usable
            s.efficiency_ratio = min(1.0, max(0.0, raw))
        else:
            s.efficiency_ratio = 0.0

    fsi_vals = [s.fsi_utilization for s in feasible]
    eff_vals = [s.efficiency_ratio for s in feasible]
    area_vals = [s.avg_unit_area_sqm for s in feasible]
    units_vals = [float(s.total_units) for s in feasible]

    n_fsi = _normalize(fsi_vals)
    n_eff = _normalize(eff_vals)
    n_area = _normalize(area_vals)
    n_units = _normalize(units_vals)

    scored: list[tuple[DevelopmentStrategy, float]] = []
    for i, s in enumerate(feasible):
        score = (
            w.w_fsi * n_fsi[i]
            + w.w_efficiency * n_eff[i]
            + w.w_unit_area * n_area[i]
            + w.w_total_units * n_units[i]
        )
        scored.append((s, score))

    scored.sort(key=lambda x: -x[1])

    return [
        StrategyEvaluation(strategy=s, score=score, rank=r)
        for r, (s, score) in enumerate(scored, start=1)
    ]


# --- Phase 1 mixed strategy evaluation ---

@dataclass
class MixedStrategyEvaluation:
    """One mixed strategy with score and rank."""

    strategy: MixedDevelopmentStrategy
    score: float
    rank: int


def _mix_signature_from_mix(mix: dict) -> str:
    """Canonical string from mix dict (UnitType -> int) for tie-break."""
    parts = []
    for ut in UnitType:
        n = mix.get(ut, 0)
        if n > 0:
            parts.append(f"{n}x{ut.value}")
    return "+".join(parts) if parts else ""


def evaluate_mixed_strategies(
    strategies: list[MixedDevelopmentStrategy],
    slab: SlabMetrics,
    weights: Optional[EvaluatorWeights] = None,
) -> list[MixedStrategyEvaluation]:
    """
    Score and rank mixed strategies. Uses w_fsi, w_efficiency, w_total_units,
    w_mix_diversity, w_luxury_bias. Phase 1 is FSI-maximizing by design.
    """
    feasible = [s for s in strategies if s.feasible]
    if not feasible:
        return []

    w = weights or get_mixed_evaluator_weights()
    fsi_vals = [s.fsi_utilization for s in feasible]
    eff_vals = [s.efficiency_ratio for s in feasible]
    units_vals = [float(s.total_units) for s in feasible]
    div_vals = [s.mix_diversity_score for s in feasible]
    lux_vals = [s.luxury_bias_score for s in feasible]

    n_fsi = _normalize(fsi_vals)
    n_eff = _normalize(eff_vals)
    n_units = _normalize(units_vals)
    n_div = _normalize(div_vals)
    n_lux = _normalize(lux_vals)

    scored: list[tuple[MixedDevelopmentStrategy, float]] = []
    for i, s in enumerate(feasible):
        score = (
            w.w_fsi * n_fsi[i]
            + w.w_efficiency * n_eff[i]
            + w.w_total_units * n_units[i]
            + w.w_mix_diversity * n_div[i]
            + w.w_luxury_bias * n_lux[i]
        )
        scored.append((s, score))

    # Sort: score desc, then fsi_utilization, efficiency_ratio, total_units, mix_signature
    def key(x):
        s, sc = x
        sig = _mix_signature_from_mix(s.mix)
        return (-sc, -s.fsi_utilization, -s.efficiency_ratio, -s.total_units, sig)

    scored.sort(key=key)

    return [
        MixedStrategyEvaluation(strategy=s, score=score, rank=r)
        for r, (s, score) in enumerate(scored, start=1)
    ]
