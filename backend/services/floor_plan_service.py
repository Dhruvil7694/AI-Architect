"""
services/floor_plan_service.py
-------------------------------
GDCR-compliant typical floor plan generator — compact core placement engine.

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

FSI note:
  Net BUA  = unit areas × n_floors  (corridor + core = common areas, excluded)
  Gross BUA = footprint × n_floors  (used for permit)
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
CORRIDOR_W      = 1.50  # internal residential corridor (NBC min 1.2 m)
LIFT_CABIN_W    = 1.50  # lift cabin internal clear width (6-person min)
LIFT_CABIN_D    = 1.80  # lift cabin internal depth (6-person min)
LIFT_SHAFT_W    = 1.85  # shaft = cabin + wall clearances
LIFT_LANDING_D  = 2.00  # §13.12.3 cl.4: clear landing in front of doors ≥ 1.8 m × 2.0 m
STAIR_W         = 1.20  # staircase clear width (Table 13.2: ≥ 1.0 m for res. ≤ 15 m;
                        #   ≥ 1.2 m for res. > 15 m / use alternative 2×1.2 = 1×1.5 m)
STAIR_D         = 3.50  # depth for straight flight with mid-landing
STAIR_WALL      = 0.15  # separation wall between two stair wells
MIN_UNIT_DEPTH  = 5.00  # minimum meaningful unit depth (m)
# Core sizing constraint: core must leave at least this much L on each side for units.
# Prevents the GDCR lift-count formula from producing a core that swallows the floor.
MIN_UNIT_BAND_M = 5.00  # metres — minimum unit-band length on each side of core
# Clearances (§13.1.7)
CLEARANCE_HABITABLE_M = 2.90  # habitable rooms: ≥ 2.9 m between finished floor levels
CLEARANCE_SERVICE_M   = 2.10  # corridors / bathrooms / stair cabins: ≥ 2.1 m


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


# ─── Unit-mix helpers ─────────────────────────────────────────────────────────

_UNIT_W: Dict[str, float] = {
    "STUDIO": 3.5, "1RK": 3.5,
    "1BHK": 5.0,
    "2BHK": 6.0,
    "3BHK": 7.5,
    "4BHK": 9.0,
}

_UNIT_MIN_DEPTH: Dict[str, float] = {
    "STUDIO": 4.0, "1RK": 4.0,
    "1BHK": 5.5,
    "2BHK": 7.0,
    "3BHK": 8.5,
    "4BHK": 10.0,
}


def _fit_type(depth_m: float, preferred: List[str]) -> Optional[str]:
    """
    Return the first unit type from `preferred` whose minimum depth ≤ available depth.
    Respects the ORDER of `preferred` — caller controls which type is tried first.
    Falls back to the global size order if nothing in `preferred` fits.
    """
    for t in preferred:
        if depth_m >= _UNIT_MIN_DEPTH.get(t, 5.0):
            return t
    # Fallback: pick the largest that fits
    for t in ["3BHK", "2BHK", "1BHK", "1RK", "STUDIO"]:
        if depth_m >= _UNIT_MIN_DEPTH.get(t, 4.0):
            return t
    return None


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
    Generate a GDCR-compliant typical floor plan for a single residential tower.

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

    # Shoelace area of actual polygon (m²) — more accurate than bounding box
    n_v = len(outer)
    shoelace = sum(
        outer[i][0] * outer[(i + 1) % n_v][1] - outer[(i + 1) % n_v][0] * outer[i][1]
        for i in range(n_v)
    )
    footprint_sqm = abs(shoelace) / 2.0 * (DXF_TO_M ** 2)

    # Origin in DXF space: the corner that corresponds to (L=0, S=0) in local frame.
    # Back-projection: dxf = l_min * l_unit + s_min * s_unit
    origin_x = l_min * ax_lx + s_min * ax_sx
    origin_y = l_min * ax_ly + s_min * ax_sy
    origin: Tuple[float, float] = (origin_x, origin_y)

    # DXF displacement vectors per 1 metre along each local axis
    l_dxf_pm: Tuple[float, float] = (ax_lx * M_TO_DXF, ax_ly * M_TO_DXF)
    s_dxf_pm: Tuple[float, float] = (ax_sx * M_TO_DXF, ax_sy * M_TO_DXF)

    # ── 2. GDCR core requirements ─────────────────────────────────────────────
    # Estimate total dwelling units for GDCR lift sizing (§13.12.2):
    # avg unit ≈ 55 m², 65% floor efficiency → units/floor ≈ footprint × 0.65 / 55
    avg_unit_sqm   = 55.0
    est_units_floor = max(2, int(footprint_sqm * 0.65 / avg_unit_sqm))
    est_total_units = est_units_floor * max(1, n_floors)

    n_lifts_gdcr     = _n_lifts_required(building_height_m, est_total_units)
    n_stairs         = _n_stairs(building_height_m)
    stair_w_required = _stair_width_required(building_height_m)

    # ── Core overflow guard ───────────────────────────────────────────────────
    # The GDCR formula (ceil(total_units/30)) can yield many lifts for large
    # towers, making the core longer than the floor plate.  We must leave at
    # least MIN_UNIT_BAND_M on EACH side of the core for residential units.
    stair_total_L     = n_stairs * STAIR_W + max(0, n_stairs - 1) * STAIR_WALL
    available_lift_L  = max(0.0, L_m - 2.0 * MIN_UNIT_BAND_M - stair_total_L - 0.5)
    n_lifts_fit       = max(0, int(available_lift_L / LIFT_SHAFT_W))
    lift_capped       = n_lifts_fit < n_lifts_gdcr
    n_lifts           = min(n_lifts_gdcr, n_lifts_fit)

    lift_total_L  = n_lifts  * LIFT_SHAFT_W
    core_gap      = 0.5 if n_lifts > 0 and n_stairs > 0 else 0.0
    core_len      = max(stair_total_L + core_gap + lift_total_L, stair_total_L, 2.5)

    # ── 3. Key S-positions (all in local metres) ──────────────────────────────
    s_mid = SHORT_m / 2.0

    # Corridor: 1.5 m band centred on floor width
    s_corr_0 = s_mid - CORRIDOR_W / 2.0   # south edge of corridor
    s_corr_1 = s_mid + CORRIDOR_W / 2.0   # north edge of corridor

    # Core depth (S-axis):
    #   - Stairs span STAIR_D centred on corridor centre (STAIR_D/2 each side)
    #   - Lift shafts sit NORTH of corridor (depth = LIFT_CABIN_D)
    #   - Lift landing (§13.12.3): 2.0 m clear depth SOUTH of lift doors
    #     (the 2.0 m landing zone sits within/overlapping the corridor space)
    stair_south_ext = STAIR_D / 2.0          # stairs extend south of corridor centre
    core_s_start    = s_corr_0 - stair_south_ext   # south edge of core

    if n_lifts > 0:
        # Lift shaft sits north of corridor; landing is the 2.0 m in front of doors
        lift_s0  = s_corr_1                          # lift shaft south edge (corridor north)
        lift_s1  = s_corr_1 + LIFT_CABIN_D           # lift shaft north edge
        # Landing zone: 2.0 m from lift door (south of lift shaft)
        landing_s0 = lift_s0 - LIFT_LANDING_D        # may extend south of corridor
        core_s_start = min(core_s_start, landing_s0)
        core_s_end   = lift_s1
    else:
        core_s_end = s_corr_1 + STAIR_D - stair_south_ext  # stairs span north of corridor too

    # Clamp to floor boundary
    core_s_start = max(0.2, core_s_start)
    core_s_end   = min(SHORT_m - 0.2, core_s_end)
    core_S_depth = core_s_end - core_s_start

    # ── 4. Key L-positions ────────────────────────────────────────────────────
    l_core_start = (L_m - core_len) / 2.0
    l_core_end   = l_core_start + core_len

    # Stairs: at the LEFT end of the core (along L)
    l_stair_start = l_core_start

    # Lifts: after gap, on RIGHT side of stairs
    l_lift_start  = l_stair_start + stair_total_L + core_gap

    # ── 5. Build feature list ─────────────────────────────────────────────────
    unit_mix_clean = [u.upper().replace(" ", "") for u in (unit_mix or ["2BHK"])]
    features: List[Dict] = []

    # Shorthand: rectangle in local-metre coords → DXF GeoJSON polygon
    def R(l0: float, s0: float, l1: float, s1: float) -> Dict:
        return _rect(l0, s0, l1, s1, origin, l_dxf_pm, s_dxf_pm)

    # ── Footprint background — use ACTUAL polygon, not bounding box ───────────
    # This correctly renders L-shaped, rotated, or irregular tower footprints.
    features.append({
        "type": "Feature", "id": "footprint_bg",
        "geometry": footprint_geojson,   # original DXF polygon
        "properties": {
            "layer": "footprint_bg",
            "area_sqm": round(footprint_sqm, 2),
        },
    })

    # ── Corridor (full length) ────────────────────────────────────────────────
    corridor_sqm = L_m * CORRIDOR_W
    features.append({
        "type": "Feature", "id": "corridor",
        "geometry": R(0, s_corr_0, L_m, s_corr_1),
        "properties": {
            "layer": "corridor",
            "label": f"Corridor  {CORRIDOR_W:.1f} m",
            "area_sqm": round(corridor_sqm, 2),
            "width_m": CORRIDOR_W,
        },
    })

    # ── Core block (compact background) ──────────────────────────────────────
    core_sqm = core_len * core_S_depth
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

    # ── Individual staircase blocks ───────────────────────────────────────────
    # Stairs span the full core S-depth (through corridor + extensions)
    for si in range(n_stairs):
        sx_l0 = l_stair_start + si * (STAIR_W + STAIR_WALL)
        sx_l1 = sx_l0 + STAIR_W
        features.append({
            "type": "Feature", "id": f"stair_{si + 1}",
            "geometry": R(sx_l0, core_s_start, sx_l1, core_s_end),
            "properties": {
                "layer": "stair",
                "index": si + 1,
                "label": f"S{si + 1}",
                "width_m": STAIR_W,
                "depth_m": core_S_depth,
                "tread_mm": 250,
                "riser_mm": 175,
                "compliant_width": STAIR_W >= 1.0,
            },
        })

    # ── Lift lobby / landing (§13.12.3: 2.0 m × lift_total_L clear landing) ──
    if n_lifts > 0:
        lobby_l0  = l_lift_start
        lobby_l1  = l_lift_start + lift_total_L
        # Landing occupies LIFT_LANDING_D (2.0 m) south of the lift shaft face.
        # This may overlap the corridor — that is intentional (it IS the corridor
        # at that bay, widened to meet the minimum landing requirement).
        lobby_s0  = s_corr_1 - LIFT_LANDING_D
        lobby_s1  = s_corr_1
        lobby_sqm = lift_total_L * LIFT_LANDING_D
        features.append({
            "type": "Feature", "id": "lift_lobby",
            "geometry": R(lobby_l0, lobby_s0, lobby_l1, lobby_s1),
            "properties": {
                "layer": "lobby",
                "label": "Lift Landing",
                "area_sqm":    round(lobby_sqm,    2),
                "landing_w_m": round(lift_total_L, 2),
                "landing_d_m": LIFT_LANDING_D,
                "gdcr_min_w":  1.80,
                "gdcr_min_d":  2.00,
                "landing_ok":  (lift_total_L >= 1.80 and LIFT_LANDING_D >= 2.00),
            },
        })

    # ── Individual lift shafts (north of corridor) ────────────────────────────
    for li in range(n_lifts):
        lx_l0  = l_lift_start + li * LIFT_SHAFT_W
        lx_l1  = lx_l0 + LIFT_SHAFT_W
        lx_s0  = s_corr_1                   # shaft south face at corridor north edge
        lx_s1  = s_corr_1 + LIFT_CABIN_D   # shaft north face
        is_fire = (building_height_m > 25.0 and li == n_lifts - 1)
        features.append({
            "type": "Feature", "id": f"lift_{li + 1}",
            "geometry": R(lx_l0, lx_s0, lx_l1, lx_s1),
            "properties": {
                "layer":      "lift",
                "index":      li + 1,
                "label":      f"FL{li + 1}" if is_fire else f"L{li + 1}",
                "cabin_w_m":  LIFT_CABIN_W,
                "cabin_d_m":  LIFT_CABIN_D,
                "cabin_sqm":  round(LIFT_CABIN_W * LIFT_CABIN_D, 2),
                "fire_lift":  is_fire,
                "capacity_persons": 6,
            },
        })

    # ── Units ─────────────────────────────────────────────────────────────────
    # Available L-regions (excluding core L-band)
    unit_regions: List[Tuple[float, float]] = []
    if l_core_start > 1.0:
        unit_regions.append((0.0, l_core_start))
    if L_m - l_core_end > 1.0:
        unit_regions.append((l_core_end, L_m))

    # South units: 0 → s_corr_0  (south of corridor, full depth)
    depth_south = s_corr_0              # e.g. 11.25 m for 24 m wide tower
    # North units: s_corr_1 → SHORT_m  (north of corridor, full depth)
    depth_north = SHORT_m - s_corr_1    # same depth (symmetric)

    unit_sides = [
        {"name": "south", "s0": 0.0,      "s1": s_corr_0,  "depth": depth_south},
        {"name": "north", "s0": s_corr_1, "s1": SHORT_m,   "depth": depth_north},
    ]

    units: List[Dict] = []
    unit_seq = 0

    for side_idx, side in enumerate(unit_sides):
        depth = side["depth"]
        if depth < MIN_UNIT_DEPTH:
            continue

        # South side → first type in mix; north side → second type (if available).
        # This gives visual variety: e.g. 2BHK south, 3BHK north.
        if len(unit_mix_clean) > 1:
            # Put this side's preferred type FIRST so _fit_type tries it first
            primary = unit_mix_clean[side_idx % len(unit_mix_clean)]
            preferred = [primary] + [t for t in unit_mix_clean if t != primary]
        else:
            preferred = unit_mix_clean

        u_type_side = _fit_type(depth, preferred) or "2BHK"
        uw = _UNIT_W.get(u_type_side, 6.0)

        for region_l0, region_l1 in unit_regions:
            region_len = region_l1 - region_l0
            if region_len < 3.5:
                continue

            n_here   = max(1, int(region_len / uw))
            uw_actual = region_len / n_here   # divide evenly — no gap at walls

            for ui in range(n_here):
                ul0 = region_l0 + ui * uw_actual
                ul1 = ul0 + uw_actual

                # ── Polygon containment check ─────────────────────────────────
                # Convert unit centroid from local (L_m, S_m) to DXF (x, y)
                # and verify it lies inside the actual tower polygon.
                # This filters out units that overflow irregular / rotated shapes.
                cl_m = (ul0 + ul1) / 2.0
                cs_m = (side["s0"] + side["s1"]) / 2.0
                cx_dxf = origin[0] + cl_m * l_dxf_pm[0] + cs_m * s_dxf_pm[0]
                cy_dxf = origin[1] + cl_m * l_dxf_pm[1] + cs_m * s_dxf_pm[1]
                if not _point_in_polygon(cx_dxf, cy_dxf, outer):
                    continue   # centroid outside polygon — skip this bay

                unit_seq += 1
                gross_sqm  = uw_actual * depth
                carpet_sqm = gross_sqm * 0.82
                rera_sqm   = gross_sqm * 0.78

                units.append({
                    "type": "Feature",
                    "id": f"unit_{unit_seq}",
                    "geometry": R(ul0, side["s0"], ul1, side["s1"]),
                    "properties": {
                        "layer":          "unit",
                        "unit_id":        f"U{unit_seq:02d}",
                        "unit_type":      u_type_side,
                        "index":          unit_seq,
                        "area_sqm":       round(gross_sqm,  2),
                        "carpet_area_sqm":round(carpet_sqm, 2),
                        "rera_carpet_sqm":round(rera_sqm,   2),
                        "side":           side["name"],
                        "label":          u_type_side,
                        "depth_m":        round(depth, 2),
                        "width_m":        round(uw_actual, 2),
                    },
                })

    features.extend(units)

    # ── 6. Metrics ────────────────────────────────────────────────────────────
    total_unit_sqm = sum(u["properties"]["area_sqm"] for u in units)
    n_units_floor  = len(units)
    net_bua_sqm    = total_unit_sqm * max(1, n_floors)
    gross_bua_sqm  = footprint_sqm  * max(1, n_floors)
    fsi_net        = net_bua_sqm   / plot_area_sqm if plot_area_sqm > 0 else 0.0
    fsi_gross      = gross_bua_sqm / plot_area_sqm if plot_area_sqm > 0 else 0.0
    efficiency_pct = (total_unit_sqm / footprint_sqm * 100.0) if footprint_sqm > 0 else 0.0

    unit_type_counts: Dict[str, int] = {}
    for u in units:
        t = u["properties"]["unit_type"]
        unit_type_counts[t] = unit_type_counts.get(t, 0) + 1

    # GDCR §13.12.2: actual required lifts based on real unit count
    actual_total_units  = n_units_floor * max(1, n_floors)
    n_lifts_req_actual  = _n_lifts_required(building_height_m, actual_total_units)
    fire_lift_required  = building_height_m > 25.0
    fire_lift_provided  = any(
        f["properties"].get("fire_lift")
        for f in features if f.get("id", "").startswith("lift_")
    )

    gdcr = {
        # §13.12.2 — Lifts
        "lift_required":             building_height_m > 10.0,
        "lift_provided":             n_lifts,
        "lift_required_gdcr":        n_lifts_gdcr,
        "lift_required_by_height":   2 if building_height_m > 25.0 else (1 if building_height_m > 10.0 else 0),
        "lift_required_by_units":    n_lifts_req_actual,
        "lift_capped":               lift_capped,
        "lift_cap_reason":           (
            f"Core would overflow floor plate ({L_m:.1f} m); "
            f"GDCR requires {n_lifts_gdcr} lifts but only {n_lifts} fit. "
            f"Floor plate too short — consider increasing tower length."
        ) if lift_capped else None,
        "lift_ok":                   n_lifts >= n_lifts_req_actual,
        "fire_lift_required":        fire_lift_required,
        "fire_lift_provided":        fire_lift_provided,
        "fire_lift_ok":              fire_lift_provided if fire_lift_required else True,
        # §13.12.3 — Lift landing
        "lift_landing_d_m":          LIFT_LANDING_D,
        "lift_landing_w_m":          round(lift_total_L, 2) if n_lifts > 0 else 0.0,
        "lift_landing_ok":           (lift_total_L >= 1.80 and LIFT_LANDING_D >= 2.00) if n_lifts > 0 else True,
        # §13.1.13 Table 13.2 — Staircases
        "stair_count":               n_stairs,
        "stair_width_m":             STAIR_W,
        "stair_width_required_m":    stair_w_required,
        "stair_width_ok":            STAIR_W >= stair_w_required,
        "stair_tread_mm":            250,
        "stair_riser_mm":            175,
        "stair_geometry_ok":         True,
        # Corridor
        "corridor_width_m":          CORRIDOR_W,
        "corridor_width_ok":         CORRIDOR_W >= 1.20,
        # §13.1.7 — Clearance heights
        "storey_height_m":           storey_height_m,
        "clearance_habitable_m":     CLEARANCE_HABITABLE_M,
        "clearance_habitable_ok":    storey_height_m >= CLEARANCE_HABITABLE_M,
        "clearance_service_m":       CLEARANCE_SERVICE_M,
        "clearance_service_ok":      storey_height_m >= CLEARANCE_SERVICE_M,
        # FSI note (Part II §8.2.2): staircase + passage + corridor exempt from FSI
        "fsi_exemptions":            ["staircase", "corridor", "lift_well", "lift_landing"],
    }

    # FSI-exempt areas (Part II §8.2.2): corridor + core (stairs + lift wells + landing)
    # These are EXCLUDED from the FSI BUA computation — only unit areas count.
    fsi_exempt_sqm = corridor_sqm + core_sqm

    metrics = {
        "footprintSqm":        round(footprint_sqm,    2),
        "floorLengthM":        round(L_m,              2),
        "floorWidthM":         round(SHORT_m,          2),
        "coreSqm":             round(core_sqm,         2),
        "corridorSqm":         round(corridor_sqm,     2),
        "fsiExemptSqm":        round(fsi_exempt_sqm,   2),
        "circulationSqm":      round(core_sqm + corridor_sqm, 2),
        "unitAreaPerFloorSqm": round(total_unit_sqm,   2),
        "nUnitsPerFloor":      n_units_floor,
        "nTotalUnits":         actual_total_units,
        "unitTypeCounts":      unit_type_counts,
        "nFloors":             n_floors,
        "buildingHeightM":     building_height_m,
        "storeyHeightM":       storey_height_m,
        "netBuaSqm":           round(net_bua_sqm,      2),
        "grossBuaSqm":         round(gross_bua_sqm,    2),
        "achievedFSINet":      round(fsi_net,          4),
        "achievedFSIGross":    round(fsi_gross,        4),
        "efficiencyPct":       round(efficiency_pct,   1),
        "gdcr":                gdcr,
    }

    logger.info(
        "floor_plan: L=%.1f S=%.1f core=%.1f×%.1f units=%d eff=%.1f%%",
        L_m, SHORT_m, core_len, core_S_depth, n_units_floor, efficiency_pct,
    )

    return {
        "status":  "ok",
        "layout":  {"type": "FeatureCollection", "features": features},
        "metrics": metrics,
    }
