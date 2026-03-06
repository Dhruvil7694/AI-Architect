"""
ai_layer/schemas.py — Dataclasses and allowlists for AI inputs/outputs.

All outputs are validated against these schemas. Unknown keys are stripped.
Strict type validation: invalid types are rejected (field discarded or None).
No silent coercion (e.g. "six" or "6" for a number → reject).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── Engine config allowlist (No New Config Keys Rule) ────────────────────────
# Only these keys may appear in Advisor output or Evaluator optional_config_delta.
ENGINE_CONFIG_ALLOWED_KEYS = frozenset({
    "template_priority_order",
    "preferred_module_width",
    "storey_height_override",
    "density_bias",
    "constraint_flags",
    "prefer_compact",
    "max_units_per_floor",
})

# Template names that exist in the engine registry. Invalid names are discarded silently.
ALLOWED_TEMPLATE_NAMES = frozenset({"STANDARD_1BHK", "COMPACT_1BHK", "STUDIO"})

# Maximum number of suggestions to retain from Evaluator. Extras are discarded.
MAX_EVALUATOR_SUGGESTIONS = 5

DENSITY_BIAS_VALUES = frozenset({"luxury", "density", "balanced"})

# Closed enum for Evaluator suggestion_type (plan Section 3).
SUGGESTION_TYPE_ENUM = frozenset({
    "increase_module_width",
    "decrease_module_width",
    "try_compact_first",
    "try_standard_first",
    "reduce_floors",
    "increase_floors",
    "adjust_density_bias",
    "no_change",
})


# ── BEFORE layer (Advisor) ────────────────────────────────────────────────────


@dataclass
class AdvisorOutput:
    """Structured config suggestion from the AI Input Advisor. All optional for merge."""

    template_priority_order: list[str] = field(default_factory=list)
    preferred_module_width: Optional[float] = None
    storey_height_override: Optional[float] = None
    density_bias: Optional[str] = None  # luxury | density | balanced
    constraint_flags: dict[str, Any] = field(default_factory=dict)

    def strip_unknown_keys(self) -> None:
        """Enforce No New Config Keys: only allowed keys retained in constraint_flags."""
        if not self.constraint_flags:
            return
        allowed_sub = {"prefer_compact", "max_units_per_floor"}  # known constraint_flags keys
        self.constraint_flags = {k: v for k, v in self.constraint_flags.items() if k in allowed_sub}

    @staticmethod
    def strict_type_ok(obj: dict[str, Any]) -> bool:
        """
        Strict type validation for raw Advisor JSON. Returns False if any allowed key
        has an invalid type (reject; no coercion). Numeric fields must be int, float, or null.
        """
        tpo = obj.get("template_priority_order")
        if tpo is not None and not isinstance(tpo, list):
            return False
        pmw = obj.get("preferred_module_width")
        if pmw is not None and not isinstance(pmw, (int, float)):
            return False
        sho = obj.get("storey_height_override")
        if sho is not None and not isinstance(sho, (int, float)):
            return False
        db = obj.get("density_bias")
        if db is not None and (not isinstance(db, str) or db.strip().lower() not in DENSITY_BIAS_VALUES):
            return False
        cf = obj.get("constraint_flags")
        if cf is not None and not isinstance(cf, dict):
            return False
        if isinstance(tpo, list):
            for x in tpo:
                if not isinstance(x, str):
                    return False  # Template names must be strings only; no int/float
        return True


# ── AFTER layer (Evaluator) ───────────────────────────────────────────────────


@dataclass
class EvaluationSuggestion:
    """Single suggestion from the Evaluator. suggestion_type must be from closed enum."""

    suggestion_type: str
    reason: str
    optional_config_delta: dict[str, Any] = field(default_factory=dict)

    def is_valid_type(self) -> bool:
        return self.suggestion_type in SUGGESTION_TYPE_ENUM

    def strip_unknown_config_keys(self) -> None:
        """Only allow engine config keys in optional_config_delta."""
        self.optional_config_delta = {
            k: v for k, v in self.optional_config_delta.items()
            if k in ENGINE_CONFIG_ALLOWED_KEYS
        }


@dataclass
class EvaluatorOutput:
    """Response from the AI Evaluator. explanation + list of suggestions."""

    explanation: str = ""
    suggestions: list[EvaluationSuggestion] = field(default_factory=list)


# ── Contract summary (input to Evaluator; no geometry) ───────────────────────


@dataclass
class FloorSummary:
    """Per-floor summary for Evaluator input. No polygons."""

    floor_id: str
    total_units: int
    unit_area_sum: float
    efficiency_ratio_floor: float


@dataclass
class ContractSummary:
    """BuildingLayoutContract reduced to scalars + floor summaries for AI. No geometry."""

    building_id: str
    total_floors: int
    total_units: int
    total_unit_area: float
    total_residual_area: float
    building_efficiency: float
    building_height_m: float
    floors: list[FloorSummary] = field(default_factory=list)


# ── PARALLEL layer (Constraint Interpreter) ───────────────────────────────────


@dataclass
class ConstraintInterpreterOutput:
    """
    Structured constraints from regulatory text. Every numeric field with a value
    must have a corresponding _source_excerpt (Source Traceability).
    """

    max_height: Optional[float] = None
    max_height_source_excerpt: Optional[str] = None
    FSI_cap: Optional[float] = None
    FSI_cap_source_excerpt: Optional[str] = None
    affordable_unit_percentage: Optional[float] = None
    affordable_unit_percentage_source_excerpt: Optional[str] = None
    parking_requirements: Optional[str] = None  # or structured TBD
    parking_requirements_source_excerpt: Optional[str] = None
    cost_bias: Optional[str] = None  # low | medium | high
    cost_bias_source_excerpt: Optional[str] = None
    min_setback_m: Optional[float] = None
    min_setback_m_source_excerpt: Optional[str] = None
    max_coverage_ratio: Optional[float] = None
    max_coverage_ratio_source_excerpt: Optional[str] = None

    def validate_source_excerpts(self) -> bool:
        """If a numeric value is present, _source_excerpt is required. Returns False if invalid."""
        pairs = [
            (self.max_height, self.max_height_source_excerpt),
            (self.FSI_cap, self.FSI_cap_source_excerpt),
            (self.affordable_unit_percentage, self.affordable_unit_percentage_source_excerpt),
            (self.parking_requirements, self.parking_requirements_source_excerpt),
            (self.cost_bias, self.cost_bias_source_excerpt),
            (self.min_setback_m, self.min_setback_m_source_excerpt),
            (self.max_coverage_ratio, self.max_coverage_ratio_source_excerpt),
        ]
        for value, excerpt in pairs:
            if value is not None and (not excerpt or not str(excerpt).strip()):
                return False
        return True
