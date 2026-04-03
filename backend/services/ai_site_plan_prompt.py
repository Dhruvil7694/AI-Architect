"""
services/ai_site_plan_prompt.py
--------------------------------
Build (system_prompt, user_prompt) for GPT-4o site plan tower layout generation.

Uses a local coordinate system where (0,0) is the envelope bounding box lower-left.
The caller must store _origin_x_dxf / _origin_y_dxf from the context to translate back.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from common.units import DXF_TO_METRES


def build_site_plan_prompt(
    context: Dict[str, Any],
    error_feedback: str = "",
) -> Tuple[str, str]:
    """
    Build GPT-4o prompts for tower layout generation.

    Computes a local coordinate origin from the envelope bounding box and
    stores it in context["_origin_x_dxf"] / context["_origin_y_dxf"].
    """

    system_prompt = """You are an expert Indian real estate site planner. Given a buildable envelope and constraints, place tower footprints as axis-aligned rectangles.

RULES:
1. Tower footprints are rectangles defined by centerX, centerY, widthM, depthM.
2. Every tower must be fully inside the USABLE AREA (see dimensions below).
3. Inter-building spacing between any two towers >= required spacing.
4. Total BUA (sum of footprint_area * floors) <= maxBUA.
5. Each tower dimension >= 12m minimum.
6. If the requested number of towers cannot fit, use fewer (even 1 is OK).
7. Maximize total BUA while respecting all constraints.

OUTPUT — a single JSON object, no markdown:
{
  "towers": [
    {"id": "T1", "centerX": <float>, "centerY": <float>, "widthM": <float>, "depthM": <float>, "orientationDeg": 0, "floors": <int>}
  ],
  "designRationale": "<brief explanation>"
}"""

    c = context
    envelope_poly = c.get("envelope_polygon")

    # Compute local origin from envelope bbox lower-left
    if envelope_poly is not None and not envelope_poly.is_empty:
        ox_dxf, oy_dxf, max_x_dxf, max_y_dxf = envelope_poly.bounds
    else:
        ox_dxf, oy_dxf, max_x_dxf, max_y_dxf = 0, 0, 0, 0

    c["_origin_x_dxf"] = ox_dxf
    c["_origin_y_dxf"] = oy_dxf

    env_width_m = round((max_x_dxf - ox_dxf) * DXF_TO_METRES, 1)
    env_depth_m = round((max_y_dxf - oy_dxf) * DXF_TO_METRES, 1)

    # Compute inscribed rectangle (largest axis-aligned rect inside envelope)
    # as a simpler usable area description for the AI
    inset_m = 1.0  # safety margin from envelope edge
    usable_w = round(env_width_m - 2 * inset_m, 1)
    usable_d = round(env_depth_m - 2 * inset_m, 1)
    usable_cx = round(env_width_m / 2, 1)
    usable_cy = round(env_depth_m / 2, 1)

    spacing_m = c.get("spacing_required_m", 6.0)
    max_floors = c.get("max_floors", 20)
    n_towers = c.get("n_towers_requested", 2)
    max_bua = c.get("max_bua_sqm", 0)

    # Compute max tower footprint that fits with spacing
    if n_towers >= 2:
        # For 2 towers stacked vertically
        max_single_depth = round((usable_d - spacing_m) / 2, 1)
        fit_note = (
            f"For 2 towers stacked vertically: max tower depth = "
            f"({usable_d} - {spacing_m}) / 2 = {max_single_depth}m each. "
            f"Place T1 center at Y ~{round(inset_m + max_single_depth/2, 1)}, "
            f"T2 center at Y ~{round(env_depth_m - inset_m - max_single_depth/2, 1)}."
        )
    else:
        max_single_depth = usable_d
        fit_note = f"Single tower: use up to {usable_w}m x {usable_d}m."

    retry_section = ""
    if error_feedback:
        retry_section = f"""

PREVIOUS ATTEMPT FAILED:
{error_feedback}
Fix these issues. Reduce tower sizes or count if needed."""

    user_prompt = f"""ENVELOPE (local coordinates, origin at lower-left):
- Bounding box: {env_width_m}m wide x {env_depth_m}m deep
- Usable area: X from {inset_m} to {round(env_width_m - inset_m, 1)}, Y from {inset_m} to {round(env_depth_m - inset_m, 1)}
- Center: ({usable_cx}, {usable_cy})

CONSTRAINTS:
- Road width: {c.get('road_width_m', 0)}m
- Max height: {c.get('building_height_m', 30)}m | Max floors: {max_floors}
- Storey height: {c.get('storey_height_m', 3.0)}m
- Max FSI: {c.get('max_fsi', 0):.3f} | Max BUA: {max_bua:.0f} sqm
- Ground coverage: {c.get('ground_coverage_pct', 0):.1f}%
- Inter-building spacing: {spacing_m:.1f}m (GDCR H/3)
- Min tower dimension: 12m

DESIGN: {n_towers} towers, type={c.get('building_type', 2)}, segment={c.get('segment', 'mid')}, units/core={c.get('units_per_core', 4)}

SIZING GUIDE: {fit_note}
Max footprint per tower for BUA target: {round(max_bua / max(1, max_floors * max(1, n_towers)), 0):.0f} sqm

Place up to {n_towers} tower(s), each tower center inside usable area, with {spacing_m:.1f}m gap between towers.{retry_section}"""

    return system_prompt, user_prompt
