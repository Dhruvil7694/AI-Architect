"""
ai_planner.feasibility_suggestions
------------------------------------

Generate human-readable suggestions from a FeasibilityMap.

Two modes:
  1. Rule-based (deterministic): always available, fast, no API key needed.
  2. AI-enhanced (LLM): when OPENAI_API_KEY is set, enriches suggestions with
     contextual phrasing. Falls back to rule-based on failure or nonsense output.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config

logger = logging.getLogger(__name__)


def _rule_based_suggestions(feasibility_data: dict) -> List[str]:
    """
    Generate deterministic suggestions from feasibility data.
    Always works — no AI dependency. Must be accurate.
    """
    suggestions: list[str] = []
    tower_options = feasibility_data.get("towerOptions", [])
    max_feasible = feasibility_data.get("maxFeasibleTowers", 0)
    max_floors = feasibility_data.get("maxFloors", 0)
    max_height_m = feasibility_data.get("maxHeightM", 0.0)
    road_width_m = feasibility_data.get("roadWidthM", 0.0)
    plot_area_sqm = feasibility_data.get("plotAreaSqm", 0.0)
    max_fsi = feasibility_data.get("maxFSI", 0.0)
    recommended_towers = feasibility_data.get("recommendedTowers", 0)
    recommended_floors = feasibility_data.get("recommendedFloors", 0)

    if max_feasible == 0:
        suggestions.append(
            "This plot cannot accommodate any standard tower configuration "
            "under current GDCR constraints. Consider reviewing setback requirements."
        )
        return suggestions

    # Recommended configuration
    if recommended_towers > 0:
        rec_opt = next(
            (t for t in tower_options
             if t.get("nTowers") == recommended_towers and t.get("isFeasible")),
            None,
        )
        if rec_opt:
            fsi = rec_opt.get("estimatedFsiAtMax", 0.0)
            fp_sqm = rec_opt.get("estimatedFootprintSqm", 0.0)
            fp_w = rec_opt.get("footprintWidthM", 0.0)
            fp_d = rec_opt.get("footprintDepthM", 0.0)
            dim_str = f" ({fp_w:.0f}m x {fp_d:.0f}m)" if fp_w > 0 and fp_d > 0 else ""
            suggestions.append(
                f"Recommended: {recommended_towers} tower(s), "
                f"{recommended_floors} floors — "
                f"FSI {fsi:.2f}, ~{fp_sqm:.0f} sqm/tower{dim_str}."
            )

    # Tower count options summary
    feasible_towers = [t for t in tower_options if t.get("isFeasible")]
    if len(feasible_towers) > 1:
        parts = []
        for t in feasible_towers:
            parts.append(
                f"{t['nTowers']}T: {t['minFloors']}-{t['maxFloors']}F, "
                f"~{t.get('estimatedFootprintSqm', 0):.0f} sqm"
            )
        suggestions.append(f"Feasible options: {' | '.join(parts)}.")

    # Height cap
    if road_width_m > 0 and max_height_m > 0:
        suggestions.append(
            f"GDCR height cap: {max_height_m:.0f}m ({max_floors} floors) "
            f"for {road_width_m:.0f}m road. Max FSI: {max_fsi:.2f}."
        )

    # Plot size context
    if plot_area_sqm > 0 and plot_area_sqm < 200:
        suggestions.append(
            "Small plot — single tower with compact unit mix (1BHK/2BHK) recommended."
        )
    elif plot_area_sqm > 2000:
        cop_sqm = plot_area_sqm * 0.10
        suggestions.append(
            f"Large plot ({plot_area_sqm:.0f} sqm) — COP required: ~{cop_sqm:.0f} sqm "
            f"(10% of plot area)."
        )

    # Floor plan compatibility for recommended config
    compat = feasibility_data.get("floorPlanCompat")
    if compat:
        feasible_units = []
        infeasible_units = []
        for unit, key in [("1BHK", "canFit1bhk"), ("2BHK", "canFit2bhk"),
                          ("3BHK", "canFit3bhk"), ("4BHK", "canFit4bhk"),
                          ("5BHK", "canFit5bhk")]:
            if compat.get(key, False):
                feasible_units.append(unit)
            else:
                infeasible_units.append(unit)

        if feasible_units:
            est_units = compat.get("estimatedUnitsPerFloor", 0)
            unit_str = f" (~{est_units} units/floor)" if est_units > 0 else ""
            suggestions.append(
                f"Unit types that fit: {', '.join(feasible_units)}{unit_str}."
            )
        if infeasible_units:
            suggestions.append(
                f"Unit types that DON'T fit: {', '.join(infeasible_units)} — "
                f"footprint too compact."
            )

    return suggestions


def _build_ai_prompt(feasibility_data: dict, user_context: dict | None = None) -> str:
    """Build a concise prompt for the LLM from feasibility data."""
    parts = [
        f"Plot area: {feasibility_data.get('plotAreaSqm', 0):.0f} sqm",
        f"Road width: {feasibility_data.get('roadWidthM', 0):.0f}m",
        f"Height cap: {feasibility_data.get('maxHeightM', 0):.0f}m ({feasibility_data.get('maxFloors', 0)} floors)",
        f"Max FSI: {feasibility_data.get('maxFSI', 0):.2f}",
        f"Max feasible towers: {feasibility_data.get('maxFeasibleTowers', 0)}",
    ]

    tower_options = feasibility_data.get("towerOptions", [])
    for t in tower_options:
        status = "FEASIBLE" if t.get("isFeasible") else "NOT FEASIBLE"
        fp_w = t.get("footprintWidthM", 0)
        fp_d = t.get("footprintDepthM", 0)
        dim_str = f", dims={fp_w:.0f}x{fp_d:.0f}m" if fp_w > 0 else ""
        parts.append(
            f"  {t.get('nTowers')} tower(s): {status}, "
            f"floors {t.get('minFloors', 0)}-{t.get('maxFloors', 0)}, "
            f"footprint ~{t.get('estimatedFootprintSqm', 0):.0f}sqm{dim_str}, "
            f"FSI ~{t.get('estimatedFsiAtMax', 0):.2f}"
        )

    compat = feasibility_data.get("floorPlanCompat")
    if compat:
        fits = [u for u, k in [("1BHK","canFit1bhk"),("2BHK","canFit2bhk"),
                                ("3BHK","canFit3bhk"),("4BHK","canFit4bhk")]
                if compat.get(k)]
        parts.append(f"  Unit types that fit: {', '.join(fits) if fits else 'none'}")

    if user_context:
        if user_context.get("requested_towers"):
            parts.append(f"User requested: {user_context['requested_towers']} tower(s)")
        if user_context.get("unit_mix"):
            parts.append(f"User unit mix: {', '.join(user_context['unit_mix'])}")

    return "\n".join(parts)


_SYSTEM_PROMPT = """You are an architecture feasibility advisor for GDCR-compliant residential developments in Gujarat, India.

Given plot feasibility data, generate 3-5 concise, actionable suggestions.

RULES:
- Use ONLY the numbers provided in the data. Do NOT invent or assume values.
- If plot area is X sqm, say X sqm. Do NOT say 0 sqm unless the data says 0.
- Each suggestion must be 1-2 sentences, specific with numbers.
- Focus on: recommended config, feasible alternatives, unit types that fit, regulatory limits.

Return JSON: {"suggestions": ["...", "...", ...]}"""


def _validate_ai_suggestions(
    suggestions: list[str],
    feasibility_data: dict,
) -> list[str]:
    """
    Validate AI output against actual data.
    Reject suggestions that contain obviously wrong claims.
    """
    plot_area = feasibility_data.get("plotAreaSqm", 0)
    validated = []

    for s in suggestions:
        # Reject suggestions claiming 0 area when plot has area
        if plot_area > 10 and "0 sqm" in s.lower() and "insufficient" in s.lower():
            continue
        # Reject suggestions claiming 0 FSI when FSI > 0
        max_fsi = feasibility_data.get("maxFSI", 0)
        if max_fsi > 0 and "0.00" in s and "no built-up" in s.lower():
            continue
        # Reject generic "no unit types" when there are feasible towers
        if feasibility_data.get("maxFeasibleTowers", 0) > 0 and "no unit types" in s.lower():
            continue
        validated.append(s)

    return validated


def generate_feasibility_suggestions(
    feasibility_data: dict,
    user_context: dict | None = None,
) -> List[str]:
    """
    Generate suggestions from feasibility data.
    Uses AI when available, falls back to rule-based.
    """
    # Always compute rule-based as baseline
    rule_suggestions = _rule_based_suggestions(feasibility_data)

    # Try AI enhancement
    config = get_ai_config()
    if not config.advisor_enabled or not config.has_api_key():
        return rule_suggestions

    try:
        user_prompt = _build_ai_prompt(feasibility_data, user_context)
        raw = call_openai(
            model=config.advisor_model,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            timeout_s=config.advisor_timeout_s,
            temperature=0.1,
            rate_limit_kind="advisor",
        )

        parsed = parse_json_response(raw)
        if parsed and isinstance(parsed.get("suggestions"), list):
            ai_suggestions = [
                s for s in parsed["suggestions"]
                if isinstance(s, str) and len(s) > 10
            ]
            # Validate AI output against actual data
            ai_suggestions = _validate_ai_suggestions(ai_suggestions, feasibility_data)
            if len(ai_suggestions) >= 2:
                return ai_suggestions

    except Exception as exc:
        logger.warning("AI feasibility suggestion failed: %s", exc)

    return rule_suggestions
