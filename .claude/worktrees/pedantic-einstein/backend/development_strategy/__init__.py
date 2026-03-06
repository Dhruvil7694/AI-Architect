"""
development_strategy
--------------------
Deterministic Development Strategy Engine: slab metrics, unit-mix strategy
generation, scoring, and recommendation. Sits between FloorSkeleton and the
future Level 2 Layout Engine. No layout slicing, DXF, or AI.
"""

from development_strategy.slab_metrics import SlabMetrics, compute_slab_metrics
from development_strategy.strategy_generator import (
    DevelopmentStrategy,
    UnitType,
    generate_strategies,
)
from development_strategy.evaluator import (
    StrategyEvaluation,
    evaluate_strategies,
    MixedStrategyEvaluation,
    evaluate_mixed_strategies,
    EvaluatorWeights,
)
from development_strategy.service import (
    resolve_development_strategy,
    resolve_mixed_development_strategy,
)
from development_strategy.mixed_generator import BandCombination, generate_band_combinations
from development_strategy.mixed_resolver import (
    FloorCombination,
    MixedDevelopmentStrategy,
    resolve_floor_combinations,
)

__all__ = [
    "SlabMetrics",
    "compute_slab_metrics",
    "UnitType",
    "DevelopmentStrategy",
    "generate_strategies",
    "StrategyEvaluation",
    "evaluate_strategies",
    "resolve_development_strategy",
    "MixedStrategyEvaluation",
    "evaluate_mixed_strategies",
    "EvaluatorWeights",
    "resolve_mixed_development_strategy",
    "BandCombination",
    "generate_band_combinations",
    "FloorCombination",
    "MixedDevelopmentStrategy",
    "resolve_floor_combinations",
]
