"""
services/plot_exploration_prompt.py
-----------------------------------
Build (system_prompt, user_prompt) for GPT-4o plot exploration scenario generation.

Input: structured context dict with plot area, road width, GDCR limits, FSI policy,
unit compatibility, and permissible building types.

Output: tuple[str, str] — (system_prompt, user_prompt).
"""
from __future__ import annotations

from typing import Any


def build_exploration_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for GPT-4o scenario generation."""

    system_prompt = """You are an expert Indian real estate development feasibility consultant specializing in GDCR (Gujarat Development Control Regulations).

Given a plot's regulatory constraints, generate exactly 3 development scenarios as a JSON object.

RULES:
- Each scenario MUST respect the provided constraints (max towers, max floors, max height, max FSI).
- buildingType MUST be one of the provided permissibleBuildingTypes IDs.
- unitMix items MUST only include unit types marked as compatible.
- Scenarios MUST be meaningfully different: one maximizes density, one balances density/livability, one prioritizes premium positioning.
- All numeric values must be realistic and internally consistent.

OUTPUT FORMAT — a single JSON object, no markdown:
{
  "scenarios": [
    {
      "id": "high_density",
      "label": "High Density",
      "description": "<one line>",
      "towers": <int>,
      "floors": <int>,
      "buildingType": <int from permissible list>,
      "segment": "<budget|mid|premium|luxury>",
      "unitMix": ["2BHK", "3BHK"],
      "unitsPerCore": <2|4|6>,
      "estimatedFSI": <float>,
      "tradeoffNote": "<one line>"
    },
    { "id": "balanced", ... },
    { "id": "premium", ... }
  ]
}"""

    c = context
    compatible_units = [k for k, v in c.get("unitCompatibility", {}).items() if v]
    building_types_str = ", ".join(
        f"ID {bt['id']}: {bt['label']} (max {bt['maxHeightM']}m)"
        for bt in c.get("permissibleBuildingTypes", [])
    )

    user_prompt = f"""PLOT ANALYSIS:
- Plot area: {c['plotAreaSqm']:.0f} sqm ({c['plotAreaSqm'] / 0.8361:.0f} sq.yd)
- Road width: {c['roadWidthM']}m
- Zone: {c.get('zone', 'R1')}

REGULATORY CONSTRAINTS:
- Max height: {c['maxHeightM']}m
- Max floors: {c['maxFloors']}
- Max FSI: {c['maxFSI']}
- Base FSI: {c['baseFSI']}
- Max ground cover: {c['maxGCPct']}%
- Max feasible towers: {c['maxFeasibleTowers']}
- Corridor eligible: {c.get('corridorEligible', False)}

PERMISSIBLE BUILDING TYPES: {building_types_str}
COMPATIBLE UNIT TYPES: {', '.join(compatible_units)}

SELLABLE RATIO TABLE (FSI → sellable sq.yd per sq.yd of plot):
  FSI 1.8 → 28, FSI 2.7 → 42, FSI 3.6 → 54, FSI 4.0 → 60
  (Use linear interpolation between points)

Generate 3 scenarios: high_density (maximize sellable area), balanced (recommended), premium (maximize unit value).
Each scenario must stay within the above constraints."""

    return system_prompt, user_prompt
