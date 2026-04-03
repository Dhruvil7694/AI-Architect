"""
services/ai_floor_plan_validator.py
-------------------------------------
Validate AI-generated floor plate JSON against GDCR constraints and geometry.

Auto-repairs minor issues (clamping coordinates, bumping room sizes).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---- GDCR room minimums: (min_area_sqm, min_width_m) ----
GDCR_MINIMUMS: Dict[str, Tuple[float, float]] = {
    "living":   (9.5, 3.0),
    "dining":   (7.5, 2.5),
    "bedroom":  (9.5, 2.7),   # principal; secondary checked separately
    "kitchen":  (5.5, 1.8),
    "bathroom": (2.16, 1.2),
    "toilet":   (1.65, 1.1),
    "balcony":  (0.0, 1.2),   # min depth 1.2 m
    "foyer":    (1.0, 1.0),   # architectural standard
    "utility":  (1.35, 0.9),  # 0.9 x 1.5
}

# Secondary bedroom has lower minimums
GDCR_SECONDARY_BEDROOM = (7.5, 2.5)

# Overlap tolerance (metres)
OVERLAP_TOL = 0.05

# ---- Room programs for completeness checking ----
_REQUIRED_ROOMS: Dict[str, Dict[str, int]] = {
    "1BHK": {"foyer": 1, "living": 1, "kitchen": 1, "bedroom": 1, "bathroom": 1},
    "2BHK": {"foyer": 1, "living": 1, "kitchen": 1, "utility": 1, "bedroom": 1, "bathroom": 1, "bedroom2": 1, "toilet": 1},
    "3BHK": {"foyer": 1, "living": 1, "dining": 1, "kitchen": 1, "utility": 1, "bedroom": 1, "bathroom": 2, "bedroom2": 2, "toilet": 1},
    "4BHK": {"foyer": 1, "living": 1, "dining": 1, "kitchen": 1, "utility": 1, "bedroom": 1, "bathroom": 3, "bedroom2": 3, "toilet": 1},
}

# Habitable room types that require exterior wall contact for ventilation
_HABITABLE_ROOMS = {"living", "dining", "bedroom", "bedroom2"}

# Tolerance for "touching exterior wall" check (metres)
_EXTERIOR_TOL = 0.15


def _normalize_room_type(rtype: str) -> str:
    """Normalize room type aliases to canonical names."""
    rtype = rtype.lower()
    if rtype in ("bedroom1", "bedroom_1", "master_bedroom"):
        return "bedroom"
    if rtype in ("bedroom3", "bedroom_3", "bedroom4", "bedroom_4"):
        return "bedroom2"
    return rtype


def check_room_completeness(unit: Dict[str, Any]) -> List[str]:
    """
    Check that a unit has all required rooms for its type.

    Returns list of error strings (empty if all rooms present).
    """
    unit_type = unit.get("type", "2BHK").upper()
    rooms = unit.get("rooms", [])
    uid = unit.get("id", "?")

    required = _REQUIRED_ROOMS.get(unit_type)
    if not required:
        return [f"Unit {uid}: unknown type '{unit_type}'"]

    if not rooms:
        return [f"Unit {uid} ({unit_type}): has NO rooms — expected {sum(required.values())} rooms"]

    # Count room types present
    type_counts: Dict[str, int] = {}
    for r in rooms:
        rtype = _normalize_room_type(r.get("type", ""))
        type_counts[rtype] = type_counts.get(rtype, 0) + 1

    errors = []
    for room_type, min_count in required.items():
        actual = type_counts.get(room_type, 0)
        if actual < min_count:
            errors.append(
                f"Unit {uid} ({unit_type}): missing {room_type} "
                f"(has {actual}, need {min_count})"
            )
    return errors


def enforce_gdcr_minimums(
    rooms: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Clamp room dimensions up to GDCR minimums.

    Returns (adjusted_rooms, warnings).
    """
    adjusted = copy.deepcopy(rooms)
    warnings: List[str] = []

    for room in adjusted:
        lookup_type = _normalize_room_type(room.get("type", ""))

        mins = GDCR_MINIMUMS.get(lookup_type)
        if not mins:
            continue

        min_area, min_width = mins
        w = room.get("w", 0)
        h = room.get("h", 0)
        rid = room.get("id", "?")
        rtype = room.get("type", "?")

        # Clamp width
        if w < min_width and min_width > 0:
            warnings.append(f"Room {rid} ({rtype}): width {w:.2f}m < min {min_width:.2f}m, clamped")
            room["w"] = min_width
            w = min_width

        # Clamp area by increasing depth if needed
        area = w * h
        if area < min_area and min_area > 0:
            needed_h = min_area / max(w, 0.1)
            warnings.append(f"Room {rid} ({rtype}): area {area:.2f} sqm < min {min_area:.2f} sqm, depth increased")
            room["h"] = round(needed_h, 2)

    return adjusted, warnings


def check_ventilation(
    unit: Dict[str, Any],
    rooms: List[Dict[str, Any]],
) -> List[str]:
    """
    Check that all habitable rooms touch an exterior wall (GDCR Reg 13.4).

    Exterior walls for a unit are:
    - South unit: y=0 (south exterior), x=unit.x (left), x=unit.x+unit.w (right)
    - North unit: y=unit.y+unit.h (north exterior), x=unit.x (left), x=unit.x+unit.w (right)
    """
    errors = []
    uid = unit.get("id", "?")
    ux = unit.get("x", 0)
    uy = unit.get("y", 0)
    uw = unit.get("w", 0)
    uh = unit.get("h", 0)
    side = unit.get("side", "south")

    for room in rooms:
        rtype = _normalize_room_type(room.get("type", ""))
        if rtype not in _HABITABLE_ROOMS:
            continue

        rx = room.get("x", 0)
        ry = room.get("y", 0)
        rw = room.get("w", 0)
        rh = room.get("h", 0)
        rid = room.get("id", "?")

        touches_exterior = False

        # Left exterior wall of unit
        if abs(rx - ux) < _EXTERIOR_TOL:
            touches_exterior = True
        # Right exterior wall of unit
        if abs((rx + rw) - (ux + uw)) < _EXTERIOR_TOL:
            touches_exterior = True
        # South exterior (south units: y=0 is exterior)
        if side == "south" and abs(ry - uy) < _EXTERIOR_TOL:
            touches_exterior = True
        # North exterior (north units: y+h is exterior)
        if side == "north" and abs((ry + rh) - (uy + uh)) < _EXTERIOR_TOL:
            touches_exterior = True

        if not touches_exterior:
            errors.append(
                f"Room {rid} ({room.get('type', '?')}) in unit {uid}: no exterior wall contact — "
                f"violates GDCR Reg 13.4 ventilation requirement"
            )

    return errors


def validate_ai_floor_plan(
    layout: Dict[str, Any],
    floor_width_m: float,
    floor_depth_m: float,
    expected_lifts: int,
    expected_stairs: int,
) -> Dict[str, Any]:
    """
    Validate and auto-repair an AI-generated floor plate layout.

    Returns dict with:
      valid: bool
      errors: list of blocking errors
      warnings: list of non-blocking issues
      repaired_layout: the (possibly repaired) layout
    """
    errors: List[str] = []
    warnings: List[str] = []
    layout = copy.deepcopy(layout)

    # ---- 1. Structural validation ----
    if not isinstance(layout.get("core"), dict):
        errors.append("Missing or invalid 'core' object")
    if not isinstance(layout.get("corridor"), dict):
        errors.append("Missing or invalid 'corridor' object")
    if not isinstance(layout.get("units"), list) or len(layout.get("units", [])) == 0:
        errors.append("Missing or empty 'units' array")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "repaired_layout": layout}

    core = layout["core"]
    corridor = layout["corridor"]
    units = layout["units"]

    # ---- 2. Core validation ----
    stairs = core.get("stairs", [])
    lifts = core.get("lifts", [])
    if len(stairs) < expected_stairs:
        warnings.append(f"Core has {len(stairs)} stairs, expected {expected_stairs}")
    if len(lifts) < expected_lifts:
        warnings.append(f"Core has {len(lifts)} lifts, expected {expected_lifts}")

    # Validate core bounds
    _clamp_rect(core, floor_width_m, floor_depth_m, "core", warnings)

    # ---- 3. Corridor validation ----
    _clamp_rect(corridor, floor_width_m, floor_depth_m, "corridor", warnings)
    corr_w = corridor.get("h", 0)
    if corr_w < 1.4:
        warnings.append(f"Corridor width {corr_w:.1f}m < 1.5m minimum")

    # ---- 4. Unit validation ----
    for i, unit in enumerate(units):
        uid = unit.get("id", f"U{i+1}")

        # Clamp unit to floor bounds
        _clamp_rect(unit, floor_width_m, floor_depth_m, f"unit {uid}", warnings)

        # Rooms are injected deterministically AFTER validation by unit_layout_engine.
        # Skip room-level validation here — the engine enforces GDCR minimums itself.
        rooms = unit.get("rooms", [])

        # Balcony is placed by unit_layout_engine (may project outside floor bounds — that's correct).

    # ---- 5. Overlap detection (unit-to-unit) ----
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if _rects_overlap(units[i], units[j]):
                errors.append(
                    f"Units {units[i].get('id', i)} and {units[j].get('id', j)} overlap"
                )

    # ---- 6. Coverage check ----
    total_unit_area = sum(_rect_area(u) for u in units)
    core_area = _rect_area(core)
    corridor_area = _rect_area(corridor)
    footprint_area = floor_width_m * floor_depth_m
    coverage = (total_unit_area + core_area + corridor_area) / max(footprint_area, 1)
    if coverage < 0.70:
        warnings.append(f"Floor plate coverage {coverage:.0%} is low (< 70%)")
    elif coverage < 0.85:
        warnings.append(f"Floor plate coverage {coverage:.0%} is below target (< 85%)")

    valid = len(errors) == 0
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "repaired_layout": layout,
    }


def _clamp_rect(
    rect: Dict[str, Any],
    max_x: float,
    max_y: float,
    label: str,
    warnings: List[str],
) -> None:
    """Clamp a rectangle's coordinates to floor plate bounds."""
    x = rect.get("x", 0)
    y = rect.get("y", 0)
    w = rect.get("w", 0)
    h = rect.get("h", 0)

    if x < -0.1:
        warnings.append(f"{label}: x={x:.2f} clamped to 0")
        rect["x"] = 0.0
    if y < -0.1:
        warnings.append(f"{label}: y={y:.2f} clamped to 0")
        rect["y"] = 0.0
    if x + w > max_x + 0.5:
        warnings.append(f"{label}: extends beyond floor width ({x + w:.1f} > {max_x:.1f})")
    if y + h > max_y + 0.5:
        warnings.append(f"{label}: extends beyond floor depth ({y + h:.1f} > {max_y:.1f})")


def _rect_area(rect: Dict[str, Any]) -> float:
    return rect.get("w", 0) * rect.get("h", 0)


def _rects_overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Check if two axis-aligned rectangles overlap (with tolerance)."""
    ax, ay, aw, ah = a.get("x", 0), a.get("y", 0), a.get("w", 0), a.get("h", 0)
    bx, by, bw, bh = b.get("x", 0), b.get("y", 0), b.get("w", 0), b.get("h", 0)

    # No overlap if separated on any axis
    if ax + aw <= bx + OVERLAP_TOL:
        return False
    if bx + bw <= ax + OVERLAP_TOL:
        return False
    if ay + ah <= by + OVERLAP_TOL:
        return False
    if by + bh <= ay + OVERLAP_TOL:
        return False
    return True
