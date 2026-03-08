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
  Balcony        : min width 1.2 m (depth ≥ 1.2 m from exterior wall)\
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

## COORDINATE SYSTEM
- Unit is a rectangle: X = 0 to unit_width_m (along corridor axis)
                       Y = 0 to unit_depth_m (away from corridor)
- Y = 0  → CORRIDOR / ENTRY side (foyer, entry door here)
- Y = unit_depth_m → EXTERIOR WALL (bedrooms, balcony, exterior windows)
- All room rectangles defined by: x (left edge), y (bottom/corridor edge),
  w (width along X), h (height along Y)
- Units: METRES. All values are floating point.

## HARD CONSTRAINTS (non-negotiable)
{gdcr}

## DESIGN PRINCIPLES (Indian residential apartments)
1.  Foyer at Y=0, typically full width or partial, depth 1.0–1.5 m.
2.  Living room near foyer. Must have exterior window (large, toward Y=max or side).
3.  Kitchen near foyer (service access). Can be interior or side-lit.
4.  All bedrooms toward exterior wall (Y close to unit_depth_m). Exterior windows mandatory.
5.  Master bedroom: largest bedroom, attached bathroom inside the bedroom zone.
6.  Attached bathroom: tucked between two bedrooms OR as a pocket off the bedroom.
7.  Balcony: at the very exterior (Y = unit_depth_m − balcony_depth). Min depth 1.2 m.
8.  Utility/service: 0.9 × 1.5 m min, adjacent to kitchen.
9.  All rooms must be NON-OVERLAPPING rectangles that TILE the unit completely
    (allow thin inter-room walls by slightly reducing room sizes, ~0.1 m each side).
10. VASTU optional: master bed SW or NW zone, kitchen SE zone.

## DOOR & WINDOW RULES
- door_wall : which side of the room the door opening sits on
  "south" = toward Y=0 (corridor), "north" = toward exterior
  "west"  = toward X=0,            "east"  = toward X=width
- door_offset : metres from the LEFT (or BOTTOM) end of that wall to door hinge (≥ 0.1 m)
- door_width  : always 0.9 m (bedroom/living) or 0.75 m (bathroom/toilet/utility)
- window_walls: list of wall names where exterior glazing appears (exterior rooms only)
- window_offset, window_width: centre of window from left end of wall

## OUTPUT — return ONLY this exact JSON (no prose, no markdown fences):
{
  "rooms": [
    {
      "name": "Foyer",
      "type": "foyer",
      "x": 0.0, "y": 0.0, "w": 7.5, "h": 1.1,
      "door_wall": "south", "door_offset": 3.0, "door_width": 0.9,
      "window_walls": [],
      "window_offset": null, "window_width": null
    }
  ],
  "design_notes": "one sentence"
}

Allowed room types: foyer, living, dining, kitchen, bedroom, bedroom2,
                    bathroom, toilet, balcony, utility, studio
"""


# ─── User prompt builder ───────────────────────────────────────────────────────

def _user_prompt(unit_type: str, w: float, d: float, brief: str) -> str:
    rooms = _ROOM_LIST.get(unit_type.upper(), _ROOM_LIST["2BHK"])
    return (
        f"Design a {unit_type} flat.\n"
        f"Unit size: {w:.2f} m wide × {d:.2f} m deep (total {w*d:.1f} m²)\n"
        f"Entry: south wall (Y=0), approximately centred.\n"
        f"Required rooms: {rooms}\n"
        + (f"Design brief: {brief}\n" if brief else "")
        + f"\nConstraints:\n"
        f"  • All rooms must fit within X=[0,{w:.2f}], Y=[0,{d:.2f}]\n"
        f"  • Zero overlaps allowed\n"
        f"  • Tile the unit as fully as possible (≥95% area coverage)\n"
        f"  • Respect every GDCR minimum\n"
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
                temperature=0.25,   # low → more precise geometry
                max_tokens=2500,
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
