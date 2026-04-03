"""
services/ai_to_geojson_converter.py
-------------------------------------
Convert AI-generated floor plate JSON to GeoJSON FeatureCollection
matching the existing FloorPlanLayout format used by the frontend.

Walls, doors, windows, and door arcs are generated deterministically
from room geometry — NOT delegated to the LLM.

Coordinate system: local metres, Y increases northward (Y=0 = south face).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# ---- Dimensional constants ----
WALL_EXT = 0.230      # 230 mm external brick wall
WALL_INT = 0.115      # 115 mm internal partition wall
DOOR_W = 0.900        # standard door clear width
DOOR_BATH_W = 0.750   # bathroom / toilet door
DOOR_PANEL_T = 0.050  # door leaf thickness in plan view
WINDOW_DEPTH = 0.080  # window glass thickness in plan
WIN_SIL = 0.900       # typical sill height (used for info only)
DOOR_ARC_SEGS = 10    # polygon segments for door-swing arc

# Room types that are typically left open between adjacent spaces
# (no door placed on their shared wall)
_OPEN_PLAN_PAIRS: frozenset = frozenset({
    frozenset(("living", "dining")),
    frozenset(("living", "foyer")),
    frozenset(("dining", "kitchen")),   # open kitchen plans
    frozenset(("foyer", "passage")),
    frozenset(("passage", "living")),
    frozenset(("passage", "foyer")),
})

# Window widths by room type
_WIN_W: Dict[str, float] = {
    "living":          1.50,
    "dining":          1.20,
    "bedroom":         1.20,
    "bedroom1":        1.20,
    "bedroom2":        1.20,
    "bedroom3":        1.20,
    "bedroom4":        1.20,
    "master_bedroom":  1.20,
    "kitchen":         0.90,
    "bathroom":        0.60,
    "attached_bath":   0.60,
    "toilet":          0.60,
    "foyer":           0.00,   # typically no exterior window (interior location)
    "passage":         0.00,   # interior circulation — no exterior window
    "utility":         0.60,
    "balcony":         0.00,   # open-to-sky
}


# ============================================================================
# Public entry point
# ============================================================================

_SNAP_GRID = 0.05   # 50 mm grid for coordinate snapping


def _snap(v: float) -> float:
    return round(round(v / _SNAP_GRID) * _SNAP_GRID, 3)


def _snap_rect(d: Dict) -> Dict:
    """Snap x,y,w,h of a rect dict to the grid (in-place)."""
    for k in ("x", "y", "w", "h"):
        if k in d:
            d[k] = _snap(d[k])
    return d


def _snap_layout(layout: Dict) -> Dict:
    """
    Snap every coordinate in the AI layout to a 50 mm grid.
    Reduces sub-millimetre noise from the LLM so walls align cleanly.
    """
    import copy
    layout = copy.deepcopy(layout)
    for key in ("core", "corridor"):
        if key in layout:
            _snap_rect(layout[key])
    for sub in ("stairs", "lifts"):
        for item in layout.get("core", {}).get(sub, []):
            _snap_rect(item)
    lobby = layout.get("core", {}).get("lobby")
    if lobby:
        _snap_rect(lobby)
    for unit in layout.get("units", []):
        _snap_rect(unit)
        for room in unit.get("rooms", []):
            _snap_rect(room)
        if unit.get("balcony"):
            _snap_rect(unit["balcony"])
    return layout


def convert_ai_layout_to_geojson(
    ai_layout: Dict[str, Any],
    floor_width_m: float,
    floor_depth_m: float,
) -> Dict[str, Any]:
    """
    Convert AI floor plate JSON → GeoJSON FeatureCollection.

    Works in local metres (origin 0,0 = SW corner).
    Returns { type: "FeatureCollection", features: [...] }.
    """
    ai_layout = _snap_layout(ai_layout)

    features: List[Dict[str, Any]] = []
    fid = _IdGen()

    # 1. Footprint background
    features.append(_make_feature(
        fid(), "footprint_bg",
        _rect_poly(0, 0, floor_width_m, floor_depth_m),
        {"layer": "footprint_bg", "label": "Floor Plate",
         "area_sqm": round(floor_width_m * floor_depth_m, 1)},
    ))

    # 2. Core (background rect + stair + lift + lobby sub-features)
    core = ai_layout.get("core", {})
    if core:
        features.append(_make_feature(
            fid(), "core",
            _rect_poly(core["x"], core["y"], core["w"], core["h"]),
            {"layer": "core", "label": "Core",
             "area_sqm": round(core["w"] * core["h"], 1)},
        ))
        for si, stair in enumerate(core.get("stairs", [])):
            features.append(_make_feature(
                fid(), "stair",
                _rect_poly(stair["x"], stair["y"], stair["w"], stair["h"]),
                {"layer": "stair", "label": f"S{si + 1}",
                 "index": si, "area_sqm": round(stair["w"] * stair["h"], 1)},
            ))
            # Tread lines and flight direction arrow inside staircase box
            features.extend(_stair_treads(
                fid, stair["x"], stair["y"], stair["w"], stair["h"],
            ))
        for li, lift in enumerate(core.get("lifts", [])):
            features.append(_make_feature(
                fid(), "lift",
                _rect_poly(lift["x"], lift["y"], lift["w"], lift["h"]),
                {"layer": "lift", "label": f"L{li + 1}",
                 "index": li, "n_lifts": 1,
                 "area_sqm": round(lift["w"] * lift["h"], 1)},
            ))
            # Lift door indicator line on the south face (corridor side)
            features.extend(_lift_door_indicator(
                fid, lift["x"], lift["y"], lift["w"], lift["h"],
            ))
        lobby = core.get("lobby")
        if lobby:
            features.append(_make_feature(
                fid(), "lobby",
                _rect_poly(lobby["x"], lobby["y"], lobby["w"], lobby["h"]),
                {"layer": "lobby", "label": "Lobby",
                 "area_sqm": round(lobby["w"] * lobby["h"], 1)},
            ))

    # 3. Corridor
    corridor = ai_layout.get("corridor", {})
    if corridor:
        features.append(_make_feature(
            fid(), "corridor",
            _rect_poly(corridor["x"], corridor["y"],
                       corridor["w"], corridor["h"]),
            {"layer": "corridor", "label": "Corridor",
             "width_m": round(corridor["h"], 2),
             "area_sqm": round(corridor["w"] * corridor["h"], 1)},
        ))

    # 4. Units + rooms + walls + doors + windows
    for ui, unit in enumerate(ai_layout.get("units", [])):
        uid   = unit.get("id", f"U{ui + 1}")
        utype = unit.get("type", "2BHK").upper()
        ux, uy, uw, uh = unit["x"], unit["y"], unit["w"], unit["h"]
        side  = unit.get("side", "south")

        # Unit outline
        unit_area = uw * uh
        features.append(_make_feature(
            fid(), "unit",
            _rect_poly(ux, uy, uw, uh),
            {"layer": "unit", "label": uid, "unit_id": uid,
             "unit_type": utype, "side": side,
             "area_sqm": round(unit_area, 1),
             "carpet_area_sqm": round(unit_area * 0.85, 1),
             "rera_carpet_sqm": round(unit_area * 0.87, 1),
             "width_m": round(uw, 2), "depth_m": round(uh, 2),
             "index": ui},
        ))

        rooms = unit.get("rooms", [])

        # Room polygons (filled / hatched)
        for room in rooms:
            rtype = room.get("type", "living").upper()
            rname = room.get("name", rtype)
            rx, ry, rw, rh = room["x"], room["y"], room["w"], room["h"]
            features.append(_make_feature(
                fid(), "room",
                _rect_poly(rx, ry, rw, rh),
                {"layer": "room", "label": rname, "room_type": rtype,
                 "unit_id": uid,
                 "area_sqm": round(rw * rh, 1),
                 "width_m": round(rw, 2), "depth_m": round(rh, 2)},
            ))

        # Balcony fill + perimeter walls (parapet + sides) + sliding door opening
        balcony = unit.get("balcony")
        if balcony and isinstance(balcony, dict):
            bx, by, bw, bh = (balcony["x"], balcony["y"],
                               balcony["w"], balcony["h"])
            features.append(_make_feature(
                fid(), "balcony",
                _rect_poly(bx, by, bw, bh),
                {"layer": "balcony", "label": f"Balcony ({uid})",
                 "unit_id": uid, "fsi_exempt": True,
                 "area_sqm": round(bw * bh, 1),
                 "balcony_sqm": round(bw * bh, 1)},
            ))
            features.extend(_balcony_walls(fid, bx, by, bw, bh, ux, uy, uw, uh,
                                           side, uid))

        # External walls (perimeter of the unit)
        features.extend(_unit_perimeter_walls(fid, ux, uy, uw, uh, uid, side))

        # Internal walls between adjacent rooms
        features.extend(_internal_walls(fid, rooms, uid))

        # Doors (entry + internal + wet-area) with swing arcs
        door_feats = _unit_doors(fid, unit, side, floor_width_m, floor_depth_m)
        features.extend(door_feats)

        # White gap openings at every door position (punches a hole in the wall layer)
        features.extend(_door_openings(fid, door_feats, ux, uy, uw, uh, side))

        # Windows on exterior walls (auto-detected, replaces GPT window_walls)
        features.extend(_unit_windows(fid, rooms, uid,
                                      floor_width_m, floor_depth_m))

    return {"type": "FeatureCollection", "features": features}


# ============================================================================
# Internal walls
# ============================================================================

def _adjacent_pairs(rooms: List[Dict]) -> List[Tuple]:
    """
    Return all pairs of rooms that share a wall segment.

    Each result is a tuple:
      (axis, coord, seg_lo, seg_hi, room_south_or_west, room_north_or_east)

    axis   : "H" = horizontal wall running E-W
             "V" = vertical wall running N-S
    coord  : Y for H walls, X for V walls
    seg_lo : lower X (H) or lower Y (V) extent of shared segment
    seg_hi : upper X (H) or upper Y (V) extent
    """
    TOL = 0.08
    results: List[Tuple] = []
    for i, ra in enumerate(rooms):
        ax0, ay0 = ra["x"], ra["y"]
        ax1, ay1 = ax0 + ra["w"], ay0 + ra["h"]
        for rb in rooms[i + 1:]:
            bx0, by0 = rb["x"], rb["y"]
            bx1, by1 = bx0 + rb["w"], by0 + rb["h"]

            # H wall: ra top = rb bottom  →  ra is south of rb
            if abs(ay1 - by0) < TOL:
                ox0, ox1 = max(ax0, bx0), min(ax1, bx1)
                if ox1 - ox0 > 0.20:
                    results.append(("H", ay1, ox0, ox1, ra, rb))

            # H wall: rb top = ra bottom  →  rb is south of ra
            elif abs(by1 - ay0) < TOL:
                ox0, ox1 = max(ax0, bx0), min(ax1, bx1)
                if ox1 - ox0 > 0.20:
                    results.append(("H", ay0, ox0, ox1, rb, ra))

            # V wall: ra right = rb left  →  ra is west of rb
            if abs(ax1 - bx0) < TOL:
                oy0, oy1 = max(ay0, by0), min(ay1, by1)
                if oy1 - oy0 > 0.20:
                    results.append(("V", ax1, oy0, oy1, ra, rb))

            # V wall: rb right = ra left  →  rb is west of ra
            elif abs(bx1 - ax0) < TOL:
                oy0, oy1 = max(ay0, by0), min(ay1, by1)
                if oy1 - oy0 > 0.20:
                    results.append(("V", ax0, oy0, oy1, rb, ra))

    return results


def _internal_walls(fid_gen, rooms: List[Dict], uid: str) -> List[Dict]:
    """Thin partition walls between every pair of adjacent rooms."""
    walls: List[Dict] = []
    t = WALL_INT
    for axis, coord, s0, s1, _ra, _rb in _adjacent_pairs(rooms):
        if axis == "H":
            walls.append(_wall_feat(fid_gen(),
                                    s0, coord - t / 2, s1 - s0, t,
                                    uid, "internal"))
        else:
            walls.append(_wall_feat(fid_gen(),
                                    coord - t / 2, s0, t, s1 - s0,
                                    uid, "internal"))
    return walls


# ============================================================================
# Door placement
# ============================================================================

def _unit_doors(
    fid_gen,
    unit: Dict,
    side: str,
    floor_w: float,
    floor_d: float,
) -> List[Dict]:
    """
    Generate door panel + swing-arc features for:
      1. Entry door  (unit foyer → corridor)
      2. Internal doors between adjacent rooms
    """
    features: List[Dict] = []
    rooms  = unit.get("rooms", [])
    uid    = unit.get("id", "U?")
    ux, uy, uw, uh = unit["x"], unit["y"], unit["w"], unit["h"]

    # ── Entry door ──────────────────────────────────────────────────────────
    # Locate the foyer (or fall back to smallest room on corridor face)
    foyer = _find_foyer(rooms, uy, uh, side)
    if foyer:
        fx, fy, fw, fh = foyer["x"], foyer["y"], foyer["w"], foyer["h"]
        # Hinge: slightly left of foyer centre
        hinge_x = fx + max(0.15, (fw - DOOR_W) / 2 - 0.10)
        if side == "south":
            hinge_y = fy + fh          # north face of foyer
            swing    = -1              # opens south (into unit)
        else:
            hinge_y = fy               # south face of foyer
            swing    = +1              # opens north (into unit)
        features.extend(_door_h(fid_gen, hinge_x, hinge_y, DOOR_W,
                                 swing, uid, "entry"))

    # ── Internal doors ───────────────────────────────────────────────────────
    for axis, coord, s0, s1, ra, rb in _adjacent_pairs(rooms):
        ta = ra.get("type", "").lower()
        tb = rb.get("type", "").lower()

        # Skip open-plan pairs
        if frozenset((ta, tb)) in _OPEN_PLAN_PAIRS:
            continue

        # Door width
        is_wet = ta in ("bathroom", "toilet") or tb in ("bathroom", "toilet")
        dw = DOOR_BATH_W if is_wet else DOOR_W
        seg = s1 - s0
        if seg < dw + 0.20:
            continue

        # Position along segment: near corner for wet rooms, otherwise centred
        if is_wet:
            offset = 0.12
        else:
            offset = (seg - dw) / 2.0

        if axis == "H":
            hx = s0 + offset
            hy = coord
            # Swing into the wet room or the "upper" room (rb)
            if ta in ("bathroom", "toilet"):
                swing = -1  # opens south (into ra)
            else:
                swing = +1  # opens north (into rb)
            features.extend(_door_h(fid_gen, hx, hy, dw, swing, uid, "internal"))
        else:
            hx = coord
            hy = s0 + offset
            # Swing into the wet room or the "eastern" room (rb)
            if ta in ("bathroom", "toilet"):
                swing = -1  # opens west (into ra)
            else:
                swing = +1  # opens east (into rb)
            features.extend(_door_v(fid_gen, hx, hy, dw, swing, uid, "internal"))

    return features


def _find_foyer(rooms: List[Dict], uy: float, uh: float, side: str) -> Optional[Dict]:
    """Return foyer room, or the smallest room on the corridor-facing side."""
    explicit = [r for r in rooms if r.get("type", "").lower() == "foyer"]
    if explicit:
        return explicit[0]
    # Fall back: room whose corridor-facing edge is closest to the wall
    corridor_face = uy + uh if side == "south" else uy
    candidates = []
    for r in rooms:
        ry, rh = r["y"], r["h"]
        face = ry + rh if side == "south" else ry
        dist = abs(face - corridor_face)
        if dist < 0.25:
            candidates.append((r["w"] * r["h"], r))
    if candidates:
        candidates.sort(key=lambda t: t[0])
        return candidates[0][1]
    return None


def _door_h(
    fid_gen,
    hinge_x: float,
    hinge_y: float,
    dw: float,
    swing: int,   # +1 = opens north (↑), -1 = opens south (↓)
    uid: str,
    dtype: str,
) -> List[Dict]:
    """
    Door on a horizontal wall (wall runs E-W).
    Panel extends east from hinge. Arc sweeps into the room on the swing side.

    Geometry note (Y-up math, 0°=east CCW):
      swing=-1 (south): arc from 0° to  -90° (CW in math)
      swing=+1 (north): arc from 0° to  +90° (CCW in math)
    """
    py = hinge_y - DOOR_PANEL_T / 2
    panel = _make_feature(
        fid_gen(), "door",
        _rect_poly(hinge_x, py, dw, DOOR_PANEL_T),
        {"layer": "door", "unit_id": uid,
         "door_type": dtype, "door_width": round(dw, 2),
         # opening metadata consumed by door_opening layer:
         "opening_x": round(hinge_x, 3), "opening_y": round(hinge_y, 3),
         "opening_w": round(dw, 3), "opening_axis": "H"},
    )
    arc_start = 0.0
    arc_end   = 90.0 * swing
    arc = _make_feature(
        fid_gen(), "door_arc",
        _arc_poly(hinge_x, hinge_y, dw, arc_start, arc_end),
        {"layer": "door_arc", "unit_id": uid,
         # exact arc params for smooth SVG rendering:
         "arc_cx": round(hinge_x, 3), "arc_cy": round(hinge_y, 3),
         "arc_r": round(dw, 3),
         "arc_start": arc_start, "arc_end": arc_end},
    )
    return [panel, arc]


def _door_v(
    fid_gen,
    hinge_x: float,
    hinge_y: float,
    dw: float,
    swing: int,   # +1 = opens east (→), -1 = opens west (←)
    uid: str,
    dtype: str,
) -> List[Dict]:
    """
    Door on a vertical wall (wall runs N-S).
    Panel extends north from hinge.  Arc sweeps east or west.

    Geometry note (Y-up math, 0°=east CCW):
      swing=+1 (east): arc from 90° to   0° (CW in math)
      swing=-1 (west): arc from 90° to 180° (CCW in math)
    """
    px = hinge_x - DOOR_PANEL_T / 2
    panel = _make_feature(
        fid_gen(), "door",
        _rect_poly(px, hinge_y, DOOR_PANEL_T, dw),
        {"layer": "door", "unit_id": uid,
         "door_type": dtype, "door_width": round(dw, 2),
         "opening_x": round(hinge_x, 3), "opening_y": round(hinge_y, 3),
         "opening_w": round(dw, 3), "opening_axis": "V"},
    )
    arc_start = 90.0
    arc_end   = 0.0 if swing > 0 else 180.0
    arc = _make_feature(
        fid_gen(), "door_arc",
        _arc_poly(hinge_x, hinge_y, dw, arc_start, arc_end),
        {"layer": "door_arc", "unit_id": uid,
         "arc_cx": round(hinge_x, 3), "arc_cy": round(hinge_y, 3),
         "arc_r": round(dw, 3),
         "arc_start": arc_start, "arc_end": arc_end},
    )
    return [panel, arc]


def _arc_poly(
    cx: float, cy: float, r: float,
    start_deg: float, end_deg: float,
    n: int = DOOR_ARC_SEGS,
) -> Dict:
    """
    Filled sector polygon (fan) from start_deg to end_deg.
    Angles in degrees; 0° = east, 90° = north (standard math convention, Y-up).
    """
    pts = [[cx, cy]]
    for i in range(n + 1):
        t = math.radians(start_deg + (end_deg - start_deg) * i / n)
        pts.append([cx + r * math.cos(t), cy + r * math.sin(t)])
    pts.append([cx, cy])
    return {"type": "Polygon", "coordinates": [pts]}


# ============================================================================
# Door openings (white gap painted over walls at every door position)
# ============================================================================

def _door_openings(
    fid_gen,
    door_feats: List[Dict],
    ux: float, uy: float, uw: float, uh: float,
    side: str,
) -> List[Dict]:
    """
    Generate a white "door_opening" rectangle for every door panel.
    These are rendered after walls to create a visual gap/opening.

    The opening rectangle covers the door width plus a little extra (for wall
    thickness) and spans the full wall thickness.
    """
    openings: List[Dict] = []
    WALL_EXTRA = 0.05   # slight extension beyond door width

    for feat in door_feats:
        p = feat.get("properties", {})
        if p.get("layer") != "door":
            continue
        ox = p.get("opening_x")
        oy = p.get("opening_y")
        ow = p.get("opening_w")
        ax = p.get("opening_axis")
        if ox is None or ow is None:
            continue

        if ax == "H":
            # Horizontal wall — opening is a horizontal band
            t = WALL_EXT + WALL_EXTRA
            openings.append(_make_feature(
                fid_gen(), "door_opening",
                _rect_poly(ox - WALL_EXTRA / 2, oy - t / 2,
                            ow + WALL_EXTRA, t),
                {"layer": "door_opening"},
            ))
        else:
            # Vertical wall — opening is a vertical band
            t = WALL_INT + WALL_EXTRA
            openings.append(_make_feature(
                fid_gen(), "door_opening",
                _rect_poly(ox - t / 2, oy - WALL_EXTRA / 2,
                            t, ow + WALL_EXTRA),
                {"layer": "door_opening"},
            ))
    return openings


# ============================================================================
# Window placement (deterministic, based on exterior wall detection)
# ============================================================================

def _unit_windows(
    fid_gen,
    rooms: List[Dict],
    uid: str,
    floor_w: float,
    floor_d: float,
) -> List[Dict]:
    """Auto-place windows on exterior walls of every room."""
    windows: List[Dict] = []
    for room in rooms:
        rtype = room.get("type", "living").lower()
        rx, ry, rw, rh = room["x"], room["y"], room["w"], room["h"]
        target_w = _WIN_W.get(rtype, 1.0)
        if target_w == 0:
            continue
        for wall in _exterior_walls(rx, ry, rw, rh, floor_w, floor_d):
            windows.extend(_windows_on_wall(
                fid_gen, rx, ry, rw, rh, wall, target_w, uid, rtype.upper(),
            ))
    return windows


def _exterior_walls(
    rx: float, ry: float, rw: float, rh: float,
    floor_w: float, floor_d: float,
    tol: float = 0.20,
) -> List[str]:
    """Return the wall names that face the building exterior."""
    walls: List[str] = []
    if ry < tol:              walls.append("south")
    if ry + rh > floor_d - tol: walls.append("north")
    if rx < tol:              walls.append("west")
    if rx + rw > floor_w - tol: walls.append("east")
    return walls


def _windows_on_wall(
    fid_gen,
    rx: float, ry: float, rw: float, rh: float,
    wall: str,
    win_w_target: float,
    uid: str,
    rtype: str,
) -> List[Dict]:
    """Place 1-3 evenly spaced windows on a wall."""
    wall_len = rw if wall in ("south", "north") else rh
    win_w = min(win_w_target, wall_len * 0.55)
    if win_w < 0.30:
        return []

    # Number of windows: 1 per ~2.5 m of wall, capped at 3
    n = max(1, min(3, int(wall_len / 2.5)))
    total_glass = n * win_w
    if total_glass > wall_len * 0.85:
        win_w = wall_len * 0.85 / n
    spacing = (wall_len - n * win_w) / (n + 1)

    results: List[Dict] = []
    for i in range(n):
        offset = spacing * (i + 1) + win_w * i
        feat = _single_window(fid_gen, rx, ry, rw, rh, wall, offset, win_w, uid, rtype)
        if feat:
            results.append(feat)
    return results


def _single_window(
    fid_gen,
    rx: float, ry: float, rw: float, rh: float,
    wall: str, offset: float, win_w: float,
    uid: str, rtype: str,
) -> Optional[Dict]:
    if wall == "south":
        wx, wy, ww, wh = rx + offset, ry, win_w, WINDOW_DEPTH
    elif wall == "north":
        wx, wy, ww, wh = rx + offset, ry + rh - WINDOW_DEPTH, win_w, WINDOW_DEPTH
    elif wall == "west":
        wx, wy, ww, wh = rx, ry + offset, WINDOW_DEPTH, win_w
    elif wall == "east":
        wx, wy, ww, wh = rx + rw - WINDOW_DEPTH, ry + offset, WINDOW_DEPTH, win_w
    else:
        return None

    return _make_feature(
        fid_gen(), "window",
        _rect_poly(wx, wy, ww, wh),
        {"layer": "window",
         "unit_id": uid,
         "room_type": rtype,
         "window_width": round(win_w, 2),
         "wall": wall},
    )


# ============================================================================
# Staircase tread lines and lift door indicator
# ============================================================================

_TREAD_DEPTH = 0.28   # standard tread depth 280 mm


def _stair_treads(
    fid_gen,
    sx: float, sy: float, sw: float, sh: float,
) -> List[Dict]:
    """
    Generate horizontal tread lines inside a staircase bounding box.

    The flight runs along the depth (Y) axis.  A diagonal arrow line is added
    to show the ascent direction (bottom → top of box).
    Each tread is a thin LineString-style rectangle (2 mm thick) spanning the
    stair width.
    """
    TREAD_T = 0.02   # visual thickness of tread line in metres
    feats: List[Dict] = []
    n_treads = max(2, int(sh / _TREAD_DEPTH))
    step = sh / n_treads

    for i in range(1, n_treads):
        ty = sy + i * step
        feats.append(_make_feature(
            fid_gen(), "stair_tread",
            _rect_poly(sx, ty - TREAD_T / 2, sw, TREAD_T),
            {"layer": "stair_tread"},
        ))

    # Arrow: diagonal line from (sx + 0.15, sy + 0.15) to (sx + sw - 0.15, sy + sh - 0.15)
    arrow_pts = [
        [sx + 0.15, sy + 0.15],
        [sx + sw - 0.15, sy + sh - 0.15],
        [sx + sw - 0.15, sy + sh - 0.15],   # duplicate end for arrowhead base
    ]
    feats.append(_make_feature(
        fid_gen(), "stair_arrow",
        {"type": "LineString", "coordinates": arrow_pts},
        {"layer": "stair_arrow"},
    ))
    return feats


def _lift_door_indicator(
    fid_gen,
    lx: float, ly: float, lw: float, lh: float,
) -> List[Dict]:
    """
    Add a thin line on the south face of the lift shaft to indicate the door.
    Also adds two small vertical lines at the door edges (door-jam marks).
    """
    DOOR_T = 0.03
    # Full-width opening line at the south face
    feats = [
        _make_feature(
            fid_gen(), "lift_door",
            _rect_poly(lx, ly, lw, DOOR_T),
            {"layer": "lift_door"},
        ),
    ]
    return feats


# ============================================================================
# Balcony walls (parapet + side cheeks + sliding-door opening in exterior wall)
# ============================================================================

def _balcony_walls(
    fid_gen,
    bx: float, by: float, bw: float, bh: float,
    ux: float, uy: float, uw: float, uh: float,
    side: str,
    uid: str,
) -> List[Dict]:
    """
    Generate thin parapet / cheek walls around a balcony projection and a
    wide sliding-door opening in the unit's exterior wall.

    South unit: balcony is below the unit (by = uy - bh).
      - Parapet: south face of balcony  (y = by)
      - Cheeks:  east and west sides of balcony
      - Opening: gap in the south wall of the unit at the balcony width

    North unit: balcony is above the unit (by = uy + uh).
      - Parapet: north face of balcony  (y = by + bh - tp)
      - Cheeks:  east and west sides of balcony
      - Opening: gap in the north wall of the unit at the balcony width
    """
    walls: List[Dict] = []
    tp = 0.115   # parapet / cheek thickness (thin 115 mm wall)

    # ── Parapet (front face) ──────────────────────────────────────────────────
    if side == "south":
        walls.append(_wall_feat(fid_gen(), bx, by, bw, tp, uid, "parapet"))
    else:
        walls.append(_wall_feat(fid_gen(), bx, by + bh - tp, bw, tp, uid, "parapet"))

    # ── Cheeks (side walls) ───────────────────────────────────────────────────
    walls.append(_wall_feat(fid_gen(), bx, by, tp, bh, uid, "parapet"))           # west cheek
    walls.append(_wall_feat(fid_gen(), bx + bw - tp, by, tp, bh, uid, "parapet")) # east cheek

    # ── Sliding-door opening in the unit exterior wall ────────────────────────
    # The opening is centred on the balcony width; it is as wide as the balcony
    # (minus cheek thickness on each side) and spans the full wall thickness.
    WALL_EXTRA = 0.05
    open_x = bx + tp
    open_w = bw - 2 * tp
    te = WALL_EXT

    if side == "south":
        # South wall of unit sits at y = uy
        walls.append(_make_feature(
            fid_gen(), "door_opening",
            _rect_poly(open_x - WALL_EXTRA / 2, uy - te / 2,
                       open_w + WALL_EXTRA, te + WALL_EXTRA),
            {"layer": "door_opening", "unit_id": uid, "opening_type": "sliding"},
        ))
    else:
        # North wall of unit sits at y = uy + uh - te
        walls.append(_make_feature(
            fid_gen(), "door_opening",
            _rect_poly(open_x - WALL_EXTRA / 2, uy + uh - te / 2,
                       open_w + WALL_EXTRA, te + WALL_EXTRA),
            {"layer": "door_opening", "unit_id": uid, "opening_type": "sliding"},
        ))

    return walls


# ============================================================================
# Perimeter walls
# ============================================================================

def _unit_perimeter_walls(
    fid_gen,
    ux: float, uy: float, uw: float, uh: float,
    uid: str, side: str,
) -> List[Dict]:
    """External perimeter walls for a unit (thick rectangles)."""
    walls: List[Dict] = []
    te = WALL_EXT
    ti = WALL_INT

    if side == "south":
        walls.append(_wall_feat(fid_gen(), ux, uy,          uw, te, uid, "external"))  # south
        walls.append(_wall_feat(fid_gen(), ux, uy + uh - ti, uw, ti, uid, "entry"))    # north (corridor)
        walls.append(_wall_feat(fid_gen(), ux + uw - te, uy, te, uh, uid, "external")) # east
        walls.append(_wall_feat(fid_gen(), ux, uy,          te, uh, uid, "external"))  # west
    else:  # north unit
        walls.append(_wall_feat(fid_gen(), ux, uy + uh - te, uw, te, uid, "external")) # north
        walls.append(_wall_feat(fid_gen(), ux, uy,           uw, ti, uid, "entry"))    # south (corridor)
        walls.append(_wall_feat(fid_gen(), ux + uw - te, uy, te, uh, uid, "external")) # east
        walls.append(_wall_feat(fid_gen(), ux, uy,           te, uh, uid, "external")) # west
    return walls


# ============================================================================
# Primitive helpers
# ============================================================================

def _rect_poly(x: float, y: float, w: float, h: float) -> Dict:
    coords = [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]
    return {"type": "Polygon", "coordinates": [coords]}


def _make_feature(
    fid: str, layer: str,
    geometry: Dict,
    properties: Dict[str, Any],
) -> Dict[str, Any]:
    return {"type": "Feature", "id": fid, "geometry": geometry,
            "properties": properties}


def _wall_feat(
    fid: str,
    x: float, y: float, w: float, h: float,
    uid: str, wall_type: str,
) -> Dict[str, Any]:
    return _make_feature(
        fid, "wall",
        _rect_poly(x, y, w, h),
        {"layer": "wall", "unit_id": uid,
         "wall_type": wall_type,
         "thickness_m": round(min(w, h), 3)},
    )


class _IdGen:
    def __init__(self) -> None:
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"ai-fp-{self._n}"
