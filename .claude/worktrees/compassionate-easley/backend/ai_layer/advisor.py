"""
ai_layer/advisor.py — BEFORE layer: user intent + plot metadata → structured config suggestion.

Output is suggestion only; orchestration merges with precedence and validates before engine.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config
from ai_layer.schemas import (
    AdvisorOutput,
    ALLOWED_TEMPLATE_NAMES,
    DENSITY_BIAS_VALUES,
    ENGINE_CONFIG_ALLOWED_KEYS,
)

logger = logging.getLogger(__name__)

# Bounds for deterministic override (plan Section 2)
MODULE_WIDTH_MIN = 2.5
MODULE_WIDTH_MAX = 8.0
STOREY_HEIGHT_MIN = 2.7
STOREY_HEIGHT_MAX = 3.5

SYSTEM_PROMPT = (
    "You are an advisory assistant for a deterministic architectural layout engine. "
    "You never generate geometry or coordinates. You only output valid JSON. "
    "Output a JSON object with keys: template_priority_order (array of strings), "
    "preferred_module_width (number or null), storey_height_override (number or null), "
    "density_bias (one of: luxury, density, balanced), constraint_flags (object). "
    "Respond with a single JSON object and nothing else. "
    "Do not include reasoning chains, markdown, or explanatory text outside the JSON. "
    "Do not include comments. No code blocks."
)


def _user_prompt(user_goal: str, area_sqm: Optional[float], tp_scheme: Optional[str], fp_number: Optional[str]) -> str:
    parts = [f"User goal: {user_goal}"]
    if area_sqm is not None:
        parts.append(f"Plot area_sqm={area_sqm:.1f}")
    if tp_scheme:
        parts.append(f"tp_scheme={tp_scheme}")
    if fp_number:
        parts.append(f"fp_number={fp_number}")
    parts.append("Return only the JSON object.")
    return "\n".join(parts)


def _parse_advisor_response(obj: dict[str, Any]) -> AdvisorOutput:
    """Parse and validate; strip unknown keys, apply bounds. Strict types only; no coercion."""
    tpo = obj.get("template_priority_order")
    if not isinstance(tpo, list):
        tpo = []
    # Template names must be strings only; discard non-strings. Then filter to allowed names (discard invalid silently).
    tpo = [x.strip() for x in tpo if isinstance(x, str) and x.strip()]
    tpo = [name for name in tpo if name in ALLOWED_TEMPLATE_NAMES]
    # Empty after filtering → no template suggestion; merge treats [] as no override (only applies when non-empty).

    pmw = obj.get("preferred_module_width")
    if pmw is not None and not isinstance(pmw, (int, float)):
        pmw = None  # Reject: no coercion (e.g. "six" or "6" as str)
    if pmw is not None:
        pmw = max(MODULE_WIDTH_MIN, min(MODULE_WIDTH_MAX, float(pmw)))

    sho = obj.get("storey_height_override")
    if sho is not None and not isinstance(sho, (int, float)):
        sho = None  # Reject: no coercion
    if sho is not None:
        sho = max(STOREY_HEIGHT_MIN, min(STOREY_HEIGHT_MAX, float(sho)))

    db = obj.get("density_bias")
    if db not in DENSITY_BIAS_VALUES:
        db = None
    else:
        db = str(db).strip().lower()

    cf = obj.get("constraint_flags")
    if not isinstance(cf, dict):
        cf = {}
    allowed_sub = {"prefer_compact", "max_units_per_floor"}
    cf = {k: v for k, v in cf.items() if k in allowed_sub}

    out = AdvisorOutput(
        template_priority_order=tpo,
        preferred_module_width=pmw,
        storey_height_override=sho,
        density_bias=db,
        constraint_flags=cf,
    )
    out.strip_unknown_keys()
    return out


def advise_config(
    user_goal: str,
    plot_area_sqm: Optional[float] = None,
    tp_scheme: Optional[str] = None,
    fp_number: Optional[str] = None,
) -> Optional[AdvisorOutput]:
    """
    Call AI Input Advisor. Returns structured config suggestion or None on failure/disabled.

    Orchestration must merge with precedence (hard constraints > user overrides > this > defaults)
    and filter template_priority_order to allowed template names before passing to engine.
    """
    config = get_ai_config()
    if not config.advisor_enabled:
        return None

    user_msg = _user_prompt(user_goal, plot_area_sqm, tp_scheme, fp_number)
    raw = call_openai(
        model=config.advisor_model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_msg,
        timeout_s=config.advisor_timeout_s,
        temperature=config.temperature,
        rate_limit_kind="advisor",
    )
    if not raw:
        return None

    obj = parse_json_response(raw)
    if not obj:
        return None

    if not AdvisorOutput.strict_type_ok(obj):
        logger.debug("Advisor rejected due to strict type violation.")
        return None

    try:
        return _parse_advisor_response(obj)
    except (TypeError, ValueError):
        return None
