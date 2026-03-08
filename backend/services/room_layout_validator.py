"""
services/room_layout_validator.py
----------------------------------
Validates and auto-repairs LLM-generated room layouts.

Checks:
  1. All room coordinates are within unit boundary (clamps if needed)
  2. No degenerate rooms (w < 0.5 m, h < 0.5 m)
  3. GDCR minimum area + clear width (§13.1.8 / §13.1.9)
  4. No overlapping rooms (reports warnings; does not auto-fix)
  5. Required fields present and numeric
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ─── GDCR minimums ────────────────────────────────────────────────────────────
_GDCR: Dict[str, Dict[str, float]] = {
    "foyer":    {"min_area": 0.00, "min_w": 1.00},
    "living":   {"min_area": 9.50, "min_w": 3.00},
    "dining":   {"min_area": 5.00, "min_w": 2.40},
    "kitchen":  {"min_area": 5.50, "min_w": 1.80},
    "bedroom":  {"min_area": 9.50, "min_w": 2.70},
    "bedroom2": {"min_area": 7.50, "min_w": 2.50},
    "studio":   {"min_area": 9.50, "min_w": 2.70},
    "bathroom": {"min_area": 2.16, "min_w": 1.20},
    "toilet":   {"min_area": 1.65, "min_w": 1.10},
    "balcony":  {"min_area": 0.00, "min_w": 1.20},
    "utility":  {"min_area": 0.00, "min_w": 0.90},
}

_GDCR_REF: Dict[str, str] = {
    "foyer": "§13.1.8", "living": "§13.1.8 Tbl 14.1", "dining": "§13.1.8",
    "kitchen": "§13.1.8 Tbl 14.2", "bedroom": "§13.1.8 Tbl 14.1",
    "bedroom2": "§13.1.8 Tbl 14.1", "studio": "§13.1.8 Tbl 14.1",
    "bathroom": "§13.1.9", "toilet": "§13.1.9",
    "balcony": "§13.1.10", "utility": "internal",
}


def _boxes_overlap(r1: Dict, r2: Dict, tol: float = 0.04) -> bool:
    """True if two room rectangles overlap (ignoring shared edges ≤ tol)."""
    return (
        r1["x"] + r1["w"] - tol > r2["x"]
        and r2["x"] + r2["w"] - tol > r1["x"]
        and r1["y"] + r1["h"] - tol > r2["y"]
        and r2["y"] + r2["h"] - tol > r1["y"]
    )


def validate_and_fix(
    rooms: List[Dict[str, Any]],
    unit_w: float,
    unit_d: float,
) -> Dict[str, Any]:
    """
    Validate, clamp, and annotate rooms.

    Returns
    -------
    {
        "valid"      : bool,   # True if no hard errors (warnings OK)
        "errors"     : [...],  # hard errors (degenerate rooms)
        "warnings"   : [...],  # GDCR under-size, overlaps
        "rooms"      : [...],  # fixed + annotated rooms
    }
    """
    errors:   List[str] = []
    warnings: List[str] = []
    fixed:    List[Dict] = []

    for raw in rooms:
        name  = str(raw.get("name", "Room"))
        rtype = str(raw.get("type", "living")).lower().strip()

        # ── Parse & clamp coordinates ────────────────────────────────────────
        try:
            x = float(raw.get("x", 0))
            y = float(raw.get("y", 0))
            w = float(raw.get("w", 0))
            h = float(raw.get("h", 0))
        except (TypeError, ValueError):
            errors.append(f"{name}: non-numeric coordinates — skipped.")
            continue

        # Clamp to boundary
        x = max(0.0, min(x, unit_w))
        y = max(0.0, min(y, unit_d))
        w = min(w, unit_w - x)
        h = min(h, unit_d - y)

        # Degenerate?
        if w < 0.4 or h < 0.4:
            errors.append(
                f"{name}: degenerate after clamp ({w:.2f}×{h:.2f} m) — skipped."
            )
            continue

        # ── GDCR compliance ──────────────────────────────────────────────────
        gdcr     = _GDCR.get(rtype, {"min_area": 0.0, "min_w": 0.0})
        ref      = _GDCR_REF.get(rtype, "—")
        area     = round(w * h, 2)
        clear_w  = round(min(w, h), 2)
        gdcr_ok  = (area  >= gdcr["min_area"] - 0.05) and \
                   (clear_w >= gdcr["min_w"]    - 0.04)

        if not gdcr_ok:
            issue = (
                f"area {area:.1f} m² < {gdcr['min_area']} m² min"
                if area < gdcr["min_area"] - 0.05
                else f"width {clear_w:.2f} m < {gdcr['min_w']} m min"
            )
            warnings.append(f"{name}: {issue} ({ref})")

        # ── Door defaults ────────────────────────────────────────────────────
        door_wall   = str(raw.get("door_wall", "south"))
        door_offset = float(raw.get("door_offset") or 0.3)
        door_width  = float(raw.get("door_width")  or (0.9 if rtype in
                            {"living","bedroom","bedroom2","studio"} else 0.75))
        # clamp offset so door fits on wall
        wall_len = h if door_wall in ("west", "east") else w
        door_offset = max(0.1, min(door_offset, wall_len - door_width - 0.1))

        # ── Window defaults ──────────────────────────────────────────────────
        raw_ww       = raw.get("window_walls") or []
        window_walls = [str(s) for s in raw_ww] if isinstance(raw_ww, list) else []
        window_offset = raw.get("window_offset") or None
        window_width  = float(raw.get("window_width") or 1.2)
        if window_offset is not None:
            window_offset = float(window_offset)

        fixed.append({
            "name":          name,
            "type":          rtype,
            "x":             round(x, 3),
            "y":             round(y, 3),
            "w":             round(w, 3),
            "h":             round(h, 3),
            "area_sqm":      area,
            "width_m":       round(w, 2),
            "depth_m":       round(h, 2),
            "gdcr_ok":       gdcr_ok,
            "gdcr_ref":      ref,
            "gdcr_min_area": gdcr["min_area"],
            "gdcr_min_w":    gdcr["min_w"],
            "door_wall":     door_wall,
            "door_offset":   round(door_offset, 2),
            "door_width":    round(door_width, 2),
            "window_walls":  window_walls,
            "window_offset": round(window_offset, 2) if window_offset else None,
            "window_width":  round(window_width, 2),
        })

    # ── Overlap check ────────────────────────────────────────────────────────
    for i in range(len(fixed)):
        for j in range(i + 1, len(fixed)):
            if _boxes_overlap(fixed[i], fixed[j]):
                warnings.append(
                    f"Overlap: '{fixed[i]['name']}' ∩ '{fixed[j]['name']}'"
                )

    return {
        "valid":    len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
        "rooms":    fixed,
    }
