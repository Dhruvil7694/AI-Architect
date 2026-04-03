from __future__ import annotations

"""
ai_planner.program_generator
----------------------------

LLM-backed program generator that converts a free-form user brief and site
area into a structured ProgramSpec consumable by deterministic pipelines.

The LLM is only used to infer intent and mix — it never produces geometry.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config


@dataclass
class ProgramSpec:
    unit_mix: Dict[str, float]
    target_units: int
    preferred_towers: int
    max_floors: int
    open_space_priority: str
    density_priority: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgramSpec":
        unit_mix = data.get("unit_mix") or {}
        # Normalise mix keys and ensure all expected keys exist.
        keys = [
            "1bhk_compact",
            "2bhk_compact",
            "2bhk_luxury",
            "3bhk_luxury",
        ]
        normalised_mix: Dict[str, float] = {}
        for key in keys:
            try:
                normalised_mix[key] = float(unit_mix.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                normalised_mix[key] = 0.0

        try:
            target_units = int(data.get("target_units", 0) or 0)
        except (TypeError, ValueError):
            target_units = 0

        try:
            preferred_towers = int(data.get("preferred_towers", 0) or 0)
        except (TypeError, ValueError):
            preferred_towers = 0

        try:
            max_floors = int(data.get("max_floors", 0) or 0)
        except (TypeError, ValueError):
            max_floors = 0

        open_space_priority = str(
            (data.get("open_space_priority") or "medium")
        ).lower()
        if open_space_priority not in {"low", "medium", "high"}:
            open_space_priority = "medium"

        density_priority = str(
            (data.get("density_priority") or "medium")
        ).lower()
        if density_priority not in {"low", "medium", "high"}:
            density_priority = "medium"

        return cls(
            unit_mix=normalised_mix,
            target_units=target_units,
            preferred_towers=preferred_towers,
            max_floors=max_floors,
            open_space_priority=open_space_priority,
            density_priority=density_priority,
        )


def _build_system_prompt() -> str:
    return (
        "You are a senior residential architect and feasibility consultant. "
        "Given a short planning brief and site area, you propose a HIGH-LEVEL "
        "program only. You never propose geometry or tower shapes.\n\n"
        "Return a single JSON object matching exactly this schema:\n"
        "{\n"
        '  "unit_mix": {\n'
        '    "1bhk_compact": float,  // fraction 0-1\n'
        '    "2bhk_compact": float,\n'
        '    "2bhk_luxury": float,\n'
        '    "3bhk_luxury": float\n'
        "  },\n"
        '  "target_units": int,      // approximate total number of units\n'
        '  "preferred_towers": int,  // typical 1-4 towers for this brief\n'
        '  "max_floors": int,        // typical building height in floors\n'
        '  "open_space_priority": "low" | "medium" | "high",\n'
        '  "density_priority": "low" | "medium" | "high"\n'
        "}\n\n"
        "Rules:\n"
        "- Use Indian mid- to high-rise apartment precedents.\n"
        "- Use site_area_sqm only to gauge scale (small < 4000, medium 4-8000, large > 8000).\n"
        "- unit_mix values should sum to ~1.0 but do not need to be perfect.\n"
        "- If the brief emphasises luxury, bias towards 2bhk_luxury and 3bhk_luxury.\n"
        "- If the brief emphasises affordability or compact, bias towards 1bhk_compact and 2bhk_compact.\n"
    )


def _build_user_prompt(brief: str, site_area: float) -> str:
    return (
        f"User brief: {brief or 'N/A'}\n"
        f"Site area (sqm): {site_area:.1f}\n\n"
        "Infer a suitable residential program for this single site. "
        "Do not describe layouts or geometry; only fill the JSON fields."
    )


def generate_program_spec(brief: str, site_area: float) -> ProgramSpec:
    """
    Convert user brief + site area into a structured ProgramSpec.

    Uses the shared OpenAI client with JSON response mode. When the AI layer
    is disabled or unavailable, falls back to a simple heuristic program.
    """
    config = get_ai_config()
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(brief, site_area)

    raw: Optional[str] = None
    if config.advisor_enabled and config.has_api_key():
        raw = call_openai(
            model=config.advisor_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=config.advisor_timeout_s,
            temperature=config.temperature,
            rate_limit_kind="advisor",
        )

    data = parse_json_response(raw) if raw else None

    if not isinstance(data, dict):
        # Fallback: simple default program based on site size only.
        # This path is fully deterministic.
        if site_area <= 0:
            site_area = 4000.0
        if site_area < 4000:
            unit_mix = {
                "1bhk_compact": 0.3,
                "2bhk_compact": 0.5,
                "2bhk_luxury": 0.2,
                "3bhk_luxury": 0.0,
            }
            target_units = 80
            preferred_towers = 1
            max_floors = 8
        elif site_area < 8000:
            unit_mix = {
                "1bhk_compact": 0.2,
                "2bhk_compact": 0.5,
                "2bhk_luxury": 0.2,
                "3bhk_luxury": 0.1,
            }
            target_units = 160
            preferred_towers = 2
            max_floors = 12
        else:
            unit_mix = {
                "1bhk_compact": 0.15,
                "2bhk_compact": 0.4,
                "2bhk_luxury": 0.3,
                "3bhk_luxury": 0.15,
            }
            target_units = 250
            preferred_towers = 3
            max_floors = 20

        data = {
            "unit_mix": unit_mix,
            "target_units": target_units,
            "preferred_towers": preferred_towers,
            "max_floors": max_floors,
            "open_space_priority": "medium",
            "density_priority": "medium",
        }

    return ProgramSpec.from_dict(data)


__all__ = ["ProgramSpec", "generate_program_spec"]

