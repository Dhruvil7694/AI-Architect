"""
ai_layer — Phase 6 AI Layer Architecture.

Optional advisory layer around the deterministic pipeline. Three components:
- Advisor (BEFORE): user intent → structured config suggestion
- Evaluator (AFTER): BuildingLayoutContract summary → explanation + suggestions
- Constraint Interpreter (PARALLEL): raw regulatory text → structured constraints

AI never touches geometry; outputs are validated and optionally merged by orchestration.
"""

from ai_layer.config import get_ai_config
from ai_layer.schemas import (
    AdvisorOutput,
    EvaluatorOutput,
    ConstraintInterpreterOutput,
    ContractSummary,
    FloorSummary,
    EvaluationSuggestion,
    ENGINE_CONFIG_ALLOWED_KEYS,
)
from ai_layer.advisor import advise_config
from ai_layer.evaluator import evaluate_building, build_contract_summary
from ai_layer.constraint_mapper import interpret_constraints

__all__ = [
    "get_ai_config",
    "AdvisorOutput",
    "EvaluatorOutput",
    "ConstraintInterpreterOutput",
    "ContractSummary",
    "FloorSummary",
    "EvaluationSuggestion",
    "ENGINE_CONFIG_ALLOWED_KEYS",
    "advise_config",
    "evaluate_building",
    "build_contract_summary",
    "interpret_constraints",
]
