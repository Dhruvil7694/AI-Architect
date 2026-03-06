"""
ai_layer/constraint_mapper.py — PARALLEL layer: raw regulatory text → structured constraints.

Explicit numeric extraction only; no inference. Source traceability required for every extracted number.
Conditional clauses must be preserved in full in _source_excerpt.

Important: The Constraint Interpreter does NOT evaluate conditional clauses. It extracts
numbers only; interpretation of conditional applicability (e.g. "FSI = 2.5 subject to
road width > 12m") is out of scope. The engine may receive an unconditional cap; it is
the caller's responsibility to use _source_excerpt for audit and to apply conditions
elsewhere if required.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config
from ai_layer.schemas import ConstraintInterpreterOutput

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an advisory assistant for a deterministic architectural layout engine. "
    "You never generate geometry or coordinates. You only output valid JSON. "
    "Extract constraints from the following text. "
    "Output JSON with keys: max_height, FSI_cap, affordable_unit_percentage, parking_requirements, cost_bias, "
    "and for each numeric value the corresponding _source_excerpt (e.g. FSI_cap_source_excerpt). "
    "Use null for missing. Do not invent numbers. "
    "If a constraint is conditional (e.g. on plot area, zone, or category), include the full conditional text "
    "in _source_excerpt; do not simplify or drop the condition. "
    "Respond with a single JSON object and nothing else. No markdown, comments, or text outside JSON."
)

# Max document length to control cost (plan: 12k chars)
MAX_DOCUMENT_CHARS = 12_000


def interpret_constraints(document_text: str) -> ConstraintInterpreterOutput:
    """
    Call Constraint Interpreter on raw text. Returns structured constraints with source excerpts.

    On failure or invalid response: returns empty ConstraintInterpreterOutput (all null).
    If a numeric value is present but _source_excerpt is missing, that field is discarded.
    """
    config = get_ai_config()
    if not config.constraint_interpreter_enabled:
        return ConstraintInterpreterOutput()

    text = document_text.strip()[:MAX_DOCUMENT_CHARS]
    if not text:
        return ConstraintInterpreterOutput()

    user_msg = f"Document:\n{text}"
    raw = call_openai(
        model=config.interpreter_model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_msg,
        timeout_s=config.interpreter_timeout_s,
        temperature=config.temperature,
        rate_limit_kind="interpreter",
    )
    if not raw:
        return ConstraintInterpreterOutput()

    obj = parse_json_response(raw)
    if not obj:
        return ConstraintInterpreterOutput()

    out = _parse_constraint_response(obj)
    if not out.validate_source_excerpts():
        logger.debug("Constraint interpreter: one or more fields had value but missing _source_excerpt; discarding those fields.")
        out = _discard_constraints_without_excerpt(out)
    return out


def _parse_constraint_response(obj: dict[str, Any]) -> ConstraintInterpreterOutput:
    """Build ConstraintInterpreterOutput from parsed JSON; leave null where missing. Strict types: numerics are int/float only (no coercion)."""
    def num(key: str) -> Optional[float]:
        v = obj.get(key)
        if v is None:
            return None
        if not isinstance(v, (int, float)):
            logger.debug("Constraint interpreter: rejected non-numeric value for %s (strict type).", key)
            return None  # Reject: no coercion (e.g. "2.5" or "six")
        return float(v)

    def str_or_none(key: str) -> Optional[str]:
        v = obj.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    return ConstraintInterpreterOutput(
        max_height=num("max_height"),
        max_height_source_excerpt=str_or_none("max_height_source_excerpt"),
        FSI_cap=num("FSI_cap"),
        FSI_cap_source_excerpt=str_or_none("FSI_cap_source_excerpt"),
        affordable_unit_percentage=num("affordable_unit_percentage"),
        affordable_unit_percentage_source_excerpt=str_or_none("affordable_unit_percentage_source_excerpt"),
        parking_requirements=str_or_none("parking_requirements"),
        parking_requirements_source_excerpt=str_or_none("parking_requirements_source_excerpt"),
        cost_bias=str_or_none("cost_bias"),
        cost_bias_source_excerpt=str_or_none("cost_bias_source_excerpt"),
        min_setback_m=num("min_setback_m"),
        min_setback_m_source_excerpt=str_or_none("min_setback_m_source_excerpt"),
        max_coverage_ratio=num("max_coverage_ratio"),
        max_coverage_ratio_source_excerpt=str_or_none("max_coverage_ratio_source_excerpt"),
    )


def _discard_constraints_without_excerpt(out: ConstraintInterpreterOutput) -> ConstraintInterpreterOutput:
    """Return a copy with any numeric value missing _source_excerpt set to null (and excerpt cleared)."""
    return ConstraintInterpreterOutput(
        max_height=out.max_height if out.max_height_source_excerpt else None,
        max_height_source_excerpt=out.max_height_source_excerpt,
        FSI_cap=out.FSI_cap if out.FSI_cap_source_excerpt else None,
        FSI_cap_source_excerpt=out.FSI_cap_source_excerpt,
        affordable_unit_percentage=out.affordable_unit_percentage if out.affordable_unit_percentage_source_excerpt else None,
        affordable_unit_percentage_source_excerpt=out.affordable_unit_percentage_source_excerpt,
        parking_requirements=out.parking_requirements if out.parking_requirements_source_excerpt else None,
        parking_requirements_source_excerpt=out.parking_requirements_source_excerpt,
        cost_bias=out.cost_bias if out.cost_bias_source_excerpt else None,
        cost_bias_source_excerpt=out.cost_bias_source_excerpt,
        min_setback_m=out.min_setback_m if out.min_setback_m_source_excerpt else None,
        min_setback_m_source_excerpt=out.min_setback_m_source_excerpt,
        max_coverage_ratio=out.max_coverage_ratio if out.max_coverage_ratio_source_excerpt else None,
        max_coverage_ratio_source_excerpt=out.max_coverage_ratio_source_excerpt,
    )
