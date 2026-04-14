"""
services/llm_room_layout_service.py
-------------------------------------
OpenAI GPT-4o powered room layout generator.

The LLM handles spatial reasoning & adjacency; our validator owns GDCR compliance.

Coordinate frame (all values in metres):
  X : 0 → unit_width_m  (along corridor / L-axis)
  Y : 0 → unit_depth_m  (away from corridor; Y=0 = entry/corridor side)
  Y-wall names: "south" = Y=0 (corridor), "north" = Y=depth (exterior)
                "west"  = X=0,             "east"  = X=width
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from openai import OpenAI

logger = logging.getLogger(__name__)

# ─── GDCR constraints injected into every prompt ──────────────────────────────
_GDCR_TEXT = """\
GDCR §13.1.8 / §13.1.9 HARD MINIMUMS (India — mandatory, not negotiable):
  Living/Hall    : area ≥ 9.5 m²,  clear width ≥ 3.0 m
  Principal Bed  : area ≥ 9.5 m²,  clear width ≥ 2.7 m
  Secondary Bed  : area ≥ 7.5 m²,  clear width ≥ 2.5 m
  Kitchen        : area ≥ 5.5 m²,  clear width ≥ 1.8 m
  Bathroom       : 1.2 m × 1.8 m minimum (area ≥ 2.16 m²)
  WC / Toilet    : 1.1 m × 1.5 m minimum (area ≥ 1.65 m²)
  Balcony        : min width 1.2 m (depth ≥ 1.2 m from exterior wall)

GDCR §13 CLEARANCE HEIGHTS:
  Habitable room : min ceiling height 2.75 m
  Bathroom       : min ceiling height 2.1 m

GDCR VENTILATION:
  Habitable rooms: window area ≥ 1/6 of floor area (0.1667 ratio)
  Bathrooms      : mechanical vent or window required\
"""

# ─── Room lists per unit type ─────────────────────────────────────────────────
_ROOM_LIST: Dict[str, str] = {
    "STUDIO": "foyer, studio-room (living+bed combo), kitchenette, bathroom, balcony",
    "1RK":    "foyer, studio-room (living+bed combo), kitchenette, bathroom, balcony",
    "1BHK":   "foyer, living, kitchen, toilet, bedroom, bathroom, balcony",
    "2BHK":   "foyer, living, kitchen, utility, bedroom-1 (master), bathroom-1 (attached to bed-1), bedroom-2, toilet (common), balcony",
    "3BHK":   "foyer, living+dining, kitchen, utility, bedroom-1 (master), bathroom-1 (attached), bedroom-2, bathroom-2 (attached), bedroom-3, toilet (common), balcony",
    "4BHK":   "foyer, living, dining, kitchen, utility, bedroom-1 (master), bathroom-1 (attached), bedroom-2, bathroom-2 (attached), bedroom-3, bedroom-4, bathroom-3 (attached), toilet (common), balcony",
}

# ─── System prompt ────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a senior Indian residential architect designing apartment flat layouts.
You think in spatial zones and verify geometry arithmetically before returning.

## COORDINATE SYSTEM
- Unit is a rectangle: X = 0 to unit_width_m (along corridor axis)
                       Y = 0 to unit_depth_m (away from corridor)
- Y = 0  → CORRIDOR / ENTRY side (foyer, entry door here)
- Y = unit_depth_m → EXTERIOR WALL (bedrooms, balcony, exterior windows)
- All room rectangles defined by: x (left edge), y (bottom/corridor edge),
  w (width along X), h (height along Y)
- Units: METRES. All values are floating point, rounded to 2 decimal places.

## HARD CONSTRAINTS (non-negotiable)
{gdcr}

## LAYOUT STRATEGY — follow this zone-based approach:
Divide the unit into three horizontal bands before placing rooms:
  BAND A (Y=0 to ~1.2 m)          : Foyer / entry zone (full or partial width)
  BAND B (~1.2 m to ~60% of depth) : Living, kitchen, utility, common toilet
  BAND C (~60% of depth to Y=max)  : Bedrooms, attached bathrooms, balcony
This ensures the public-to-private gradient typical of Indian apartments.

## DESIGN PRINCIPLES (Indian residential apartments)
1.  Foyer at Y=0, typically full width or partial, depth 1.0-1.5 m.
2.  Living room near foyer, spanning a generous area. Must have exterior window
    (large, toward Y=max or side wall). Living room should be the social hub.
3.  Kitchen near foyer (service access). Can be interior or side-lit.
    Place kitchen adjacent to utility for plumbing efficiency.
4.  All bedrooms toward exterior wall (Y close to unit_depth_m).
    Exterior windows mandatory for bedrooms — ensure window_walls includes "north".
5.  Master bedroom: largest bedroom, attached bathroom INSIDE the bedroom zone.
    The attached bathroom shares a wall with the bedroom (not floating).
6.  Attached bathroom: tucked between two bedrooms OR as a pocket off the bedroom.
    Its door_wall should face INTO the bedroom it serves.
7.  Balcony: at the very exterior (y + h = unit_depth_m). Min depth 1.2 m.
    Typically spans partial or full width of exterior wall.
8.  Utility/service: 0.9 x 1.5 m min, adjacent to kitchen.
9.  Common toilet: accessible from living/circulation area (not inside a bedroom).
10. VASTU preferred: master bed SW or NW zone, kitchen SE zone.

## OVERLAP PREVENTION — CRITICAL
- All rooms must be NON-OVERLAPPING rectangles that TILE the unit.
- For room R: the occupied region is [x, x+w] x [y, y+h].
- Two rooms overlap if their X-ranges AND Y-ranges BOTH intersect.
- Before returning, mentally verify: for every pair of adjacent rooms,
  confirm one edge aligns exactly (shared wall) with no incursion.
- Allow ~0.1 m gaps for inter-room wall thickness.
- Sum of all room areas should be >= 92% of unit area (w x d).

## DOOR & WINDOW RULES
- door_wall : which side of the room the door opening sits on
  "south" = toward Y=0 (corridor), "north" = toward exterior
  "west"  = toward X=0,            "east"  = toward X=width
- door_offset : metres from the LEFT (or BOTTOM) end of that wall to door hinge (>= 0.1 m)
- door_width  : always 0.9 m (bedroom/living) or 0.75 m (bathroom/toilet/utility)
- Doors must not overflow: door_offset + door_width <= wall_length - 0.1 m
- window_walls: list of wall names where exterior glazing appears (exterior rooms only)
- window_offset: metres from left end of wall to centre of window
- window_width: width of window opening (typically 1.0-1.5 m)
- Bedrooms and living MUST have window_walls set (exterior light is mandatory).

## ADJACENCY RULES
- Bathroom/toilet doors must open into a circulation area or the bedroom they serve,
  never directly into the kitchen or living room.
- Kitchen and utility should share a wall for plumbing stack alignment.
- Foyer must connect to living room (shared wall or direct adjacency).

## SELF-CHECK (do this before returning)
1. Verify every room's x+w <= unit_width_m and y+h <= unit_depth_m.
2. Verify no two rooms overlap (X-range AND Y-range both intersecting).
3. Verify every bedroom/living has window_walls set.
4. Verify w*h >= GDCR minimum area for each room type.
5. Verify min(w,h) >= GDCR minimum clear width for each room type.

## OUTPUT — return ONLY this exact JSON (no prose, no markdown fences):
{{
  "rooms": [
    {{
      "name": "Foyer",
      "type": "foyer",
      "x": 0.0, "y": 0.0, "w": 7.5, "h": 1.1,
      "door_wall": "south", "door_offset": 3.0, "door_width": 0.9,
      "window_walls": [],
      "window_offset": null, "window_width": null
    }}
  ],
  "design_notes": "one sentence"
}}

Allowed room types: foyer, living, dining, kitchen, bedroom, bedroom2,
                    bathroom, toilet, balcony, utility, studio
"""


# ─── User prompt builder ───────────────────────────────────────────────────────

def _user_prompt(unit_type: str, w: float, d: float, brief: str) -> str:
    rooms = _ROOM_LIST.get(unit_type.upper(), _ROOM_LIST["2BHK"])
    total_area = w * d
    return (
        f"Design a {unit_type} flat.\n"
        f"Unit size: {w:.2f} m wide x {d:.2f} m deep (total {total_area:.1f} m2)\n"
        f"Entry: south wall (Y=0), approximately centred.\n"
        f"Required rooms: {rooms}\n"
        + (f"Design brief: {brief}\n" if brief else "")
        + f"\nConstraints (ALL must be satisfied):\n"
        f"  - Every room must fit within X=[0, {w:.2f}], Y=[0, {d:.2f}]\n"
        f"  - Zero overlaps: no two rooms may share interior area\n"
        f"  - Tile the unit as fully as possible (target >= 95% of {total_area:.1f} m2)\n"
        f"  - Respect every GDCR minimum area AND clear-width\n"
        f"  - Bedrooms and living room MUST have window_walls set\n"
        f"\nApproach: First mentally divide {d:.2f} m depth into 3 bands \n"
        f"(entry -> public -> private), then allocate rooms within each band.\n"
        f"Verify arithmetic: sum of all room areas should be close to {total_area:.1f} m2 and \n"
        f"no room exceeds the unit boundary.\n"
        f"\nReturn the JSON layout now."
    )


# ─── Main function ─────────────────────────────────────────────────────────────

def generate_llm_room_layout(
    unit_type: str,
    unit_width_m: float,
    unit_depth_m: float,
    design_brief: str = "",
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    Call OpenAI GPT-4o to generate a room layout.

    Returns
    -------
    dict with "rooms" (list) and "design_notes" (str).

    Raises RuntimeError if all attempts fail.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in the environment.")

    client = OpenAI(api_key=api_key)
    system = _SYSTEM_PROMPT.format(gdcr=_GDCR_TEXT)
    user   = _user_prompt(unit_type, unit_width_m, unit_depth_m, design_brief)

    logger.debug("LLM system prompt length: %d chars", len(system))
    logger.debug("LLM user prompt length: %d chars", len(user))

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.20,   # low → more precise geometry
                max_tokens=3500,    # allow room for larger unit types
            )
            data: Dict = json.loads(resp.choices[0].message.content)

            if not isinstance(data.get("rooms"), list) or not data["rooms"]:
                raise ValueError("LLM returned no 'rooms' list.")

            logger.info(
                "LLM room layout OK: %d rooms for %s (attempt %d)",
                len(data["rooms"]), unit_type, attempt + 1,
            )
            return data

        except Exception as exc:
            last_err = exc
            logger.warning("LLM layout attempt %d failed: %s", attempt + 1, exc)

    raise RuntimeError(
        f"LLM room layout failed after {max_retries + 1} attempts: {last_err}"
    )
