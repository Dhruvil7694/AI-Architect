"""
services/unit_interior_service.py
----------------------------------
Generate a GDCR-compliant room layout for a single residential unit.

Coordinate frame (all values in metres):
  X : 0 → unit_width_m   (along corridor / L-axis of the floor plate)
  Y : 0 → unit_depth_m   (away from corridor, toward exterior wall)
  (0, 0) = the entry door corner at the corridor side

Returns a GeoJSON FeatureCollection of room Polygon features in the local
coordinate frame, plus a GDCR compliance summary.

GDCR references:
  §13.1.7  — Storey heights
  §13.1.8  — Habitable room minimum dimensions (Table 14.1)
  §13.1.9  — Bath / WC minimum dimensions (Table 14.2)
  §13.1.10 — Balcony projection limits
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


# ─── GDCR §13.1.8 / §13.1.9 minimum room requirements ────────────────────────

_ROOM_GDCR: Dict[str, Dict[str, Any]] = {
    "foyer":    {"min_area": 0.00, "min_w": 1.20, "ref": "§13.1.8"},
    "living":   {"min_area": 9.50, "min_w": 3.00, "ref": "§13.1.8 Tbl 14.1"},
    "dining":   {"min_area": 5.00, "min_w": 2.40, "ref": "§13.1.8"},
    "kitchen":  {"min_area": 5.50, "min_w": 1.80, "ref": "§13.1.8 Tbl 14.2"},
    "bedroom":  {"min_area": 9.50, "min_w": 2.70, "ref": "§13.1.8 Tbl 14.1"},
    "bedroom2": {"min_area": 7.50, "min_w": 2.50, "ref": "§13.1.8 Tbl 14.1"},
    "bathroom": {"min_area": 2.16, "min_w": 1.20, "ref": "§13.1.9"},
    "toilet":   {"min_area": 1.65, "min_w": 1.10, "ref": "§13.1.9"},
    "balcony":  {"min_area": 0.00, "min_w": 1.20, "ref": "§13.1.10"},
    "utility":  {"min_area": 0.00, "min_w": 0.90, "ref": "internal"},
}


# ─── Room layout templates ─────────────────────────────────────────────────────
# Each entry: (display_name, room_type, x0_frac, y0_frac, x1_frac, y1_frac)
# Fractions are multiplied by unit_width_m (x) and unit_depth_m (y).
# Y=0 = corridor/entry; Y=1 = exterior wall.

_TEMPLATES: Dict[str, List[Tuple[str, str, float, float, float, float]]] = {
    "STUDIO": [
        ("Foyer",        "foyer",    0.00, 0.00, 1.00, 0.15),
        ("Studio Room",  "living",   0.00, 0.15, 0.64, 0.78),
        ("Kitchenette",  "kitchen",  0.64, 0.15, 1.00, 0.56),
        ("Bathroom",     "bathroom", 0.64, 0.56, 1.00, 0.78),
        ("Balcony",      "balcony",  0.00, 0.78, 1.00, 1.00),
    ],
    "1BHK": [
        ("Foyer",           "foyer",    0.00, 0.00, 1.00, 0.13),
        ("Living / Hall",   "living",   0.00, 0.13, 0.60, 0.56),
        ("Kitchen",         "kitchen",  0.60, 0.13, 1.00, 0.50),
        ("Toilet",          "toilet",   0.60, 0.50, 1.00, 0.56),
        ("Bedroom",         "bedroom",  0.00, 0.56, 0.62, 0.87),
        ("Bathroom",        "bathroom", 0.62, 0.56, 1.00, 0.87),
        ("Balcony",         "balcony",  0.00, 0.87, 1.00, 1.00),
    ],
    "2BHK": [
        ("Foyer",              "foyer",    0.00, 0.00, 1.00, 0.12),
        ("Living / Hall",      "living",   0.00, 0.12, 0.58, 0.52),
        ("Kitchen",            "kitchen",  0.58, 0.12, 1.00, 0.42),
        ("Utility",            "utility",  0.58, 0.42, 1.00, 0.52),
        ("Bedroom 1 (Master)", "bedroom",  0.00, 0.52, 0.55, 0.87),
        ("Bathroom 1",         "bathroom", 0.55, 0.52, 1.00, 0.68),
        ("Bedroom 2",          "bedroom2", 0.55, 0.68, 1.00, 0.87),
        ("Toilet (Common)",    "toilet",   0.00, 0.87, 0.50, 1.00),
        ("Balcony",            "balcony",  0.50, 0.87, 1.00, 1.00),
    ],
    "3BHK": [
        ("Foyer",              "foyer",    0.00, 0.00, 1.00, 0.10),
        ("Living / Dining",    "living",   0.00, 0.10, 0.55, 0.50),
        ("Kitchen",            "kitchen",  0.55, 0.10, 1.00, 0.38),
        ("Utility",            "utility",  0.55, 0.38, 1.00, 0.50),
        ("Bedroom 1 (Master)", "bedroom",  0.00, 0.50, 0.48, 0.75),
        ("Bathroom 1 (Att.)",  "bathroom", 0.48, 0.50, 0.65, 0.63),
        ("Bedroom 2",          "bedroom2", 0.65, 0.50, 1.00, 0.75),
        ("Bathroom 2 (Att.)",  "bathroom", 0.48, 0.63, 0.65, 0.75),
        ("Bedroom 3",          "bedroom2", 0.00, 0.75, 0.55, 0.90),
        ("Toilet (Common)",    "toilet",   0.55, 0.75, 1.00, 0.90),
        ("Balcony",            "balcony",  0.00, 0.90, 1.00, 1.00),
    ],
    "4BHK": [
        ("Foyer",              "foyer",    0.00, 0.00, 1.00, 0.09),
        ("Living",             "living",   0.00, 0.09, 0.40, 0.45),
        ("Dining",             "dining",   0.40, 0.09, 0.58, 0.45),
        ("Kitchen",            "kitchen",  0.58, 0.09, 1.00, 0.34),
        ("Utility",            "utility",  0.58, 0.34, 1.00, 0.45),
        ("Bedroom 1 (Master)", "bedroom",  0.00, 0.45, 0.45, 0.68),
        ("Bathroom 1 (Att.)",  "bathroom", 0.45, 0.45, 0.62, 0.57),
        ("Bedroom 2",          "bedroom2", 0.62, 0.45, 1.00, 0.68),
        ("Bathroom 2 (Att.)",  "bathroom", 0.45, 0.57, 0.62, 0.68),
        ("Bedroom 3",          "bedroom2", 0.00, 0.68, 0.45, 0.87),
        ("Bathroom 3",         "bathroom", 0.45, 0.68, 0.62, 0.82),
        ("Bedroom 4",          "bedroom2", 0.62, 0.68, 1.00, 0.87),
        ("Toilet (Common)",    "toilet",   0.45, 0.82, 0.62, 0.87),
        ("Balcony",            "balcony",  0.00, 0.87, 1.00, 1.00),
    ],
}
_TEMPLATES["1RK"] = _TEMPLATES["STUDIO"]


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _polygon(x0: float, y0: float, x1: float, y1: float) -> Dict:
    ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
    return {"type": "Polygon", "coordinates": [ring]}


# ─── Main function ─────────────────────────────────────────────────────────────

def generate_unit_interior(
    unit_type: str,
    unit_width_m: float,
    unit_depth_m: float,
) -> Dict[str, Any]:
    """
    Generate a room-level layout for one residential unit.

    Parameters
    ----------
    unit_type    : "1BHK", "2BHK", "3BHK", "4BHK", "STUDIO", "1RK"
    unit_width_m : clear internal width of the unit (along corridor axis)
    unit_depth_m : clear internal depth of the unit (perpendicular to corridor)

    Returns
    -------
    dict with keys:
      status         : "ok" | "error"
      unit_type      : normalised unit type key
      unit_width_m   : (echoed)
      unit_depth_m   : (echoed)
      layout         : GeoJSON FeatureCollection (rooms in local metre coords)
      rooms          : list of room dicts with GDCR compliance data
      gdcr_summary   : { all_ok, violations }
    """
    key = unit_type.upper().replace(" ", "")
    template = _TEMPLATES.get(key)
    if template is None:
        # Graceful fallback: use 2BHK template
        key = "2BHK"
        template = _TEMPLATES["2BHK"]

    # Clamp to sensible minimums
    w = max(float(unit_width_m), 3.5)
    d = max(float(unit_depth_m), 4.5)

    features: List[Dict] = []
    rooms:    List[Dict] = []
    violations: List[Dict] = []

    for i, (name, rtype, xf0, yf0, xf1, yf1) in enumerate(template):
        x0, y0 = xf0 * w, yf0 * d
        x1, y1 = xf1 * w, yf1 * d
        rw   = x1 - x0
        rd   = y1 - y0
        area = rw * rd

        gdcr     = _ROOM_GDCR.get(rtype, {"min_area": 0, "min_w": 0, "ref": "—"})
        min_area = gdcr["min_area"]
        min_w    = gdcr["min_w"]
        # Use the shorter dimension as the "clear width" for GDCR check
        clear_w  = min(rw, rd)
        ok       = (area >= min_area - 0.01) and (clear_w >= min_w - 0.01)

        if not ok:
            violations.append({
                "room": name,
                "ref":  gdcr["ref"],
                "issue": (
                    f"Area {area:.1f} m² < required {min_area} m²"
                    if area < min_area
                    else f"Clear width {clear_w:.2f} m < required {min_w} m"
                ),
            })

        features.append({
            "type": "Feature",
            "id": f"room_{i}",
            "geometry": _polygon(x0, y0, x1, y1),
            "properties": {
                "name":          name,
                "room_type":     rtype,
                "area_sqm":      round(area, 2),
                "width_m":       round(rw, 2),
                "depth_m":       round(rd, 2),
                "gdcr_ok":       ok,
                "gdcr_min_area": min_area,
                "gdcr_min_w":    min_w,
                "gdcr_ref":      gdcr["ref"],
            },
        })

        rooms.append({
            "name":     name,
            "type":     rtype,
            "area_sqm": round(area, 2),
            "width_m":  round(rw, 2),
            "depth_m":  round(rd, 2),
            "gdcr_ok":  ok,
            "gdcr_ref": gdcr["ref"],
        })

    return {
        "status":        "ok",
        "unit_type":     key,
        "unit_width_m":  round(w, 2),
        "unit_depth_m":  round(d, 2),
        "layout": {
            "type":     "FeatureCollection",
            "features": features,
        },
        "rooms": rooms,
        "gdcr_summary": {
            "all_ok":     len(violations) == 0,
            "violations": violations,
        },
    }
