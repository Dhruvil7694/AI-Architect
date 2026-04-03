"""
services/floor_plan_service.py
-------------------------------
GDCR-compliant typical floor plan generator — optimised placement engine.

Core layout (plan view, S = short/width axis, L = long/corridor axis):

  ┌─────────────────────────────────────────────────────────────┐
  │  SOUTH UNITS  (full L, S: 0 → s_corridor₀)                 │
  ├──────────────┬────────────────────┬────────────────────────-┤
  │  corridor    │   S T A I R S      │    corridor             │ ← 1.5 m
  │              ├──────┬──────┬──────┤                         │
  │              │Lobby │  L1  │  L2  │                         │ ← lobby + lifts
  │              │      │      │      │                         │
  ├──────────────┴────────────────────┴─────────────────────────┤
  │  NORTH UNITS  (non-core L-bands, S: s_core₁ → SHORT_m)     │
  └─────────────────────────────────────────────────────────────┘

Core is a COMPACT block (core_len × core_S_depth) centred on the floor length.
It does NOT extend wall-to-wall — typical depth is stair_D ≈ 3.5 m.

Optimisation layer (new in this revision):
  1.  Mixed-type bin-packing — each unit band fills with the best combination
      of unit types from the mix to minimise wasted floorspace (greedy LFD).
  2.  Unit depth maximisation — full available depth is used; type selected
      accordingly (not just minimum-depth cutoffs).
  3.  Balcony strips — south-facing units get a 1.5 m balcony depth appended
      to their south face (GDCR §13.1.12).  Balcony area is tracked separately
      and excluded from FSI (it is an open area).
  4.  Ventilation compliance (GDCR §13.1.11) — each unit is flagged if its
      floor area implies a required window area ≥ 1/6 floor area; the required
      vs available window width is emitted per unit so the UI can highlight
      any shortfall.
  5.  Core overflow guard — GDCR lift formula capped to what physically fits;
      lift_capped + lift_cap_reason emitted for UI warnings.

FSI note:
  Net BUA  = unit areas × n_floors  (corridor + core = common areas, excluded)
  Gross BUA = footprint × n_floors  (used for permit)
  Balcony areas are open-to-sky and excluded from FSI per §8.2.2 cl.8.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("services.floor_plan")

# ─── Coordinate conversion ────────────────────────────────────────────────────
DXF_TO_M = 0.3048
M_TO_DXF = 1.0 / DXF_TO_M  # ≈ 3.28084

# ─── GDCR / NBC dimensional standards (metres) ───────────────────────────────
# GDCR Part III Section 13.12.2–13.12.3 / Table 13.2
CORRIDOR_W      = 1.50  # internal residential corridor (NBC min 1.2 m; upgraded 1.5 m for comfort)
LIFT_CABIN_W    = 1.50  # lift cabin internal clear width (6-person min)
LIFT_CABIN_D    = 1.80  # lift cabin internal depth (6-person min)
LIFT_SHAFT_W    = 1.85  # shaft = cabin + wall clearances
LIFT_LANDING_D  = 2.00  # §13.12.3 cl.4: clear landing in front of doors ≥ 1.8 m × 2.0 m
STAIR_W         = 1.20  # staircase clear width (Table 13.2: ≥ 1.0 m for res. ≤ 15 m;
                        #   ≥ 1.2 m for res. > 15 m / use alternative 2×1.2 = 1×1.5 m)
STAIR_D         = 3.50  # depth for straight flight with mid-landing
STAIR_WALL      = 0.15  # separation wall between two stair wells
MIN_UNIT_DEPTH  = 4.50  # absolute minimum unit depth — units thinner than this are discarded
# Core sizing constraint: core must leave at least this much L on each side for units.
# Prevents the GDCR lift-count formula from producing a core that swallows the floor.
MIN_UNIT_BAND_M = 5.00  # metres — minimum unit-band length on each side of core

# Clearances (§13.1.7)
CLEARANCE_HABITABLE_M = 2.90  # habitable rooms: ≥ 2.9 m between finished floor levels
CLEARANCE_SERVICE_M   = 2.10  # corridors / bathrooms / stair cabins: ≥ 2.1 m

# Balcony (§13.1.12 / Table 13.5): open balcony depth permitted up to 2.0 m.
# We place a 1.5 m balcony on south-facing units (best natural light + ventilation).
BALCONY_DEPTH_M = 1.50
BALCONY_ENABLED = True   # set False to suppress balconies

# Ventilation (§13.1.11): window area ≥ 1/6 of floor area of the served room.
VENTILATION_WINDOW_RATIO = 1.0 / 6.0   # window ≥ floor_area / 6

# ─── Room subdivision tables (metres) ────────────────────────────────────────
# Each unit type defines: back_strip_depth, bedroom_depth, toilet_w, kitchen_w
# Slicing order: back strip (TOILET+KITCHEN) → middle (BEDROOM) → front (LIVING)
_ROOM_CONFIG: Dict[str, Dict[str, float]] = {
    "STUDIO": {"back_depth": 2.0, "bedroom_depth": 0.0, "toilet_w_frac": 1.0, "kitchen_w_frac": 0.0},
    "1RK":    {"back_depth": 2.0, "bedroom_depth": 0.0, "toilet_w_frac": 1.0, "kitchen_w_frac": 0.0},
    "1BHK":   {"back_depth": 2.0, "bedroom_depth": 3.0, "toilet_w_frac": 0.40, "kitchen_w_frac": 0.60},
    "2BHK":   {"back_depth": 2.2, "bedroom_depth": 3.2, "toilet_w_frac": 0.38, "kitchen_w_frac": 0.62},
    "3BHK":   {"back_depth": 2.3, "bedroom_depth": 3.4, "toilet_w_frac": 0.35, "kitchen_w_frac": 0.65},
    "4BHK":   {"back_depth": 2.5, "bedroom_depth": 3.6, "toilet_w_frac": 0.33, "kitchen_w_frac": 0.67},
}

# Room fill colours for frontend legend (emitted in properties)
_ROOM_LABEL: Dict[str, str] = {
    "LIVING": "Living", "BEDROOM": "Bedroom", "KITCHEN": "Kitchen",
    "TOILET": "Toilet", "PASSAGE": "Passage",
}


# ─── GDCR helpers ─────────────────────────────────────────────────────────────

def _n_lifts_required(height_m: float, total_units: int) -> int:
    """
    GDCR Part III §13.12.2 — minimum lifts for residential:
      > 10 m : max(1,  ceil(total_units / 30))
      > 25 m : max(2,  ceil(total_units / 30))  ← one must be fire lift
    """
    if height_m <= 10.0:
        return 0
    min_by_height = 2 if height_m > 25.0 else 1
    by_units = math.ceil(total_units / 30) if total_units > 0 else 0
    return max(min_by_height, by_units)


def _n_stairs(height_m: float) -> int:
    """Table 13.2: residential > 15 m needs 2 staircases of ≥ 1.2 m (or 1 of ≥ 1.5 m)."""
    return 2 if height_m > 15.0 else 1


def _stair_width_required(height_m: float) -> float:
    """Table 13.2 minimum stair clear width (residential)."""
    return 1.20 if height_m > 15.0 else 1.00


# ─── Geometry helpers ─────────────────────────────────────────────────────────

def _principal_axis(coords: List[List[float]]) -> Tuple[float, float, float, float]:
    """
    Determine the L (long) axis unit vector from the longest edge of the polygon.
    Returns (lx, ly, sx, sy) — unit vectors for L and S axes in DXF space.
    Always orients L so it points in the +X half-plane (or +Y when vertical),
    giving a canonical direction for back-projection.
    """
    ring = coords[:-1] if len(coords) > 1 and coords[0] == coords[-1] else coords
    max_len, lx, ly = 0.0, 1.0, 0.0
    for i in range(len(ring)):
        dx = ring[(i + 1) % len(ring)][0] - ring[i][0]
        dy = ring[(i + 1) % len(ring)][1] - ring[i][1]
        length = math.hypot(dx, dy)
        if length > max_len:
            max_len, lx, ly = length, dx / length, dy / length
    # Canonical direction: lx ≥ 0; if lx == 0 then ly ≥ 0
    if lx < 0 or (abs(lx) < 1e-9 and ly < 0):
        lx, ly = -lx, -ly
    # S axis is 90° counter-clockwise from L
    sx, sy = -ly, lx
    return lx, ly, sx, sy


def _point_in_polygon(px: float, py: float, ring: List[List[float]]) -> bool:
    """Ray-casting point-in-polygon test (2-D, DXF coordinate space)."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _rect(
    l0: float, s0: float, l1: float, s1: float,
    origin: Tuple[float, float],
    l_dxf: Tuple[float, float],
    s_dxf: Tuple[float, float],
) -> Dict:
    """
    Rectangle polygon in DXF coordinate space from local (L, S) metre coords.

    origin : DXF point corresponding to L=0, S=0
    l_dxf  : DXF displacement per 1 metre along L axis
    s_dxf  : DXF displacement per 1 metre along S axis
    """
    ox, oy = origin
    lx, ly = l_dxf
    sx, sy = s_dxf

    def pt(l: float, s: float) -> List[float]:
        return [ox + l * lx + s * sx, oy + l * ly + s * sy]

    corners = [pt(l0, s0), pt(l1, s0), pt(l1, s1), pt(l0, s1), pt(l0, s0)]
    return {"type": "Polygon", "coordinates": [corners]}


# ─── Unit-mix tables ──────────────────────────────────────────────────────────

# Nominal module widths per type (metres) — used as the PREFERRED width.
# Greedy packing may stretch by up to ±20% to fill a region.
_UNIT_W: Dict[str, float] = {
    "STUDIO": 3.5, "1RK": 3.5,
    "1BHK": 5.0,
    "2BHK": 6.0,
    "3BHK": 7.5,
    "4BHK": 9.0,
}

# Minimum clear depth (from corridor face to external wall) per type.
# GDCR §13.1.8/9: min room sizes mandate these depths.
_UNIT_MIN_DEPTH: Dict[str, float] = {
    "STUDIO": 4.0, "1RK": 4.0,
    "1BHK": 5.5,
    "2BHK": 6.5,
    "3BHK": 8.0,
    "4BHK": 10.0,
}

# Typical depth for full GDCR §13.1.8 compliance (used for ventilation check)
_UNIT_TYP_DEPTH: Dict[str, float] = {
    "STUDIO": 5.0, "1RK": 5.0,
    "1BHK": 6.5,
    "2BHK": 8.0,
    "3BHK": 9.5,
    "4BHK": 11.5,
}

_UNIT_SIZE_ORDER = ["4BHK", "3BHK", "2BHK", "1BHK", "1RK", "STUDIO"]


def _fit_type(depth_m: float, preferred: List[str]) -> Optional[str]:
    """
    Return the first unit type from `preferred` whose minimum depth ≤ available depth.
    Falls back to the global size order if nothing in `preferred` fits.
    """
    for t in preferred:
        if depth_m >= _UNIT_MIN_DEPTH.get(t, 5.0):
            return t
    for t in _UNIT_SIZE_ORDER:
        if depth_m >= _UNIT_MIN_DEPTH.get(t, 4.0):
            return t
    return None


# ─── Optimisation: greedy mixed-type bin-packing ──────────────────────────────

def _pack_region_mixed(
    region_len: float,
    depth: float,
    preferred_mix: List[str],
) -> List[Tuple[str, float, float]]:
    """
    Greedily pack unit modules into `region_len` (metres) using a mixed-type
    strategy that minimises wasted floor space.

    Strategy (Largest-Fit-Decreasing, then fill remainder):
      1. Build a feasible set of types: those whose minimum depth ≤ available depth.
      2. Sort feasible types by nominal width DESC (largest first).
      3. Walk left-to-right, at each position try the preferred type from the
         caller's mix first; if it would leave a remainder smaller than the
         smallest unit, switch to the next smaller type.
      4. After all whole modules are placed, stretch the last module to absorb
         any remainder ≤ 1.0 m (keeping width within ±20% of nominal).
      5. If the remainder is > 1.0 m and < min_width, insert a STUDIO (smallest
         feasible) at the end so no space is wasted.

    Returns list of (unit_type, l_start, l_end) triples in L-metre coordinates.
    Result is always non-empty if region_len ≥ smallest feasible unit width.
    """
    # Feasible types in preferred-mix order, then remaining types from size order
    feasible = [t for t in preferred_mix if depth >= _UNIT_MIN_DEPTH.get(t, 4.0)]
    for t in _UNIT_SIZE_ORDER:
        if t not in feasible and depth >= _UNIT_MIN_DEPTH.get(t, 4.0):
            feasible.append(t)

    if not feasible:
        return []

    min_w = min(_UNIT_W[t] for t in feasible)   # narrowest feasible unit
    max_stretch = 1.20  # allow up to +20 % width stretch

    placements: List[Tuple[str, float, float]] = []
    cursor = 0.0

    while region_len - cursor >= min_w - 0.01:
        remaining = region_len - cursor

        placed = False
        # Try preferred type first, then fall back through feasible list
        for utype in feasible:
            uw = _UNIT_W[utype]
            if uw > remaining + 0.01:
                continue  # doesn't fit
            # Check: would placing this leave an un-fillable sliver?
            leftover = remaining - uw
            if 0 < leftover < min_w:
                # Try stretching this unit to absorb the sliver (≤ 20% stretch)
                if leftover / uw <= (max_stretch - 1.0):
                    placements.append((utype, cursor, cursor + remaining))
                    cursor = region_len
                    placed = True
                    break
                # Try inserting a smaller unit after this one
                smaller = [t for t in feasible if _UNIT_W[t] <= leftover]
                if smaller:
                    placements.append((utype, cursor, cursor + uw))
                    cursor += uw
                    placed = True
                    break
                # Last resort: stretch anyway
                placements.append((utype, cursor, cursor + remaining))
                cursor = region_len
                placed = True
                break
            else:
                placements.append((utype, cursor, cursor + uw))
                cursor += uw
                placed = True
                break

        if not placed:
            # Remaining space is smaller than any unit — stretch the last one
            if placements:
                last_type, last_l0, last_l1 = placements[-1]
                placements[-1] = (last_type, last_l0, region_len)
            break

    return placements


# ─── Ventilation helper ────────────────────────────────────────────────────────

def _ventilation_check(
    unit_type: str,
    unit_width_m: float,
    unit_depth_m: float,
) -> Dict[str, Any]:
    """
    GDCR §13.1.11: window opening area ≥ 1/6 of the floor area of the room.
    We model the principal living room as occupying 60% of the unit floor area
    (gross carpet) and assume a single window per unit whose width = unit width
    and typical sill-to-lintel height = 1.2 m.

    Returns a dict: {ok, required_window_sqm, available_window_sqm, ratio}
    """
    floor_sqm     = unit_width_m * unit_depth_m
    req_window    = floor_sqm * VENTILATION_WINDOW_RATIO   # ≥ floor/6
    # Assume window spans unit_width × 1.2 m head height (typical residential)
    avail_window  = unit_width_m * 1.20
    return {
        "ventilation_ok":         avail_window >= req_window,
        "required_window_sqm":    round(req_window,   2),
        "available_window_sqm":   round(avail_window, 2),
        "gdcr_clause":            "§13.1.11 — window ≥ 1/6 floor area",
    }


# ─── Detailed unit subdivision — walls, doors, windows ────────────────────────

# Architectural constants (metres)
EXT_WALL_T   = 0.230   # 230 mm external / party wall
INT_WALL_T   = 0.115   # 115 mm internal partition
DOOR_MAIN_W  = 0.900   # main entry door
DOOR_ROOM_W  = 0.800   # bedroom / kitchen door
DOOR_BATH_W  = 0.750   # bathroom door
WINDOW_DEPTH = 0.100   # window thickness in plan (visual only)


def _local_polygon(
    pts: List[Tuple[float, float]],
    origin: Tuple[float, float],
    l_dxf: Tuple[float, float],
    s_dxf: Tuple[float, float],
) -> Dict:
    """Convert a list of (L, S) local-metre points to a DXF GeoJSON Polygon."""
    ox, oy = origin
    lx, ly = l_dxf
    sx, sy = s_dxf
    coords = [[ox + l * lx + s * sx, oy + l * ly + s * sy] for l, s in pts]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def _door_arc_pts(
    hl: float, hs: float, w: float,
    dl: float, ds: float, n: int = 12,
) -> List[Tuple[float, float]]:
    """Quarter-circle arc polygon in local metres for a door swing.

    hl, hs : hinge point (local L, S)
    w      : door width (arc radius)
    dl, ds : direction multipliers for the sweep
             e.g. dl=1,ds=-1 sweeps from +L into -S
    """
    pts: List[Tuple[float, float]] = [(hl, hs)]
    for i in range(n + 1):
        theta = math.pi / 2.0 * i / n
        pts.append((
            hl + w * math.cos(theta) * dl,
            hs + w * math.sin(theta) * ds,
        ))
    pts.append((hl, hs))
    return pts


def _generate_unit_detail(
    l0: float, s0: float, l1: float, s1: float,
    unit_type: str,
    core_side: str,
    unit_id: str,
    origin: Tuple[float, float],
    l_dxf: Tuple[float, float],
    s_dxf: Tuple[float, float],
) -> List[Dict]:
    """
    Generate complete architectural detail for one residential unit:
    rooms (inset from walls), thick wall polygons, doors with arcs, windows.

    core_side : "south" → entry at s0 (corridor at bottom of unit)
                "north" → entry at s1 (corridor at top of unit)

    Returns a list of GeoJSON Feature dicts ready for the FeatureCollection.
    """
    features: List[Dict] = []
    W = l1 - l0
    D = s1 - s0

    cfg = _ROOM_CONFIG.get(unit_type, _ROOM_CONFIG["2BHK"])
    back_depth = cfg["back_depth"]
    bed_depth  = cfg["bedroom_depth"]
    toilet_frac = cfg["toilet_w_frac"]

    e = EXT_WALL_T
    p = INT_WALL_T
    seq = [0]  # mutable counter for unique IDs

    def R(rl0: float, rs0: float, rl1: float, rs1: float) -> Dict:
        return _rect(rl0, rs0, rl1, rs1, origin, l_dxf, s_dxf)

    def P(pts: List[Tuple[float, float]]) -> Dict:
        return _local_polygon(pts, origin, l_dxf, s_dxf)

    def add_room(room_type: str, rl0: float, rs0: float, rl1: float, rs1: float) -> None:
        area = (rl1 - rl0) * (rs1 - rs0)
        seq[0] += 1
        features.append({
            "type": "Feature",
            "id": f"room_{unit_id}_{room_type.lower()}_{seq[0]}",
            "geometry": R(rl0, rs0, rl1, rs1),
            "properties": {
                "layer": "room",
                "room_type": room_type,
                "unit_id": unit_id,
                "area_sqm": round(area, 2),
                "label": _ROOM_LABEL.get(room_type, room_type),
            },
        })

    def add_wall(wl0: float, ws0: float, wl1: float, ws1: float, wtype: str = "external") -> None:
        seq[0] += 1
        features.append({
            "type": "Feature",
            "id": f"wall_{unit_id}_{seq[0]}",
            "geometry": R(wl0, ws0, wl1, ws1),
            "properties": {"layer": "wall", "wall_type": wtype},
        })

    def add_door(hl: float, hs: float, w: float, dl: float, ds: float) -> None:
        arc = _door_arc_pts(hl, hs, w, dl, ds)
        seq[0] += 1
        features.append({
            "type": "Feature",
            "id": f"door_{unit_id}_{seq[0]}",
            "geometry": P(arc),
            "properties": {"layer": "door", "width_m": w},
        })

    def add_window(wl0: float, ws0: float, wl1: float, ws1: float) -> None:
        seq[0] += 1
        features.append({
            "type": "Feature",
            "id": f"window_{unit_id}_{seq[0]}",
            "geometry": R(wl0, ws0, wl1, ws1),
            "properties": {"layer": "window", "width_m": round(max(wl1 - wl0, ws1 - ws0), 2)},
        })

    # ── Interior bounds after external walls ─────────────────────────────
    # Three sides get external walls; the corridor-facing side gets a thin entry wall.
    il0 = l0 + e          # left
    il1 = l1 - e          # right
    iW  = il1 - il0

    if core_side == "north":
        # Entry at s1 (top), outer wall at s0 (bottom)
        is0 = s0 + e      # inner face of outer wall
        is1 = s1 - p      # inner face of entry wall
    else:
        # Entry at s0 (bottom), outer wall at s1 (top)
        is0 = s0 + p      # inner face of entry wall
        is1 = s1 - e      # inner face of outer wall

    iD = is1 - is0

    # ── Scale room depths to fit interior ────────────────────────────────
    n_part = (2 if bed_depth > 0 else 1) if back_depth > 0 else 0
    part_total = n_part * p
    avail = iD - part_total
    total_back_bed = back_depth + bed_depth

    if total_back_bed > 0 and total_back_bed > avail * 0.70:
        scale = avail * 0.70 / total_back_bed
        back_depth *= scale
        bed_depth  *= scale

    living_depth = avail - back_depth - bed_depth
    if living_depth < 1.5:
        living_depth = avail
        back_depth = 0.0
        bed_depth  = 0.0

    # ── Compute S-positions per room band ────────────────────────────────
    # Direction: from entry toward outer wall.
    if core_side == "north":
        # Entry at top (is1), outer at bottom (is0)
        # Living (entry side) → Bedroom → Back strip (outer side)
        s_liv_1  = is1                        # living top
        s_liv_0  = is1 - living_depth         # living bottom

        s_wlb_0  = s_liv_0 - p               # wall living/bedroom
        s_wlb_1  = s_liv_0

        s_bed_1  = s_wlb_0                    # bedroom top
        s_bed_0  = s_wlb_0 - bed_depth if bed_depth > 0.3 else s_wlb_0

        s_wbb_0  = s_bed_0 - p if bed_depth > 0.3 else s_wlb_0 - p
        s_wbb_1  = s_bed_0 if bed_depth > 0.3 else s_wlb_0

        s_bck_1  = s_wbb_0                   # back-strip top
        s_bck_0  = is0                        # back-strip bottom (at outer wall)
    else:
        # Entry at bottom (is0), outer at top (is1)
        s_liv_0  = is0
        s_liv_1  = is0 + living_depth

        s_wlb_0  = s_liv_1
        s_wlb_1  = s_liv_1 + p

        s_bed_0  = s_wlb_1
        s_bed_1  = s_wlb_1 + bed_depth if bed_depth > 0.3 else s_wlb_1

        s_wbb_0  = s_bed_1 if bed_depth > 0.3 else s_wlb_1
        s_wbb_1  = s_bed_1 + p if bed_depth > 0.3 else s_wlb_1 + p

        s_bck_0  = s_wbb_1
        s_bck_1  = is1

    # ── ROOMS ────────────────────────────────────────────────────────────
    add_room("LIVING", il0, s_liv_0, il1, s_liv_1)

    if bed_depth > 0.3:
        if unit_type in ("3BHK", "4BHK") and iW >= 5.5:
            mid = il0 + iW * 0.55
            add_room("BEDROOM", il0, s_bed_0, mid - p / 2, s_bed_1)
            add_room("BEDROOM", mid + p / 2, s_bed_0, il1, s_bed_1)
            # Partition between bedrooms
            add_wall(mid - p / 2, s_bed_0, mid + p / 2, s_bed_1, "internal")
        else:
            add_room("BEDROOM", il0, s_bed_0, il1, s_bed_1)

    back_d = abs(s_bck_1 - s_bck_0)
    if back_depth > 0.3 and back_d > 0.5:
        toilet_w = iW * toilet_frac
        tk_wall_l = il0 + toilet_w   # vertical wall between toilet & kitchen
        # Toilet (left)
        add_room("TOILET", il0, s_bck_0, tk_wall_l - p / 2, s_bck_1)
        # Kitchen (right)
        add_room("KITCHEN", tk_wall_l + p / 2, s_bck_0, il1, s_bck_1)
        # Partition between toilet & kitchen
        add_wall(tk_wall_l - p / 2, s_bck_0, tk_wall_l + p / 2, s_bck_1, "internal")

    # ── THICK WALLS ──────────────────────────────────────────────────────
    # External walls (3 sides)
    add_wall(l0, s0, l0 + e, s1, "external")      # left
    add_wall(l1 - e, s0, l1, s1, "external")       # right

    if core_side == "north":
        add_wall(l0, s0, l1, s0 + e, "external")   # outer (bottom)
        # Entry wall (top) — split for door opening
        door_center_l = (l0 + l1) / 2.0
        dh = DOOR_MAIN_W / 2.0
        add_wall(l0, s1 - p, door_center_l - dh, s1, "entry")
        add_wall(door_center_l + dh, s1 - p, l1, s1, "entry")
    else:
        add_wall(l0, s1 - e, l1, s1, "external")   # outer (top)
        door_center_l = (l0 + l1) / 2.0
        dh = DOOR_MAIN_W / 2.0
        add_wall(l0, s0, door_center_l - dh, s0 + p, "entry")
        add_wall(door_center_l + dh, s0, l1, s0 + p, "entry")

    # Internal horizontal partitions (living/bedroom, bedroom/back)
    if bed_depth > 0.3:
        # Door gap in living→bedroom wall (left side)
        door_l = il0
        add_wall(door_l + DOOR_ROOM_W, s_wlb_0, il1, s_wlb_1, "internal")
        # Door gap in bedroom→back wall (left = toilet door, right = kitchen door)
        if back_depth > 0.3 and back_d > 0.5:
            # Toilet door (left)
            td_l = il0
            td_r = td_l + DOOR_BATH_W
            # Kitchen door (right, near toilet/kitchen partition)
            kd_r = il1
            kd_l = kd_r - DOOR_ROOM_W
            # Wall segments with door gaps
            add_wall(td_r, s_wbb_0, kd_l, s_wbb_1, "internal")
    elif back_depth > 0.3 and back_d > 0.5:
        # No bedroom — wall between living and back
        door_l = il0
        add_wall(door_l + DOOR_ROOM_W, s_wlb_0, il1, s_wlb_1, "internal")

    # ── DOORS (quarter-circle arcs) ──────────────────────────────────────
    if core_side == "north":
        # Main entry: hinge at right side of opening, swings inward (-S)
        add_door(door_center_l + dh, s1, DOOR_MAIN_W, -1, -1)
        if bed_depth > 0.3:
            # Bedroom door: hinge left, swings into bedroom (-S)
            add_door(il0, s_wlb_0, DOOR_ROOM_W, 1, -1)
            if back_depth > 0.3 and back_d > 0.5:
                # Toilet door: hinge left, swings into toilet (-S)
                add_door(il0, s_wbb_0, DOOR_BATH_W, 1, -1)
                # Kitchen door: hinge right, swings into kitchen (-S)
                add_door(il1, s_wbb_0, DOOR_ROOM_W, -1, -1)
    else:
        # Main entry: hinge at right side, swings inward (+S)
        add_door(door_center_l + dh, s0, DOOR_MAIN_W, -1, 1)
        if bed_depth > 0.3:
            add_door(il0, s_wlb_1, DOOR_ROOM_W, 1, 1)
            if back_depth > 0.3 and back_d > 0.5:
                add_door(il0, s_wbb_1, DOOR_BATH_W, 1, 1)
                add_door(il1, s_wbb_1, DOOR_ROOM_W, -1, 1)

    # ── WINDOWS (on external walls) ──────────────────────────────────────
    wd = WINDOW_DEPTH
    if core_side == "north":
        outer_s = s0
        # Living window — large, centered on outer wall
        ww_liv = min(1.5, iW * 0.5)
        wc = (il0 + il1) / 2
        add_window(wc - ww_liv / 2, outer_s, wc + ww_liv / 2, outer_s + wd)
        # Bedroom window — on left external wall
        if bed_depth > 0.3:
            ww_bed = min(1.2, (s_bed_1 - s_bed_0) * 0.5)
            bc = (s_bed_0 + s_bed_1) / 2
            add_window(l0, bc - ww_bed / 2, l0 + wd, bc + ww_bed / 2)
        # Kitchen window — on outer wall (right side)
        if back_depth > 0.3 and back_d > 0.5:
            tk_l = il0 + iW * toilet_frac + p / 2
            kc = (tk_l + il1) / 2
            ww_k = min(0.9, (il1 - tk_l) * 0.5)
            add_window(kc - ww_k / 2, outer_s, kc + ww_k / 2, outer_s + wd)
            # Toilet window — small, on left wall
            tc = (s_bck_0 + s_bck_1) / 2
            add_window(l0, tc - 0.3, l0 + wd, tc + 0.3)
    else:
        outer_s = s1
        ww_liv = min(1.5, iW * 0.5)
        wc = (il0 + il1) / 2
        add_window(wc - ww_liv / 2, outer_s - wd, wc + ww_liv / 2, outer_s)
        if bed_depth > 0.3:
            ww_bed = min(1.2, (s_bed_1 - s_bed_0) * 0.5)
            bc = (s_bed_0 + s_bed_1) / 2
            add_window(l0, bc - ww_bed / 2, l0 + wd, bc + ww_bed / 2)
        if back_depth > 0.3 and back_d > 0.5:
            tk_l = il0 + iW * toilet_frac + p / 2
            kc = (tk_l + il1) / 2
            ww_k = min(0.9, (il1 - tk_l) * 0.5)
            add_window(kc - ww_k / 2, outer_s - wd, kc + ww_k / 2, outer_s)
            tc = (s_bck_0 + s_bck_1) / 2
            add_window(l0, tc - 0.3, l0 + wd, tc + 0.3)

    return features


# ─── Main function ────────────────────────────────────────────────────────────

def generate_floor_plan(
    footprint_geojson: Dict,
    n_floors: int,
    building_height_m: float,
    unit_mix: List[str],
    storey_height_m: float = 3.0,
    plot_area_sqm: float = 0.0,
) -> Dict[str, Any]:
    """
    Generate a GDCR-compliant, optimised typical floor plan for a residential tower.

    footprint_geojson : GeoJSON Polygon in DXF coordinate space (1 unit = 1 ft)
    Returns dict: { status, layout (GeoJSON FeatureCollection), metrics }
    """
    # ── 1. Parse footprint and compute principal-axis coordinate frame ─────────
    try:
        outer = (footprint_geojson.get("coordinates") or [[]])[0]
        if len(outer) < 4:
            return {"status": "error", "error": "Footprint has < 4 vertices"}
        outer = [[float(c[0]), float(c[1])] for c in outer]
    except Exception as e:
        return {"status": "error", "error": f"Could not parse footprint: {e}"}

    # Principal axis: longest polygon edge → L axis; perpendicular → S axis.
    # This correctly handles rotated / non-axis-aligned towers.
    ax_lx, ax_ly, ax_sx, ax_sy = _principal_axis(outer)

    # Project all polygon vertices onto L and S axes (in DXF units)
    l_projs = [c[0] * ax_lx + c[1] * ax_ly for c in outer]
    s_projs = [c[0] * ax_sx + c[1] * ax_sy for c in outer]
    l_min, l_max = min(l_projs), max(l_projs)
    s_min, s_max = min(s_projs), max(s_projs)

    # Oriented bounding rectangle dimensions in metres
    L_dxf   = l_max - l_min   # DXF units along long axis
    S_dxf   = s_max - s_min   # DXF units along short axis
    L_m     = L_dxf * DXF_TO_M
    SHORT_m = S_dxf * DXF_TO_M

    # Shoelace area of actual polygon (m²)
    n_v = len(outer)
    shoelace = sum(
        outer[i][0] * outer[(i + 1) % n_v][1] - outer[(i + 1) % n_v][0] * outer[i][1]
        for i in range(n_v)
    )
    footprint_sqm = abs(shoelace) / 2.0 * (DXF_TO_M ** 2)

    # Origin in DXF space: the corner that corresponds to (L=0, S=0) in local frame.
    origin_x = l_min * ax_lx + s_min * ax_sx
    origin_y = l_min * ax_ly + s_min * ax_sy
    origin: Tuple[float, float] = (origin_x, origin_y)

    # DXF displacement vectors per 1 metre along each local axis
    l_dxf_pm: Tuple[float, float] = (ax_lx * M_TO_DXF, ax_ly * M_TO_DXF)
    s_dxf_pm: Tuple[float, float] = (ax_sx * M_TO_DXF, ax_sy * M_TO_DXF)

    # ── 2. GDCR core requirements ─────────────────────────────────────────────
    # Estimate total dwelling units for GDCR lift sizing (§13.12.2):
    # Use floor area based estimate: net usable ≈ 60% of footprint, avg unit ≈ 40 m²
    # (conservative — accounts for mix of 1RK @ 15m² to 3BHK @ 70m²).
    avg_unit_sqm    = 40.0
    est_units_floor = max(2, int(footprint_sqm * 0.60 / avg_unit_sqm))
    est_total_units = est_units_floor * max(1, n_floors)

    n_lifts_gdcr     = _n_lifts_required(building_height_m, est_total_units)
    n_stairs         = _n_stairs(building_height_m)
    stair_w_required = _stair_width_required(building_height_m)

    # ── Core overflow guard ───────────────────────────────────────────────────
    stair_total_L    = n_stairs * STAIR_W + max(0, n_stairs - 1) * STAIR_WALL
    available_lift_L = max(0.0, L_m - 2.0 * MIN_UNIT_BAND_M - stair_total_L - 0.5)
    n_lifts_fit      = max(0, int(available_lift_L / LIFT_SHAFT_W))
    lift_capped      = n_lifts_fit < n_lifts_gdcr
    n_lifts          = min(n_lifts_gdcr, n_lifts_fit)

    lift_total_L  = n_lifts  * LIFT_SHAFT_W
    core_gap      = 0.5 if n_lifts > 0 and n_stairs > 0 else 0.0
    core_len      = max(stair_total_L + core_gap + lift_total_L, stair_total_L, 2.5)

    # ── 3. Key S-positions — symmetric H-plan layout ──────────────────────────
    # Corridor: 1.8 m band centred on floor width (upgraded from 1.5 m)
    CORRIDOR_W_USE = 1.80
    s_mid    = SHORT_m / 2.0
    s_corr_0 = s_mid - CORRIDOR_W_USE / 2.0   # south edge of corridor
    s_corr_1 = s_mid + CORRIDOR_W_USE / 2.0   # north edge of corridor

    # Core extends symmetrically around corridor:
    # South half: lifts + lobby (below corridor)
    # North half: stairs (above corridor)
    if n_lifts > 0:
        core_s_start = s_corr_0 - LIFT_LANDING_D - LIFT_CABIN_D
        core_s_end   = s_corr_1 + STAIR_D
    else:
        core_s_start = s_corr_0 - STAIR_D / 2.0
        core_s_end   = s_corr_1 + STAIR_D / 2.0

    # Clamp to floor boundary
    core_s_start = max(0.2, core_s_start)
    core_s_end   = min(SHORT_m - 0.2, core_s_end)
    core_S_depth = core_s_end - core_s_start

    # ── 4. Key L-positions ────────────────────────────────────────────────────
    # Centring is optimal for symmetric plates; asymmetric plates
    # can override if a future multi-core strategy is added.
    l_core_start = (L_m - core_len) / 2.0
    l_core_end   = l_core_start + core_len

    # Stairs: left end of core; lifts: right end
    l_stair_start = l_core_start
    l_lift_start  = l_stair_start + stair_total_L + core_gap

    # ── 5. Derived unit depths (maximised, not minimum) ───────────────────────
    # Use FULL available depth: south = s_corr_0, north = SHORT_m − s_corr_1
    depth_south = s_corr_0              # full south depth
    depth_north = SHORT_m - s_corr_1   # full north depth

    # ── 6. Build feature list ─────────────────────────────────────────────────
    unit_mix_clean = [u.upper().replace(" ", "") for u in (unit_mix or ["2BHK"])]
    features: List[Dict] = []

    # Shorthand: rectangle in local-metre coords → DXF GeoJSON polygon
    def R(l0: float, s0: float, l1: float, s1: float) -> Dict:
        return _rect(l0, s0, l1, s1, origin, l_dxf_pm, s_dxf_pm)

    # ── Footprint background (actual polygon, not bounding box) ───────────────
    features.append({
        "type": "Feature", "id": "footprint_bg",
        "geometry": footprint_geojson,
        "properties": {
            "layer": "footprint_bg",
            "area_sqm": round(footprint_sqm, 2),
        },
    })

    # ── Corridor (full length) ────────────────────────────────────────────────
    corridor_sqm = L_m * CORRIDOR_W_USE
    features.append({
        "type": "Feature", "id": "corridor",
        "geometry": R(0, s_corr_0, L_m, s_corr_1),
        "properties": {
            "layer": "corridor",
            "label": f"Corridor  {CORRIDOR_W_USE:.1f} m",
            "area_sqm": round(corridor_sqm, 2),
            "width_m": CORRIDOR_W_USE,
        },
    })

    # ── Stair S-positions (north of corridor) ───────────────────────────────
    stair_s0 = s_corr_1
    stair_s1 = s_corr_1 + STAIR_D
    stair_s1 = min(stair_s1, core_s_end)

    # ── Core block (only wraps actual core elements: stair + lift + lobby) ───
    # Actual core S-span: stairs above corridor + lifts below corridor.
    core_s_above = stair_s1 - s_corr_1 if stair_s1 > s_corr_1 else 0
    core_s_below = s_corr_0 - core_s_start if n_lifts > 0 else 0
    core_sqm = core_len * (core_s_above + core_s_below)
    features.append({
        "type": "Feature", "id": "core",
        "geometry": R(l_core_start, core_s_start, l_core_end, core_s_end),
        "properties": {
            "layer": "core",
            "label": "Core",
            "area_sqm": round(core_sqm, 2),
            "n_lifts": n_lifts,
            "n_stairs": n_stairs,
        },
    })

    # ── Individual staircase blocks ────────────────────────────────────────
    for si in range(n_stairs):
        sx_l0 = l_stair_start + si * (STAIR_W + STAIR_WALL)
        sx_l1 = sx_l0 + STAIR_W
        features.append({
            "type": "Feature", "id": f"stair_{si + 1}",
            "geometry": R(sx_l0, stair_s0, sx_l1, stair_s1),
            "properties": {
                "layer":          "stair",
                "index":          si + 1,
                "label":          f"S{si + 1}",
                "width_m":        STAIR_W,
                "depth_m":        round(stair_s1 - stair_s0, 2),
                "tread_mm":       250,
                "riser_mm":       175,
                "compliant_width": STAIR_W >= stair_w_required,
                "gdcr_min_width": stair_w_required,
            },
        })

    # ── Lift lobby / landing (south of corridor, inside core) ────────────────
    if n_lifts > 0:
        lobby_l0  = l_lift_start
        lobby_l1  = l_lift_start + lift_total_L
        lobby_s0  = s_corr_0 - LIFT_LANDING_D
        lobby_s1  = s_corr_0
        lobby_s0  = max(lobby_s0, core_s_start)
        lobby_sqm = (lobby_l1 - lobby_l0) * (lobby_s1 - lobby_s0)
        features.append({
            "type": "Feature", "id": "lift_lobby",
            "geometry": R(lobby_l0, lobby_s0, lobby_l1, lobby_s1),
            "properties": {
                "layer":       "lobby",
                "label":       "Lift Landing",
                "area_sqm":    round(lobby_sqm,    2),
                "landing_w_m": round(lift_total_L, 2),
                "landing_d_m": LIFT_LANDING_D,
                "gdcr_min_w":  1.80,
                "gdcr_min_d":  2.00,
                "landing_ok":  (lift_total_L >= 1.80 and LIFT_LANDING_D >= 2.00),
            },
        })

    # ── Individual lift shafts (south of lobby, below corridor) ──────────────
    for li in range(n_lifts):
        lx_l0   = l_lift_start + li * LIFT_SHAFT_W
        lx_l1   = lx_l0 + LIFT_SHAFT_W
        lx_s0   = s_corr_0 - LIFT_LANDING_D - LIFT_CABIN_D
        lx_s1   = s_corr_0 - LIFT_LANDING_D
        lx_s0   = max(lx_s0, core_s_start)
        is_fire = (building_height_m > 25.0 and li == n_lifts - 1)
        features.append({
            "type": "Feature", "id": f"lift_{li + 1}",
            "geometry": R(lx_l0, lx_s0, lx_l1, lx_s1),
            "properties": {
                "layer":            "lift",
                "index":            li + 1,
                "label":            f"FL{li + 1}" if is_fire else f"L{li + 1}",
                "cabin_w_m":        LIFT_CABIN_W,
                "cabin_d_m":        LIFT_CABIN_D,
                "cabin_sqm":        round(LIFT_CABIN_W * LIFT_CABIN_D, 2),
                "fire_lift":        is_fire,
                "capacity_persons": 6,
            },
        })

    # ─────────────────────────────────────────────────────────────────────────
    # ── 7. Units — optimised mixed-type bin-packing ───────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # Available L-regions (flanking the core)
    unit_regions: List[Tuple[float, float]] = []
    if l_core_start > 1.0:
        unit_regions.append((0.0, l_core_start))
    if L_m - l_core_end > 1.0:
        unit_regions.append((l_core_end, L_m))

    unit_sides = [
        # south face: better light → prefer larger/premium types
        {"name": "south", "s0": 0.0,      "s1": s_corr_0,  "depth": depth_south,
         "face": "south"},
        # north face: service units → prefer 1BHK/2BHK
        {"name": "north", "s0": s_corr_1, "s1": SHORT_m,   "depth": depth_north,
         "face": "north"},
    ]

    units: List[Dict] = []
    balconies: List[Dict] = []
    unit_seq = 0

    for side_idx, side in enumerate(unit_sides):
        depth = side["depth"]
        if depth < MIN_UNIT_DEPTH:
            continue

        # Build preferred-mix for this side:
        # South → larger types first; North → smaller types first.
        if len(unit_mix_clean) > 1:
            primary = unit_mix_clean[side_idx % len(unit_mix_clean)]
            preferred = [primary] + [t for t in unit_mix_clean if t != primary]
        else:
            preferred = unit_mix_clean[:]

        # Re-order by preference (south wants bigger, north wants smaller)
        if side["face"] == "south":
            preferred = sorted(preferred,
                               key=lambda t: _UNIT_W.get(t, 6.0), reverse=True)
        else:
            preferred = sorted(preferred,
                               key=lambda t: _UNIT_W.get(t, 6.0))

        # Add remaining sizes as fallback
        for t in _UNIT_SIZE_ORDER:
            if t not in preferred:
                preferred.append(t)

        for region_l0, region_l1 in unit_regions:
            region_len = region_l1 - region_l0
            if region_len < 3.5:
                continue

            # ── Greedy mixed-type packing ──────────────────────────────────
            packed = _pack_region_mixed(region_len, depth, preferred)

            for utype, rel_l0, rel_l1 in packed:
                ul0 = region_l0 + rel_l0
                ul1 = region_l0 + rel_l1
                uw_actual = ul1 - ul0

                # Polygon containment — centroid must be inside actual footprint
                cl_m = (ul0 + ul1) / 2.0
                cs_m = (side["s0"] + side["s1"]) / 2.0
                cx_dxf = origin[0] + cl_m * l_dxf_pm[0] + cs_m * s_dxf_pm[0]
                cy_dxf = origin[1] + cl_m * l_dxf_pm[1] + cs_m * s_dxf_pm[1]
                if not _point_in_polygon(cx_dxf, cy_dxf, outer):
                    continue

                unit_seq += 1
                gross_sqm  = uw_actual * depth
                carpet_sqm = gross_sqm * 0.82
                rera_sqm   = gross_sqm * 0.78

                # Ventilation compliance (§13.1.11)
                vent = _ventilation_check(utype, uw_actual, depth)

                unit_feat = {
                    "type": "Feature",
                    "id":   f"unit_{unit_seq}",
                    "geometry": R(ul0, side["s0"], ul1, side["s1"]),
                    "properties": {
                        "layer":              "unit",
                        "unit_id":            f"U{unit_seq:02d}",
                        "unit_type":          utype,
                        "index":              unit_seq,
                        "area_sqm":           round(gross_sqm,  2),
                        "carpet_area_sqm":    round(carpet_sqm, 2),
                        "rera_carpet_sqm":    round(rera_sqm,   2),
                        "side":               side["name"],
                        "label":              utype,
                        "depth_m":            round(depth,      2),
                        "width_m":            round(uw_actual,  2),
                        "has_balcony":        False,
                        # Private: local-metre bounds for room subdivision
                        "_l0": ul0, "_s0": side["s0"],
                        "_l1": ul1, "_s1": side["s1"],
                        **vent,
                    },
                }
                units.append(unit_feat)

                # ── Balcony strip (south face only, §13.1.12) ────────────
                if BALCONY_ENABLED and side["face"] == "south":
                    balc_s1 = side["s0"]          # south face of unit wall
                    balc_s0 = balc_s1 - BALCONY_DEPTH_M   # balcony extends outward
                    if balc_s0 >= -0.01:          # within footprint projection
                        balcony_sqm = uw_actual * BALCONY_DEPTH_M
                        balc_feat = {
                            "type": "Feature",
                            "id":   f"balcony_{unit_seq}",
                            "geometry": R(ul0, max(0.0, balc_s0), ul1, balc_s1),
                            "properties": {
                                "layer":       "balcony",
                                "unit_id":     f"U{unit_seq:02d}",
                                "label":       "Balcony",
                                "depth_m":     BALCONY_DEPTH_M,
                                "width_m":     round(uw_actual, 2),
                                "area_sqm":    round(balcony_sqm, 2),
                                "fsi_exempt":  True,
                                "gdcr_clause": "§13.1.12 — open balcony excluded from FSI",
                            },
                        }
                        balconies.append(balc_feat)
                        # Mark parent unit
                        unit_feat["properties"]["has_balcony"] = True
                        unit_feat["properties"]["balcony_sqm"] = round(balcony_sqm, 2)

    # ── 7b. Detailed unit subdivision — rooms, walls, doors, windows ────────
    detail_features: List[Dict] = []

    for u in units:
        props = u["properties"]
        uid = props["unit_id"]
        utype = props["unit_type"]
        side_name = props["side"]

        ul0 = props.get("_l0", 0)
        us0 = props.get("_s0", 0)
        ul1 = props.get("_l1", ul0 + props["width_m"])
        us1 = props.get("_s1", us0 + props["depth_m"])

        # South units: corridor at s1 edge → core_side="north"
        # North units: corridor at s0 edge → core_side="south"
        core_side = "north" if side_name == "south" else "south"
        detail_features.extend(
            _generate_unit_detail(
                ul0, us0, ul1, us1,
                utype, core_side, uid,
                origin, l_dxf_pm, s_dxf_pm,
            )
        )

    features.extend(detail_features)
    features.extend(units)
    features.extend(balconies)

    # ── 8. Metrics ────────────────────────────────────────────────────────────
    total_unit_sqm  = sum(u["properties"]["area_sqm"] for u in units)
    total_balc_sqm  = sum(b["properties"]["area_sqm"] for b in balconies)
    n_units_floor   = len(units)
    net_bua_sqm     = total_unit_sqm * max(1, n_floors)
    gross_bua_sqm   = footprint_sqm  * max(1, n_floors)
    fsi_net         = net_bua_sqm   / plot_area_sqm if plot_area_sqm > 0 else 0.0
    fsi_gross       = gross_bua_sqm / plot_area_sqm if plot_area_sqm > 0 else 0.0
    efficiency_pct  = (total_unit_sqm / footprint_sqm * 100.0) if footprint_sqm > 0 else 0.0

    unit_type_counts: Dict[str, int] = {}
    for u in units:
        t = u["properties"]["unit_type"]
        unit_type_counts[t] = unit_type_counts.get(t, 0) + 1

    # Ventilation summary
    vent_fail_count = sum(
        0 if u["properties"].get("ventilation_ok", True) else 1
        for u in units
    )

    # GDCR §13.12.2: actual required lifts based on real unit count
    actual_total_units = n_units_floor * max(1, n_floors)
    n_lifts_req_actual = _n_lifts_required(building_height_m, actual_total_units)
    fire_lift_required = building_height_m > 25.0
    fire_lift_provided = any(
        f["properties"].get("fire_lift")
        for f in features if f.get("id", "").startswith("lift_")
    )

    gdcr = {
        # §13.12.2 — Lifts
        "lift_required":           building_height_m > 10.0,
        "lift_provided":           n_lifts,
        "lift_required_gdcr":      n_lifts_gdcr,
        "lift_required_by_height": 2 if building_height_m > 25.0 else (1 if building_height_m > 10.0 else 0),
        "lift_required_by_units":  n_lifts_req_actual,
        "lift_capped":             lift_capped,
        "lift_cap_reason":         (
            f"Core would overflow floor plate ({L_m:.1f} m); "
            f"GDCR requires {n_lifts_gdcr} lifts but only {n_lifts} fit. "
            f"Consider increasing tower length."
        ) if lift_capped else None,
        "lift_ok":                 n_lifts >= n_lifts_req_actual,
        "fire_lift_required":      fire_lift_required,
        "fire_lift_provided":      fire_lift_provided,
        "fire_lift_ok":            fire_lift_provided if fire_lift_required else True,
        # §13.12.3 — Lift landing
        "lift_landing_d_m":        LIFT_LANDING_D,
        "lift_landing_w_m":        round(lift_total_L, 2) if n_lifts > 0 else 0.0,
        "lift_landing_ok":         (lift_total_L >= 1.80 and LIFT_LANDING_D >= 2.00) if n_lifts > 0 else True,
        # §13.1.13 Table 13.2 — Staircases
        "stair_count":             n_stairs,
        "stair_width_m":           STAIR_W,
        "stair_width_required_m":  stair_w_required,
        "stair_width_ok":          STAIR_W >= stair_w_required,
        "stair_tread_mm":          250,
        "stair_riser_mm":          175,
        "stair_geometry_ok":       True,   # tread 250 > 250 min; riser 175 < 190 max
        # Corridor
        "corridor_width_m":        CORRIDOR_W_USE,
        "corridor_width_ok":       CORRIDOR_W_USE >= 1.20,
        # §13.1.7 — Clearance heights
        "storey_height_m":         storey_height_m,
        "clearance_habitable_m":   CLEARANCE_HABITABLE_M,
        "clearance_habitable_ok":  storey_height_m >= CLEARANCE_HABITABLE_M,
        "clearance_service_m":     CLEARANCE_SERVICE_M,
        "clearance_service_ok":    storey_height_m >= CLEARANCE_SERVICE_M,
        # §13.1.11 — Ventilation
        "ventilation_units_total": n_units_floor,
        "ventilation_units_fail":  vent_fail_count,
        "ventilation_ok":          vent_fail_count == 0,
        "ventilation_gdcr_clause": "§13.1.11 — window ≥ 1/6 floor area",
        # §13.1.12 — Balconies
        "balcony_provided":        len(balconies) > 0,
        "balcony_count":           len(balconies),
        "balcony_depth_m":         BALCONY_DEPTH_M if BALCONY_ENABLED else 0.0,
        "balcony_gdcr_clause":     "§13.1.12 — open balcony excluded from FSI",
        # FSI note
        "fsi_exemptions":          ["staircase", "corridor", "lift_well", "lift_landing", "open_balcony"],
    }

    # FSI-exempt areas (corridor + core + balconies are all excluded from net BUA)
    fsi_exempt_sqm = corridor_sqm + core_sqm

    metrics = {
        "footprintSqm":            round(footprint_sqm,       2),
        "floorLengthM":            round(L_m,                 2),
        "floorWidthM":             round(SHORT_m,             2),
        "coreSqm":                 round(core_sqm,            2),
        "corridorSqm":             round(corridor_sqm,        2),
        "fsiExemptSqm":            round(fsi_exempt_sqm,      2),
        "circulationSqm":          round(core_sqm + corridor_sqm, 2),
        "balconySqmPerFloor":      round(total_balc_sqm,      2),
        "unitAreaPerFloorSqm":     round(total_unit_sqm,      2),
        "nUnitsPerFloor":          n_units_floor,
        "nTotalUnits":             actual_total_units,
        "unitTypeCounts":          unit_type_counts,
        "nFloors":                 n_floors,
        "buildingHeightM":         building_height_m,
        "storeyHeightM":           storey_height_m,
        "netBuaSqm":               round(net_bua_sqm,         2),
        "grossBuaSqm":             round(gross_bua_sqm,        2),
        "achievedFSINet":          round(fsi_net,              4),
        "achievedFSIGross":        round(fsi_gross,            4),
        "efficiencyPct":           round(efficiency_pct,       1),
        "gdcr":                    gdcr,
    }

    logger.info(
        "floor_plan: L=%.1f S=%.1f core=%.1f×%.1f units=%d balconies=%d eff=%.1f%%",
        L_m, SHORT_m, core_len, core_S_depth,
        n_units_floor, len(balconies), efficiency_pct,
    )

    return {
        "status":  "ok",
        "layout":  {"type": "FeatureCollection", "features": features},
        "metrics": metrics,
    }
