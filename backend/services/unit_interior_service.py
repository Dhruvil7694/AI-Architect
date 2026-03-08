"""
services/unit_interior_service.py
----------------------------------
Stage 3 orchestrator: LLM room layout → GDCR validation → furniture placement.

Pipeline
--------
1. Call GPT-4o for spatial reasoning (adjacency, orientation, door/window sides)
2. Validate + clamp every room against GDCR §13.1.8/9 (room_layout_validator)
3. Add furniture footprints deterministically (based on room type + dims)
4. Fall back to proportional template if LLM/network fails

Output: flat JSON that the frontend UnitInteriorView renders into a
        professional architectural drawing (walls, arcs, windows, furniture).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from services.llm_room_layout_service import generate_llm_room_layout
from services.room_layout_validator   import validate_and_fix

logger = logging.getLogger(__name__)


# ─── Furniture placement rules ────────────────────────────────────────────────
# Each entry: (type, x_frac, y_frac, w_m, h_m, notes)
# x_frac, y_frac = fraction of room dims for top-left of furniture
# Furniture coords are in room-local space (0,0 = room bottom-left)

def _place_furniture(rtype: str, rw: float, rh: float) -> List[Dict]:
    """Return furniture list in room-local metres."""
    items: List[Dict] = []
    W_WALL = 0.12   # clearance from wall

    if rtype in ("bedroom", "studio"):
        # Queen bed (1.8 × 2.0 m) — against the back wall (y = rh − 2.0 − W_WALL)
        bw, bh = min(1.8, rw - 0.6), min(2.0, rh - 0.5)
        bx = max(W_WALL, (rw - bw) / 2)
        by = max(W_WALL, rh - bh - W_WALL)
        items.append({"type": "bed_queen", "x": bx, "y": by, "w": bw, "h": bh})
        # Wardrobe (1.2 × 0.6 m) — on a side wall
        if rw > 3.0:
            items.append({"type": "wardrobe",
                          "x": rw - 1.2 - W_WALL, "y": W_WALL,
                          "w": min(1.2, rw * 0.3), "h": 0.6})

    elif rtype == "bedroom2":
        # Single/double bed (1.4 × 1.9 m)
        bw, bh = min(1.4, rw - 0.5), min(1.9, rh - 0.5)
        bx = max(W_WALL, (rw - bw) / 2)
        by = max(W_WALL, rh - bh - W_WALL)
        items.append({"type": "bed_single", "x": bx, "y": by, "w": bw, "h": bh})
        if rw > 2.8:
            items.append({"type": "wardrobe",
                          "x": rw - 1.0 - W_WALL, "y": W_WALL,
                          "w": min(1.0, rw * 0.3), "h": 0.55})

    elif rtype == "living":
        # Sofa (2.4 × 0.85 m) + coffee table (1.2 × 0.6 m)
        sw = min(2.4, rw - 0.4)
        items.append({"type": "sofa",
                      "x": max(W_WALL, (rw - sw) / 2),
                      "y": max(W_WALL, rh - 0.85 - W_WALL),
                      "w": sw, "h": 0.85})
        items.append({"type": "coffee_table",
                      "x": max(W_WALL, (rw - 1.2) / 2),
                      "y": max(W_WALL, rh - 0.85 - 0.6 - 0.5),
                      "w": min(1.2, rw * 0.5), "h": 0.5})

    elif rtype == "dining":
        # Dining table (1.2 × 0.8 m)
        tw, th = min(1.4, rw - 0.4), min(0.8, rh - 0.4)
        items.append({"type": "dining_table",
                      "x": max(W_WALL, (rw - tw) / 2),
                      "y": max(W_WALL, (rh - th) / 2),
                      "w": tw, "h": th})

    elif rtype == "kitchen":
        # L-shaped counter: slab along back wall + one side
        slab_d  = 0.6    # counter depth
        # Back counter (north wall = y = rh side)
        items.append({"type": "kitchen_counter",
                      "x": W_WALL, "y": rh - slab_d - W_WALL,
                      "w": rw - 2 * W_WALL, "h": slab_d})
        # Side counter (east wall)
        if rh > 2.5:
            items.append({"type": "kitchen_counter",
                          "x": rw - slab_d - W_WALL,
                          "y": rh - slab_d - W_WALL - min(1.5, rh * 0.3),
                          "w": slab_d, "h": min(1.5, rh * 0.3)})

    elif rtype == "bathroom":
        # WC (0.4 × 0.65 m) + basin (0.55 × 0.4 m) + shower (0.9 × 0.9 m)
        items.append({"type": "wc",
                      "x": W_WALL, "y": rh - 0.65 - W_WALL,
                      "w": 0.4, "h": 0.65})
        items.append({"type": "basin",
                      "x": W_WALL + 0.4 + 0.05, "y": rh - 0.4 - W_WALL,
                      "w": 0.55, "h": 0.4})
        if rw > 1.6 and rh > 2.0:
            items.append({"type": "shower",
                          "x": rw - 0.9 - W_WALL, "y": W_WALL,
                          "w": min(0.9, rw - 0.5), "h": min(0.9, rh - 0.5)})

    elif rtype == "toilet":
        # WC + basin only
        items.append({"type": "wc",
                      "x": W_WALL, "y": rh - 0.65 - W_WALL,
                      "w": 0.4, "h": 0.65})
        items.append({"type": "basin",
                      "x": W_WALL + 0.4 + 0.05, "y": rh - 0.4 - W_WALL,
                      "w": min(0.5, rw - 0.6), "h": 0.38})

    return items


# ─── Proportional fallback template ───────────────────────────────────────────
# Used when LLM is unavailable. (same logic as original service but enriched)

_TEMPLATES: Dict[str, List] = {
    "STUDIO": [
        ("Foyer",       "foyer",    0.00, 0.00, 1.00, 0.15, "south", 0.30, 0.75, []),
        ("Studio Room", "studio",   0.00, 0.15, 0.65, 0.78, "south", 0.30, 0.90, ["north"]),
        ("Kitchenette", "kitchen",  0.65, 0.15, 1.00, 0.55, "west",  0.20, 0.75, []),
        ("Bathroom",    "bathroom", 0.65, 0.55, 1.00, 0.78, "west",  0.10, 0.75, []),
        ("Balcony",     "balcony",  0.00, 0.78, 1.00, 1.00, "south", 0.30, 0.90, ["north"]),
    ],
    "1BHK": [
        ("Foyer",         "foyer",    0.00, 0.00, 1.00, 0.13, "south", 0.30, 0.90, []),
        ("Living / Hall", "living",   0.00, 0.13, 0.60, 0.56, "south", 0.30, 0.90, ["west"]),
        ("Kitchen",       "kitchen",  0.60, 0.13, 1.00, 0.50, "west",  0.30, 0.75, []),
        ("Toilet",        "toilet",   0.60, 0.50, 1.00, 0.56, "west",  0.10, 0.75, []),
        ("Bedroom",       "bedroom",  0.00, 0.56, 0.62, 0.87, "south", 0.30, 0.90, ["north"]),
        ("Bathroom",      "bathroom", 0.62, 0.56, 1.00, 0.87, "west",  0.10, 0.75, []),
        ("Balcony",       "balcony",  0.00, 0.87, 1.00, 1.00, "south", 0.30, 0.90, ["north"]),
    ],
    "2BHK": [
        ("Foyer",              "foyer",    0.00, 0.00, 1.00, 0.12, "south", 0.35, 0.90, []),
        ("Living / Hall",      "living",   0.00, 0.12, 0.58, 0.52, "south", 0.25, 0.90, ["west"]),
        ("Kitchen",            "kitchen",  0.58, 0.12, 1.00, 0.42, "west",  0.20, 0.75, []),
        ("Utility",            "utility",  0.58, 0.42, 1.00, 0.52, "west",  0.10, 0.75, []),
        ("Bedroom 1 (Master)", "bedroom",  0.00, 0.52, 0.55, 0.87, "south", 0.25, 0.90, ["north"]),
        ("Bathroom 1",         "bathroom", 0.55, 0.52, 1.00, 0.68, "south", 0.10, 0.75, []),
        ("Bedroom 2",          "bedroom2", 0.55, 0.68, 1.00, 0.87, "west",  0.20, 0.90, ["north"]),
        ("Toilet (Common)",    "toilet",   0.00, 0.87, 0.50, 1.00, "north", 0.10, 0.75, []),
        ("Balcony",            "balcony",  0.50, 0.87, 1.00, 1.00, "west",  0.20, 0.90, ["north"]),
    ],
    "3BHK": [
        ("Foyer",              "foyer",    0.00, 0.00, 1.00, 0.10, "south", 0.35, 0.90, []),
        ("Living / Dining",    "living",   0.00, 0.10, 0.55, 0.50, "south", 0.20, 0.90, ["west"]),
        ("Kitchen",            "kitchen",  0.55, 0.10, 1.00, 0.38, "west",  0.20, 0.75, []),
        ("Utility",            "utility",  0.55, 0.38, 1.00, 0.50, "west",  0.10, 0.75, []),
        ("Bedroom 1 (Master)", "bedroom",  0.00, 0.50, 0.48, 0.75, "south", 0.20, 0.90, ["north"]),
        ("Bathroom 1 (Att.)",  "bathroom", 0.48, 0.50, 0.65, 0.63, "south", 0.10, 0.75, []),
        ("Bedroom 2",          "bedroom2", 0.65, 0.50, 1.00, 0.75, "west",  0.20, 0.90, ["north"]),
        ("Bathroom 2 (Att.)",  "bathroom", 0.48, 0.63, 0.65, 0.75, "south", 0.10, 0.75, []),
        ("Bedroom 3",          "bedroom2", 0.00, 0.75, 0.55, 0.90, "south", 0.20, 0.90, ["north"]),
        ("Toilet (Common)",    "toilet",   0.55, 0.75, 1.00, 0.90, "west",  0.10, 0.75, []),
        ("Balcony",            "balcony",  0.00, 0.90, 1.00, 1.00, "south", 0.30, 0.90, ["north"]),
    ],
    "4BHK": [
        ("Foyer",              "foyer",    0.00, 0.00, 1.00, 0.09, "south", 0.40, 0.90, []),
        ("Living",             "living",   0.00, 0.09, 0.40, 0.45, "south", 0.15, 0.90, ["west"]),
        ("Dining",             "dining",   0.40, 0.09, 0.58, 0.45, "south", 0.10, 0.90, []),
        ("Kitchen",            "kitchen",  0.58, 0.09, 1.00, 0.34, "west",  0.15, 0.75, []),
        ("Utility",            "utility",  0.58, 0.34, 1.00, 0.45, "west",  0.10, 0.75, []),
        ("Bedroom 1 (Master)", "bedroom",  0.00, 0.45, 0.45, 0.68, "south", 0.15, 0.90, ["north"]),
        ("Bathroom 1 (Att.)",  "bathroom", 0.45, 0.45, 0.62, 0.57, "south", 0.10, 0.75, []),
        ("Bedroom 2",          "bedroom2", 0.62, 0.45, 1.00, 0.68, "west",  0.15, 0.90, ["north"]),
        ("Bathroom 2 (Att.)",  "bathroom", 0.45, 0.57, 0.62, 0.68, "south", 0.10, 0.75, []),
        ("Bedroom 3",          "bedroom2", 0.00, 0.68, 0.45, 0.87, "south", 0.15, 0.90, ["north"]),
        ("Bathroom 3",         "bathroom", 0.45, 0.68, 0.62, 0.82, "south", 0.10, 0.75, []),
        ("Bedroom 4",          "bedroom2", 0.62, 0.68, 1.00, 0.87, "west",  0.15, 0.90, ["north"]),
        ("Toilet (Common)",    "toilet",   0.45, 0.82, 0.62, 0.87, "south", 0.10, 0.75, []),
        ("Balcony",            "balcony",  0.00, 0.87, 1.00, 1.00, "south", 0.30, 0.90, ["north"]),
    ],
}
_TEMPLATES["1RK"] = _TEMPLATES["STUDIO"]


def _template_rooms(unit_type: str, w: float, d: float) -> List[Dict]:
    """Build room list from proportional template + add doors/windows."""
    key = unit_type.upper().replace(" ", "")
    tmpl = _TEMPLATES.get(key, _TEMPLATES["2BHK"])
    rooms = []
    for (name, rtype, xf0, yf0, xf1, yf1,
         door_wall, door_offset_frac, door_width, window_walls) in tmpl:
        rx, ry = xf0 * w, yf0 * d
        rw, rh = (xf1 - xf0) * w, (yf1 - yf0) * d
        # door_offset in metres (fraction of the relevant wall length)
        wall_len = rh if door_wall in ("west", "east") else rw
        door_offset = max(0.1, door_offset_frac * wall_len)
        rooms.append({
            "name": name, "type": rtype,
            "x": round(rx, 3), "y": round(ry, 3),
            "w": round(rw, 3), "h": round(rh, 3),
            "door_wall": door_wall, "door_offset": round(door_offset, 2),
            "door_width": door_width,
            "window_walls": window_walls,
            "window_offset": None, "window_width": 1.2,
        })
    return rooms


# ─── Main function ─────────────────────────────────────────────────────────────

def generate_unit_interior(
    unit_type: str,
    unit_width_m: float,
    unit_depth_m: float,
    design_brief: str = "",
) -> Dict[str, Any]:
    """
    Generate a fully enriched room layout for one residential unit.

    Parameters
    ----------
    unit_type     : "1BHK" / "2BHK" / "3BHK" / "4BHK" / "STUDIO" / "1RK"
    unit_width_m  : clear internal width (m)
    unit_depth_m  : clear internal depth (m)
    design_brief  : optional natural-language instruction to the LLM

    Returns
    -------
    {
        status         : "ok" | "error"
        source         : "llm" | "template"   (which generator was used)
        unit_type      : str
        unit_width_m   : float
        unit_depth_m   : float
        design_notes   : str
        rooms          : [enriched room dicts with furniture]
        gdcr_summary   : { all_ok, violations }
        warnings       : [str]
    }
    """
    key = unit_type.upper().replace(" ", "")
    w   = max(float(unit_width_m),  3.5)
    d   = max(float(unit_depth_m),  4.5)

    source       = "llm"
    design_notes = ""
    raw_rooms: List[Dict] = []

    # ── 1. Try LLM layout ─────────────────────────────────────────────────────
    try:
        llm_result   = generate_llm_room_layout(key, w, d, design_brief)
        raw_rooms    = llm_result.get("rooms", [])
        design_notes = llm_result.get("design_notes", "")
        logger.info("Using LLM layout for %s", key)
    except Exception as exc:
        logger.warning("LLM layout failed (%s), falling back to template.", exc)
        source    = "template"
        raw_rooms = _template_rooms(key, w, d)

    # ── 2. Validate + fix rooms ───────────────────────────────────────────────
    val = validate_and_fix(raw_rooms, w, d)
    if not val["valid"]:
        # Hard errors from LLM → try template
        if source == "llm":
            logger.warning("LLM layout had hard errors, falling back to template.")
            source    = "template"
            raw_rooms = _template_rooms(key, w, d)
            val       = validate_and_fix(raw_rooms, w, d)

    rooms: List[Dict] = val["rooms"]

    # ── 3. Add furniture to every room ────────────────────────────────────────
    violations = []
    for room in rooms:
        room["furniture"] = _place_furniture(room["type"], room["w"], room["h"])
        if not room["gdcr_ok"]:
            violations.append({
                "room":  room["name"],
                "ref":   room["gdcr_ref"],
                "issue": (
                    f"Area {room['area_sqm']:.1f} m² < {room['gdcr_min_area']} m² min"
                    if room["area_sqm"] < room["gdcr_min_area"] - 0.05
                    else f"Width {room['width_m']:.2f} m < {room['gdcr_min_w']} m min"
                ),
            })

    return {
        "status":       "ok",
        "source":       source,
        "unit_type":    key,
        "unit_width_m": round(w, 2),
        "unit_depth_m": round(d, 2),
        "design_notes": design_notes,
        "rooms":        rooms,
        "gdcr_summary": {
            "all_ok":     len(violations) == 0,
            "violations": violations,
        },
        "warnings": val["warnings"],
    }
