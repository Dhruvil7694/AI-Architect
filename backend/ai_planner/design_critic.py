from __future__ import annotations

"""
ai_planner.design_critic
------------------------

High-level narrative explanation of layout quality for a single pipeline run.

Inputs:
  - placement_debug_metrics: PlacementDebugMetrics (or its dict form)
  - plan_metrics: dict of aggregate plan metrics (FSI, GC, towers, etc.)

Output:
  - List of 3–5 human-readable bullet insights covering:
      * open space quality
      * tower alignment
      * COP placement
      * density trade-offs

The critic is text-only: it never proposes or modifies geometry.
When the AI layer is enabled, we delegate phrasing to the LLM; otherwise we
fall back to a simple rule-based summary.
"""

from typing import Any, Dict, Iterable, List, Optional

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config


def _metrics_to_dict(placement_debug_metrics: Any) -> Dict[str, Any]:
    if placement_debug_metrics is None:
        return {}
    if isinstance(placement_debug_metrics, dict):
        return placement_debug_metrics
    # PlacementDebugMetrics dataclass exposes to_dict()
    to_dict = getattr(placement_debug_metrics, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    # Fallback: shallow attribute dump of common fields
    fields = [
        "envelope_area_sqft",
        "footprint_area_sqft",
        "leftover_area_sqft",
        "leftover_compactness_score",
        "road_frontage_length_m",
        "tower_orientation_angles_deg",
        "cop_area_sqft",
        "cop_min_dimension_m",
        "footprint_utilization_pct",
        "leftover_utilization_pct",
        "n_towers_placed",
        "open_space_consolidation",
        "largest_open_area_sqft",
        "edge_alignment_ratio",
    ]
    result: Dict[str, Any] = {}
    for f in fields:
        if hasattr(placement_debug_metrics, f):
            result[f] = getattr(placement_debug_metrics, f)
    return result


def _build_system_prompt() -> str:
    return (
        "You are a senior urban designer and design juror.\n"
        "You receive quantitative metrics for a site layout and must explain the\n"
        "quality of the solution to architects in clear, neutral language.\n\n"
        "You NEVER propose new geometry. You only interpret the given metrics.\n\n"
        "Return a JSON object with a single key:\n"
        "{ \"insights\": [\"point 1\", \"point 2\", ...] }\n"
        "Use 3–5 concise bullet points written as complete sentences.\n"
    )


def _build_user_prompt(
    placement_metrics: Dict[str, Any],
    plan_metrics: Dict[str, Any],
    user_note: str = "",
) -> str:
    note_section = f"\nArchitect's note: {user_note.strip()}\n" if user_note.strip() else ""
    return (
        "You are given:\n\n"
        f"Plan metrics (JSON):\n{plan_metrics}\n"
        f"{note_section}\n"
        "Explain:\n"
        "1) Open space quality — is the COP generous, usable, and correctly positioned at the rear?\n"
        "2) Tower placement — does the number of towers and height make architectural sense?\n"
        "3) FSI utilisation — how close to the regulatory ceiling, is it well optimised?\n"
        "4) Ground coverage — is it appropriate for a residential development?\n"
        "5) One key recommendation the architect should act on next.\n"
        "Be precise and professional. Mention specific numbers only where they reveal a problem or strength."
    )


def _rule_based_insights(
    placement_metrics: Dict[str, Any],
    plan_metrics: Dict[str, Any],
) -> List[str]:
    insights: List[str] = []

    # Open space quality
    leftover_pct = float(placement_metrics.get("leftover_utilization_pct") or 0.0)
    consolidation = float(placement_metrics.get("open_space_consolidation") or 0.0)
    if leftover_pct < 10:
        insights.append(
            "Open space inside the envelope is quite limited; most buildable area is covered by tower footprints and spacing buffers."
        )
    elif consolidation > 0.7:
        insights.append(
            "A large portion of leftover area consolidates into one or two dominant open spaces, which helps create a clear common courtyard."
        )
    else:
        insights.append(
            "Leftover open space is moderately fragmented, suggesting several smaller pockets rather than one dominant courtyard."
        )

    # Tower alignment
    edge_align = float(placement_metrics.get("edge_alignment_ratio") or 0.0)
    orientations = placement_metrics.get("tower_orientation_angles_deg") or []
    n_towers = int(placement_metrics.get("n_towers_placed") or 0)
    if n_towers == 0:
        insights.append("No valid tower placement was found for this configuration.")
    else:
        if edge_align > 0.4:
            insights.append(
                "Towers are well aligned with the primary envelope edges, which should read as clean street-aligned bars."
            )
        else:
            insights.append(
                "Tower footprints are not strongly aligned with the main envelope edges, so the plan may feel more free-form or staggered."
            )
        if isinstance(orientations, (list, tuple)) and len(orientations) > 1:
            spread = max(orientations) - min(orientations)
            if spread > 20:
                insights.append(
                    "Tower orientations vary significantly, which can improve views but may complicate facade regularity."
                )

    # COP
    cop_area_sqft = float(placement_metrics.get("cop_area_sqft") or 0.0)
    cop_min_dim = float(placement_metrics.get("cop_min_dimension_m") or 0.0)
    if cop_area_sqft <= 0:
        insights.append(
            "No dedicated Common Open Plot (COP) could be identified in the envelope metrics."
        )
    else:
        if cop_min_dim < 15:
            insights.append(
                "COP area is present but relatively narrow in at least one dimension, which may limit its usability for larger gatherings or play."
            )
        else:
            insights.append(
                "COP area is reasonably wide, which should work well as a central green or shared amenity space."
            )

    # Density trade-offs
    achieved_fsi = float(plan_metrics.get("achievedFSI") or plan_metrics.get("achieved_fsi") or 0.0)
    max_fsi = float(plan_metrics.get("maxFSI") or plan_metrics.get("max_fsi") or 0.0)
    gc_pct = float(plan_metrics.get("achievedGCPct") or plan_metrics.get("gc_utilization_pct") or 0.0)
    if max_fsi > 0:
        utilisation = achieved_fsi / max_fsi
        if utilisation > 0.9:
            insights.append(
                "The plan pushes built-up area close to the regulatory FSI ceiling, prioritising yield over generous breathing space."
            )
        elif utilisation < 0.6:
            insights.append(
                "Achieved FSI is comfortably below the statutory ceiling, leaving room for future densification or more generous open space."
            )
        else:
            insights.append(
                "FSI utilisation is balanced, achieving reasonable density while still leaving some slack in the statutory envelope."
            )
    elif gc_pct > 0:
        insights.append(
            "Ground coverage is moderate; the plan balances tower footprint against usable open areas."
        )

    # Trim to 3–5 bullets.
    if len(insights) > 5:
        insights = insights[:5]
    while len(insights) < 3:
        insights.append(
            "Overall, the layout appears technically feasible; detailed architectural refinement can now focus on entries, podiums, and landscape."
        )

    return insights


def generate_design_insights(
    placement_debug_metrics: Any,
    plan_metrics: Dict[str, Any],
    user_note: str = "",
) -> List[str]:
    """
    Produce 3–5 textual insights explaining layout quality.

    This function is safe to call even when the AI layer is disabled; in that
    case it falls back to a deterministic, rule-based critic.
    """
    placement_dict = _metrics_to_dict(placement_debug_metrics)
    config = get_ai_config()

    if config.evaluator_enabled and config.has_api_key():
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(placement_dict, plan_metrics, user_note)
        raw = call_openai(
            model=config.evaluator_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=config.evaluator_timeout_s,
            temperature=config.temperature,
            rate_limit_kind="advisor",
        )
        data = parse_json_response(raw) if raw else None
        if isinstance(data, dict):
            insights = data.get("insights")
            if isinstance(insights, Iterable):
                cleaned = [str(x).strip() for x in insights if str(x).strip()]
                if 3 <= len(cleaned) <= 8:
                    return cleaned[:5]

    return _rule_based_insights(placement_dict, plan_metrics)


__all__ = ["generate_design_insights"]

