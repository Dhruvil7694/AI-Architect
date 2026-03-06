"""
ai_layer/evaluator.py — AFTER layer: BuildingLayoutContract summary → explanation + suggestions.

Does not modify geometry or engine outputs. Returns advisory only.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config
from ai_layer.schemas import (
    ContractSummary,
    EvaluatorOutput,
    EvaluationSuggestion,
    ENGINE_CONFIG_ALLOWED_KEYS,
    MAX_EVALUATOR_SUGGESTIONS,
    SUGGESTION_TYPE_ENUM,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an advisory assistant for a deterministic architectural layout engine. "
    "You never generate geometry or coordinates. You only output valid JSON. "
    "Output a JSON object with keys: explanation (string), suggestions (array of objects with "
    "suggestion_type, reason, optional_config_delta). "
    "suggestion_type must be one of: increase_module_width, decrease_module_width, try_compact_first, "
    "try_standard_first, reduce_floors, increase_floors, adjust_density_bias, no_change. "
    "Respond with a single JSON object and nothing else. "
    "Do not include reasoning chains, markdown, or explanatory text outside the JSON. "
    "Do not include comments. No code blocks."
)


def _contract_summary_to_user_message(summary: ContractSummary, plot_area_sqm: Optional[float] = None) -> str:
    """Build user prompt under token budget. No geometry."""
    lines = [
        f"building_id={summary.building_id}",
        f"total_floors={summary.total_floors}",
        f"total_units={summary.total_units}",
        f"total_unit_area={summary.total_unit_area:.1f}",
        f"total_residual_area={summary.total_residual_area:.1f}",
        f"building_efficiency={summary.building_efficiency:.2f}",
        f"building_height_m={summary.building_height_m:.1f}",
    ]
    if plot_area_sqm is not None:
        lines.append(f"plot_area_sqm={plot_area_sqm:.1f}")
    if summary.floors:
        # Abbreviate if many floors (plan: first 3 + last 2)
        n = len(summary.floors)
        if n <= 5:
            for f in summary.floors:
                lines.append(f"floor {f.floor_id}: units={f.total_units} unit_area_sum={f.unit_area_sum:.1f} efficiency={f.efficiency_ratio_floor:.2f}")
        else:
            for f in summary.floors[:3]:
                lines.append(f"floor {f.floor_id}: units={f.total_units} unit_area_sum={f.unit_area_sum:.1f} efficiency={f.efficiency_ratio_floor:.2f}")
            lines.append(f"... {n} floors total ...")
            for f in summary.floors[-2:]:
                lines.append(f"floor {f.floor_id}: units={f.total_units} unit_area_sum={f.unit_area_sum:.1f} efficiency={f.efficiency_ratio_floor:.2f}")
    return "Layout summary:\n" + "\n".join(lines) + "\n\nReturn only the JSON object."


def _parse_suggestions(raw: list[Any]) -> list[EvaluationSuggestion]:
    """Parse and validate suggestions; discard unknown suggestion_type and strip unknown config keys. Cap at MAX_EVALUATOR_SUGGESTIONS."""
    out = []
    for item in raw:
        if len(out) >= MAX_EVALUATOR_SUGGESTIONS:
            break
        if not isinstance(item, dict):
            continue
        st = item.get("suggestion_type")
        reason = item.get("reason") or ""
        delta = item.get("optional_config_delta")
        if not isinstance(delta, dict):
            delta = {}
        if st not in SUGGESTION_TYPE_ENUM:
            continue
        delta = {k: v for k, v in delta.items() if k in ENGINE_CONFIG_ALLOWED_KEYS}
        out.append(EvaluationSuggestion(suggestion_type=st, reason=reason, optional_config_delta=delta))
    return out


# Approximate chars per token for input truncation (cost safeguard).
# Conservative estimate only; actual token count varies by model and text. Do not treat as exact.
_CHARS_PER_TOKEN = 4


def evaluate_building(
    summary: ContractSummary,
    plot_area_sqm: Optional[float] = None,
    strategy_metadata: Optional[dict[str, Any]] = None,
) -> EvaluatorOutput:
    """
    Call AI Evaluator with contract summary. Returns explanation + suggestions or fallback.

    On API failure, invalid JSON, or disabled flag: returns fallback with explanation
    "Evaluation unavailable; layout built successfully." and empty suggestions.
    If input exceeds token limit, summary is truncated and truncation is logged.
    """
    config = get_ai_config()
    if not config.evaluator_enabled:
        return EvaluatorOutput(explanation="Evaluation unavailable; layout built successfully.", suggestions=[])

    user_msg = _contract_summary_to_user_message(summary, plot_area_sqm)
    if strategy_metadata:
        user_msg += "\nStrategy used: " + str(strategy_metadata)

    max_chars = config.evaluator_input_max_tokens * _CHARS_PER_TOKEN
    if len(user_msg) > max_chars:
        logger.warning(
            "Evaluator input truncated from %d to %d chars (token limit %d); summary was over budget.",
            len(user_msg), max_chars, config.evaluator_input_max_tokens,
        )
        user_msg = user_msg[:max_chars] + "\n\n[Input truncated for token limit.]"

    raw = call_openai(
        model=config.evaluator_model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_msg,
        timeout_s=config.evaluator_timeout_s,
        temperature=config.temperature,
        rate_limit_kind="advisor",
    )
    if not raw:
        return EvaluatorOutput(explanation="Evaluation unavailable; layout built successfully.", suggestions=[])

    obj = parse_json_response(raw)
    if not obj:
        return EvaluatorOutput(explanation="Evaluation unavailable; layout built successfully.", suggestions=[])

    explanation = obj.get("explanation")
    if not isinstance(explanation, str):
        explanation = "Evaluation unavailable; layout built successfully."
    suggestions_raw = obj.get("suggestions")
    if not isinstance(suggestions_raw, list):
        suggestions_raw = []
    suggestions = _parse_suggestions(suggestions_raw)
    return EvaluatorOutput(explanation=explanation.strip(), suggestions=suggestions)


def build_contract_summary(
    building_id: str,
    total_floors: int,
    total_units: int,
    total_unit_area: float,
    total_residual_area: float,
    building_efficiency: float,
    building_height_m: float,
    floors: list[tuple[str, int, float, float]],
) -> ContractSummary:
    """
    Build ContractSummary from BuildingLayoutContract scalars + per-floor list.
    floors: list of (floor_id, total_units, unit_area_sum, efficiency_ratio_floor).
    """
    from ai_layer.schemas import FloorSummary
    floor_summaries = [
        FloorSummary(floor_id=fid, total_units=tu, unit_area_sum=uas, efficiency_ratio_floor=eff)
        for fid, tu, uas, eff in floors
    ]
    return ContractSummary(
        building_id=building_id,
        total_floors=total_floors,
        total_units=total_units,
        total_unit_area=total_unit_area,
        total_residual_area=total_residual_area,
        building_efficiency=building_efficiency,
        building_height_m=building_height_m,
        floors=floor_summaries,
    )
