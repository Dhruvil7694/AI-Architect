"""
services/ai_floor_plan_prompt.py
---------------------------------
GDCR-aware system + user prompt for AI floor plan generation.

The LLM generates complete room-level layouts for all units.
Walls, doors, and windows are added deterministically by the converter.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---- GDCR room minimums ----

GDCR_ROOM_MINIMUMS: Dict[str, Dict[str, float]] = {
    "living":    {"min_area": 9.5,  "min_width": 3.0},
    "dining":    {"min_area": 7.5,  "min_width": 2.5},
    "bedroom":   {"min_area": 9.5,  "min_width": 2.7},   # master/principal
    "bedroom2":  {"min_area": 7.5,  "min_width": 2.5},   # secondary
    "kitchen":   {"min_area": 5.5,  "min_width": 1.8},
    "bathroom":  {"min_area": 2.16, "min_width": 1.2},
    "toilet":    {"min_area": 1.65, "min_width": 1.1},
    "utility":   {"min_area": 1.80, "min_width": 1.2},
    "foyer":     {"min_area": 1.80, "min_width": 1.5},
    "balcony":   {"min_area": 0.0,  "min_width": 1.2},   # min depth
    "passage":   {"min_area": 0.0,  "min_width": 1.0},
}

# ---- Room programs per unit type ----

ROOM_PROGRAMS: Dict[str, List[str]] = {
    "1BHK": [
        "foyer", "living", "kitchen", "bedroom", "bathroom", "balcony",
    ],
    "2BHK": [
        "foyer", "living", "kitchen", "utility",
        "bedroom",        # master
        "bathroom",       # attached to master
        "bedroom2",       # secondary
        "toilet",         # common
        "balcony",
    ],
    "3BHK": [
        "foyer", "living", "dining", "kitchen", "utility",
        "bedroom",        # master
        "bathroom",       # attached to master
        "bedroom2",       # secondary with attached bath
        "bathroom",       # attached to bedroom2
        "bedroom2",       # third bedroom
        "toilet",         # common
        "balcony",
    ],
    "4BHK": [
        "foyer", "living", "dining", "kitchen", "utility",
        "bedroom",        # master
        "bathroom",       # attached to master
        "bedroom2",       # bed 2
        "bathroom",       # attached to bed 2
        "bedroom2",       # bed 3
        "bedroom2",       # bed 4
        "bathroom",       # attached to bed 3 or 4
        "toilet",         # common
        "balcony",
    ],
}

# ---- Room list descriptions (kept for backward compat) ----

ROOM_LIST: Dict[str, str] = {
    "1BHK": "foyer, living, kitchen, toilet, bedroom, bathroom, balcony",
    "2BHK": (
        "foyer, living, kitchen, utility, "
        "bedroom-1 (master with attached bathroom-1), "
        "bedroom-2, toilet (common), balcony"
    ),
    "3BHK": (
        "foyer, living+dining, kitchen, utility, "
        "bedroom-1 (master with attached bathroom-1), "
        "bedroom-2 (with attached bathroom-2), "
        "bedroom-3, toilet (common), balcony"
    ),
    "4BHK": (
        "foyer, living, dining, kitchen, utility, "
        "bedroom-1 (master with attached bathroom-1), "
        "bedroom-2 (with attached bathroom-2), "
        "bedroom-3, bedroom-4 (with attached bathroom-3), "
        "toilet (common), balcony"
    ),
}

# ---- Core sizing constants ----

LIFT_SHAFT_W = 1.85
LIFT_SHAFT_D = 1.80
STAIR_W = 1.20
STAIR_D = 3.50
LOBBY_D = 2.00
CORRIDOR_W = 1.50
WALL_T = 0.23
BALCONY_DEPTH = 1.50


def n_lifts_required(height_m: float, total_units: int) -> int:
    """GDCR Part III SS 13.12.2 - minimum lifts for residential."""
    if height_m <= 10.0:
        return 0
    min_by_height = 2 if height_m > 25.0 else 1
    by_units = math.ceil(total_units / 30) if total_units > 0 else 0
    return max(min_by_height, by_units)


def n_stairs_required(height_m: float) -> int:
    """Table 13.2: residential > 15 m needs 2 staircases."""
    return 2 if height_m > 15.0 else 1


def _load_gdcr_skill_content() -> str:
    """Load GDCR regulation content from skill files for prompt injection."""
    skills_dir = Path(__file__).resolve().parent.parent.parent / ".claude" / "skills"
    sections = []
    for filename in ["definitions.md", "part3-performance.md", "part2-margins-height-parking.md"]:
        filepath = skills_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            sections.append(f"### {filename}\n{content}")
    if not sections:
        return _inline_gdcr_rules()
    return "\n\n".join(sections)


def _inline_gdcr_rules() -> str:
    """Fallback inline GDCR rules when skill files are not available."""
    lines = ["## GDCR Room Minimums (CGDCR-2017 Part III)"]
    for room_type, mins in GDCR_ROOM_MINIMUMS.items():
        lines.append(f"  {room_type}: area >= {mins['min_area']} sqm, width >= {mins['min_width']} m")
    lines.append("")
    lines.append("## Key GDCR Performance Rules")
    lines.append("  - Habitable room ventilation: openings >= 1/10th floor area (Reg 13.4)")
    lines.append("  - Min clear height: 2.9m floor-to-floor for habitable rooms (Reg 13.1.7)")
    lines.append("  - Bathroom ventilation: min 0.25 sqm opening (Reg 13.4)")
    lines.append("  - Staircase: width 1.2m (<=12m height), 1.5m (<=25m), 2.0m (>25m) (Table 13.2)")
    lines.append("  - Lift mandatory >10m height; fire lift >25m (Reg 13.12)")
    lines.append("  - Railing height min 1.15m at balcony/terrace (Reg 13.1.11)")
    lines.append("  - Min 1 WC of 0.9 sqm per dwelling unit (Reg 13.9)")
    lines.append("  - Balcony min depth 1.2m")
    return "\n".join(lines)


def _gdcr_minimums_table() -> str:
    """Format GDCR minimums as a prompt-friendly table."""
    lines = ["GDCR ROOM MINIMUMS (mandatory — never generate rooms smaller than these):"]
    lines.append("  Room Type      | Min Area (sqm) | Min Width (m)")
    lines.append("  -------------- | -------------- | -------------")
    display_names = {
        "living": "Living/Hall", "dining": "Dining", "bedroom": "Master Bedroom",
        "bedroom2": "Secondary Bedroom", "kitchen": "Kitchen", "bathroom": "Bathroom",
        "toilet": "WC/Toilet", "utility": "Utility", "foyer": "Foyer",
        "balcony": "Balcony (depth)", "passage": "Passage",
    }
    for room_type, mins in GDCR_ROOM_MINIMUMS.items():
        name = display_names.get(room_type, room_type.title())
        lines.append(f"  {name:<16}| {mins['min_area']:<14} | {mins['min_width']}")
    return "\n".join(lines)


def build_system_prompt() -> str:
    """
    Build the GDCR-aware system prompt for room-level floor plan generation.

    Three layers:
    1. Role definition (GDCR architect for Surat)
    2. GDCR regulations (from skill files or inline fallback)
    3. Architectural design principles
    """
    gdcr_content = _load_gdcr_skill_content()
    minimums_table = _gdcr_minimums_table()

    return f"""\
You are a GDCR-compliant residential floor plan architect for Surat (SUDA, Category D1).
You generate precise room-level layouts that a professional architect would approve.

Your task is to generate a COMPLETE floor plan with room-level detail for every unit.
You must place: core (lifts + stairs + lobby), corridor, and ALL rooms within each unit.

## COORDINATE SYSTEM
- Floor plate: X = 0 to floor_width_m, Y = 0 to floor_depth_m
- All values in METRES, 2 decimal places
- Y = 0 → SOUTH face (road-facing); Y = floor_depth_m → NORTH face

## FLOOR PLATE STRUCTURE
Three horizontal bands along Y:
  SOUTH BAND (Y = 0 → corridor_y) → south-facing units
  CORRIDOR (Y = corridor_y → corridor_y+{CORRIDOR_W}) → {CORRIDOR_W}m shared passage
  NORTH BAND (Y = corridor_y+{CORRIDOR_W} → floor_depth_m) → north-facing units

## GDCR REGULATIONS
{gdcr_content}

## ROOM SIZE REQUIREMENTS
{minimums_table}

## ARCHITECTURAL DESIGN PRINCIPLES (mandatory)

1. ENTRY SEQUENCE: Corridor → Foyer → Living/Dining (public zone) → Passage → Bedrooms (private zone)
2. KITCHEN ADJACENCY: Kitchen must share a wall with dining or living room; place utility room adjacent to kitchen
3. MASTER SUITE: Master bedroom on exterior wall with attached bathroom on interior side
4. WET ZONE CLUSTERING: Group all bathrooms, toilets, kitchen, and utility to share plumbing stacks (align vertically across floors)
5. BALCONY ACCESS: Balcony accessible from living room or master bedroom; placed on exterior face only
6. NO LANDLOCKED ROOMS: Every habitable room (living, dining, bedroom) must touch an exterior wall for ventilation (GDCR Reg 13.4)
7. PASSAGE AS SPINE: For 2BHK and larger, a passage connects the foyer to the bedroom zone — do NOT route through the living room to reach bedrooms
8. PROPORTIONALITY: No room should be narrower than 60% of its depth; bedrooms should be roughly square
9. MIRRORING: Units on opposite sides of the core should be mirror images for structural symmetry

## ROOM PROGRAMS

1BHK rooms: {ROOM_LIST["1BHK"]}
2BHK rooms: {ROOM_LIST["2BHK"]}
3BHK rooms: {ROOM_LIST["3BHK"]}
4BHK rooms: {ROOM_LIST["4BHK"]}

## OUTPUT FORMAT
Return ONLY a JSON object (no markdown fences, no prose):

{{
  "core": {{
    "x": <float>, "y": <float>, "w": <float>, "h": <float>,
    "stairs": [{{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}],
    "lifts":  [{{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}],
    "lobby":  {{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}
  }},
  "corridor": {{"x": 0.0, "y": <float>, "w": <float>, "h": {CORRIDOR_W}}},
  "units": [
    {{
      "id": "U1",
      "type": "2BHK",
      "side": "south",
      "x": <float>, "y": <float>, "w": <float>, "h": <float>,
      "rooms": [
        {{
          "id": "U1_R1",
          "type": "foyer",
          "x": <float>, "y": <float>, "w": <float>, "h": <float>
        }},
        {{
          "id": "U1_R2",
          "type": "living",
          "x": <float>, "y": <float>, "w": <float>, "h": <float>
        }}
      ],
      "balcony": {{"x": <float>, "y": <float>, "w": <float>, "h": <float>}}
    }}
  ],
  "design_notes": "<one sentence>"
}}

CRITICAL RULES:
- Every unit MUST have a "rooms" array with ALL rooms listed in its room program above
- Room coordinates are ABSOLUTE (relative to floor plate origin 0,0), NOT relative to unit
- All rooms must fit within their unit's bounding box (x, y, w, h)
- No two rooms may overlap within a unit
- Rooms must tile the unit area with minimal gaps
- Balcony projects OUTSIDE the unit envelope on the exterior face
"""


def build_user_prompt(
    floor_width_m: float,
    floor_depth_m: float,
    n_floors: int,
    building_height_m: float,
    units_per_core: int,
    segment: str,
    unit_mix: List[str],
    n_lifts: int,
    n_stairs: int,
    design_brief: str = "",
) -> str:
    """Build the user prompt with specific floor plate parameters."""
    effective_mix = unit_mix if unit_mix else {
        "budget": ["1BHK", "2BHK"],
        "mid": ["2BHK", "3BHK"],
        "premium": ["3BHK", "3BHK"],
        "luxury": ["3BHK", "4BHK"],
    }.get(segment, ["2BHK", "3BHK"])

    # Compute layout geometry
    core_w = max(LIFT_SHAFT_W * n_lifts + STAIR_W * n_stairs + WALL_T * 4, 4.0)
    corridor_y = round((floor_depth_m - CORRIDOR_W) / 2, 2)
    south_band_depth = round(corridor_y, 2)
    north_band_depth = round(floor_depth_m - corridor_y - CORRIDOR_W, 2)

    n_south = units_per_core // 2
    n_north = units_per_core - n_south
    if n_south == 0:
        n_south, n_north = 1, max(units_per_core - 1, 1)

    avail_width = floor_width_m - core_w
    south_unit_width = round(avail_width / n_south, 2) if n_south > 0 else 0
    north_unit_width = round(avail_width / n_north, 2) if n_north > 0 else 0

    # Assign unit types to positions
    unit_assignments = []
    idx = 0
    for i in range(n_south):
        utype = effective_mix[idx % len(effective_mix)] if effective_mix else "2BHK"
        unit_assignments.append(f"  South U{i+1}: {utype} (~{south_unit_width:.1f}m x {south_band_depth:.1f}m)")
        idx += 1
    for i in range(n_north):
        utype = effective_mix[idx % len(effective_mix)] if effective_mix else "2BHK"
        unit_assignments.append(f"  North U{n_south+i+1}: {utype} (~{north_unit_width:.1f}m x {north_band_depth:.1f}m)")
        idx += 1

    prompt = f"""\
Design a complete room-level floor plan for this residential tower:

FLOOR PLATE: {floor_width_m:.1f}m wide (X) x {floor_depth_m:.1f}m deep (Y) = {floor_width_m * floor_depth_m:.0f} sqm
BUILDING: {n_floors} floors, {building_height_m:.1f}m tall
SEGMENT: {segment}
UNITS PER CORE: {units_per_core}

LAYOUT GEOMETRY:
  Corridor: Y = {corridor_y:.2f} to Y = {corridor_y + CORRIDOR_W:.2f} (width {CORRIDOR_W}m)
  South band: Y = 0 to {south_band_depth:.2f} (depth {south_band_depth:.2f}m) — {n_south} unit(s)
  North band: Y = {corridor_y + CORRIDOR_W:.2f} to {floor_depth_m:.2f} (depth {north_band_depth:.2f}m) — {n_north} unit(s)
  Core: centered at X ≈ {floor_width_m/2:.1f}, width ≈ {core_w:.1f}m

UNIT ASSIGNMENTS:
{chr(10).join(unit_assignments)}

CORE COMPONENTS:
  {n_lifts} lift(s) ({LIFT_SHAFT_W}x{LIFT_SHAFT_D}m each)
  {n_stairs} stair(s) ({STAIR_W}x{STAIR_D}m each)
  1 lobby ({LOBBY_D}m deep)

Generate the JSON with COMPLETE room-level detail for EVERY unit. Each unit must have ALL rooms from its room program.
"""
    if design_brief:
        prompt += f"\nDesign brief: {design_brief}\n"

    return prompt
