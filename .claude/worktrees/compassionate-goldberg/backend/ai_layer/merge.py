"""
ai_layer/merge.py — Deterministic config merge (plan Section 5).

Precedence: Hard Constraints > Explicit User Overrides > AI Advisor Suggestions > Engine Defaults.
Per-field: scalar/list/object replaced entirely by highest-precedence source; no deep merge.

Namespace: All four inputs (hard_constraints, user_overrides, advisor_suggestion, defaults)
use the same engine config namespace (ENGINE_CONFIG_ALLOWED_KEYS). Constraint Interpreter
output (max_height, FSI_cap, etc.) lives in a separate namespace; the caller must map it
to engine config keys (e.g. storey_height_override, constraint_flags) before passing as
hard_constraints. Collision handling: same key from higher precedence replaces lower;
keys are explicit and distinct within the allowlist.
"""

from __future__ import annotations

from typing import Any, Optional

from ai_layer.schemas import AdvisorOutput, ENGINE_CONFIG_ALLOWED_KEYS


def merge_config(
    hard_constraints: Optional[dict[str, Any]] = None,
    user_overrides: Optional[dict[str, Any]] = None,
    advisor_suggestion: Optional[AdvisorOutput] = None,
    defaults: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Merge config sources in deterministic order. Only allowlisted keys are retained.
    Same inputs → same output. No stochastic behavior.
    """
    hard_constraints = hard_constraints or {}
    user_overrides = user_overrides or {}
    defaults = defaults or {}
    # Restrict to allowed keys only
    hard_constraints = {k: v for k, v in hard_constraints.items() if k in ENGINE_CONFIG_ALLOWED_KEYS}
    user_overrides = {k: v for k, v in user_overrides.items() if k in ENGINE_CONFIG_ALLOWED_KEYS}

    result: dict[str, Any] = {}
    # Order: defaults first, then advisor, then user, then hard (hard wins last)
    # Plan order: 1=hard, 2=user, 3=advisor, 4=defaults. So we set in reverse: defaults, then advisor, then user, then hard.
    for k in ENGINE_CONFIG_ALLOWED_KEYS:
        if k in defaults:
            result[k] = _copy_value(defaults[k])
    if advisor_suggestion:
        # Empty template_priority_order = no suggestion; do not override (only apply when non-empty).
        if advisor_suggestion.template_priority_order:
            result["template_priority_order"] = list(advisor_suggestion.template_priority_order)
        if advisor_suggestion.preferred_module_width is not None:
            result["preferred_module_width"] = advisor_suggestion.preferred_module_width
        if advisor_suggestion.storey_height_override is not None:
            result["storey_height_override"] = advisor_suggestion.storey_height_override
        if advisor_suggestion.density_bias is not None:
            result["density_bias"] = advisor_suggestion.density_bias
        if advisor_suggestion.constraint_flags:
            result["constraint_flags"] = dict(advisor_suggestion.constraint_flags)
    for k, v in user_overrides.items():
        result[k] = _copy_value(v)
    for k, v in hard_constraints.items():
        result[k] = _copy_value(v)
    return result


def _copy_value(v: Any) -> Any:
    """Deep copy for lists/dicts so merge does not mutate inputs."""
    if isinstance(v, list):
        return list(v)
    if isinstance(v, dict):
        return dict(v)
    return v
