"""
services/floor_plan_service.py
-------------------------------
GDCR-compliant typical floor plan generator for a single residential tower.

Given:
  - Tower footprint polygon (GeoJSON in DXF coordinate space, where 1 unit = 1 ft)
  - Number of floors, building height, storey height
  - Preferred unit mix

Returns:
  - GeoJSON FeatureCollection with layers: corridor, core, lift, lobby, stair, unit
  - Metrics: areas, efficiency, FSI, GDCR compliance status

FSI note (as per developer convention):
  Net BUA = unit area only (corridor + core = common/excluded)
  FSI = Net BUA × n_floors / plot_area_sqm
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("services.floor_plan")

# ─── Coordinate conversion ────────────────────────────────────────────────────
DXF_TO_M = 0.3048          # 1 DXF unit = 1 foot
M_TO_DXF = 1.0 / DXF_TO_M  # 3.28084 DXF units per metre

# ─── GDCR / NBC dimensional standards (metres) ───────────────────────────────
CORRIDOR_W        = 1.50   # internal residential corridor (NBC min 1.2 m)
LIFT_CABIN_W      = 1.50   # lift cabin internal width
LIFT_CABIN_D      = 1.80   # lift cabin internal depth (6-person residential)
LIFT_SHAFT_EXTRA  = 0.35   # shaft walls + guide clearance per side → shaft = 1.85 × 2.15
LIFT_LOBBY_D      = 1.50   # lobby depth in front of lift doors
STAIR_W           = 1.20   # staircase clear width (GDCR min 1.0 m; NBC 1.2 m for residential)
STAIR_D           = 3.50   # depth for a straight flight with mid-landing
STAIR_GAP         = 0.15   # separating wall between two stair wells
MIN_UNIT_DEPTH    = 4.50   # minimum meaningful unit depth (m)


# ─── GDCR helpers ─────────────────────────────────────────────────────────────

def _n_lifts(n_floors: int, height_m: float) -> int:
    """Minimum lifts per GDCR 2017 + NBC norms."""
    if height_m <= 10.0:
        return 0          # not mandatory below 10 m
    if height_m <= 15.0:
        return 1
    if height_m <= 30.0:
        return 2
    return 3              # >30 m high-rise: 3 lifts


def _n_stairs(height_m: float) -> int:
    """NBC fire safety: 2 staircases when building height > 15 m."""
    return 2 if height_m > 15.0 else 1


# ─── Geometry helpers ─────────────────────────────────────────────────────────

def _rect_geojson_local(
    l0: float, s0: float, l1: float, s1: float,
    rotated: bool,
    origin_x: float, origin_y: float,
) -> Dict:
    """
    Produce a GeoJSON Polygon in DXF coordinate space from local (L, S) coords.

    Local frame:  L = corridor (long) axis, S = unit-stack (short) axis.
    If not rotated: L→DXF-X, S→DXF-Y
    If rotated:     L→DXF-Y, S→DXF-X
    """
    def to_dxf(l: float, s: float) -> List[float]:
        if not rotated:
            return [origin_x + l * M_TO_DXF, origin_y + s * M_TO_DXF]
        else:
            return [origin_x + s * M_TO_DXF, origin_y + l * M_TO_DXF]

    corners = [
        to_dxf(l0, s0), to_dxf(l1, s0),
        to_dxf(l1, s1), to_dxf(l0, s1),
        to_dxf(l0, s0),  # close ring
    ]
    return {"type": "Polygon", "coordinates": [corners]}


# ─── Unit-mix helpers ─────────────────────────────────────────────────────────

_UNIT_W: Dict[str, float] = {
    "STUDIO": 3.50, "1RK": 3.50,
    "1BHK":  5.00,
    "2BHK":  6.00,
    "3BHK":  7.50,
    "4BHK":  9.00,
}

_UNIT_MIN_DEPTH: Dict[str, float] = {
    "STUDIO": 4.00, "1RK": 4.00,
    "1BHK":  5.50,
    "2BHK":  7.00,
    "3BHK":  8.50,
    "4BHK": 10.00,
}


def _best_unit_type(depth_m: float, preferred: List[str]) -> Optional[str]:
    """Return the largest preferred unit type whose minimum depth ≤ available depth."""
    order = ["4BHK", "3BHK", "2BHK", "1BHK", "1RK", "STUDIO"]
    # preferred first, then fallback
    for t in order:
        if t in preferred and depth_m >= _UNIT_MIN_DEPTH.get(t, 5.0):
            return t
    for t in order:
        if depth_m >= _UNIT_MIN_DEPTH.get(t, 4.0):
            return t
    return None


# ─── Main service function ────────────────────────────────────────────────────

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

    Parameters
    ----------
    footprint_geojson : GeoJSON Polygon in DXF coordinate space (1 unit = 1 ft)
    n_floors          : number of storeys
    building_height_m : total building height in metres
    unit_mix          : preferred unit types, e.g. ["2BHK", "3BHK"]
    storey_height_m   : floor-to-floor height (default 3.0 m)
    plot_area_sqm     : total plot area in m² (for FSI computation)

    Returns
    -------
    dict with keys: status, layout (GeoJSON FeatureCollection), metrics
    """
    # ── 1. Extract footprint bounding box ────────────────────────────────────
    try:
        rings = footprint_geojson.get("coordinates", [[]])
        outer = rings[0] if rings else []
        if len(outer) < 4:
            return {"status": "error", "error": "Footprint has fewer than 4 vertices"}

        xs = [float(c[0]) for c in outer]
        ys = [float(c[1]) for c in outer]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
    except Exception as e:
        return {"status": "error", "error": f"Could not parse footprint: {e}"}

    W_ft = maxx - minx     # x-extent in DXF feet
    D_ft = maxy - miny     # y-extent in DXF feet
    W_m  = W_ft * DXF_TO_M
    D_m  = D_ft * DXF_TO_M
    footprint_sqm = W_m * D_m

    # ── 2. Orient: L = long axis (corridor), S = short axis (unit stack) ─────
    rotated = D_m > W_m
    L_m     = D_m if rotated else W_m
    SHORT_m = W_m if rotated else D_m

    # ── 3. GDCR core requirements ─────────────────────────────────────────────
    n_lifts  = _n_lifts(n_floors, building_height_m)
    n_stairs = _n_stairs(building_height_m)

    lift_shaft_w   = LIFT_CABIN_W + LIFT_SHAFT_EXTRA        # per lift shaft
    stair_block_w  = STAIR_W + STAIR_GAP                    # per stair (incl. wall)
    stair_total_l  = n_stairs * stair_block_w - STAIR_GAP   # total stairs along L
    lift_total_l   = n_lifts  * lift_shaft_w                # total lifts along L
    # Gap between stair block and lift block
    core_gap       = 0.50 if (n_stairs > 0 and n_lifts > 0) else 0.0
    core_len       = stair_total_l + core_gap + lift_total_l
    core_len       = max(core_len, 2.50)                    # absolute minimum

    # ── 4. Layout positions (all in local metres) ─────────────────────────────
    # Corridor: horizontal band through the middle of SHORT axis
    s_corridor_0 = (SHORT_m - CORRIDOR_W) / 2.0
    s_corridor_1 = s_corridor_0 + CORRIDOR_W

    # Core: centred along L axis, occupies full SHORT dimension
    l_core_0 = (L_m - core_len) / 2.0
    l_core_1 = l_core_0 + core_len

    # Within core: stairs on left, lifts on right (along L)
    l_stair_0 = l_core_0
    l_lift_0  = l_core_0 + stair_total_l + core_gap

    # Stair centreing in S (centre of depth = stair depth, relative to floor plate)
    s_stair_centre = SHORT_m / 2.0
    s_stair_0 = max(0.0, s_stair_centre - STAIR_D / 2.0)
    s_stair_1 = s_stair_0 + STAIR_D

    # Lift shaft centreing in S
    lift_total_depth_incl_lobby = LIFT_SHAFT_EXTRA / 2 + LIFT_CABIN_D + LIFT_LOBBY_D
    s_lift_0  = max(0.0, SHORT_m / 2.0 - lift_total_depth_incl_lobby / 2.0)
    s_lobby_0 = s_lift_0
    s_lobby_1 = s_lift_0 + LIFT_LOBBY_D
    s_cabin_0 = s_lobby_1
    s_cabin_1 = s_cabin_0 + LIFT_CABIN_D

    # Unit depth on each side of corridor
    unit_depth_south = s_corridor_0          # 0 → s_corridor_0
    unit_depth_north = SHORT_m - s_corridor_1  # s_corridor_1 → SHORT_m

    # ── 5. Build GeoJSON features ─────────────────────────────────────────────
    unit_mix_clean = [u.upper().replace(" ", "") for u in unit_mix] if unit_mix else ["2BHK"]
    features: List[Dict] = []

    def R(l0: float, s0: float, l1: float, s1: float) -> Dict:
        return _rect_geojson_local(l0, s0, l1, s1, rotated, minx, miny)

    # --- Tower footprint outline (background) ---
    features.append({
        "type": "Feature", "id": "footprint_outline",
        "geometry": R(0, 0, L_m, SHORT_m),
        "properties": {"layer": "footprint_bg", "area_sqm": round(footprint_sqm, 2)},
    })

    # --- Corridor ---
    corridor_sqm = L_m * CORRIDOR_W
    features.append({
        "type": "Feature", "id": "corridor",
        "geometry": R(0, s_corridor_0, L_m, s_corridor_1),
        "properties": {
            "layer": "corridor",
            "label": f"Corridor  {CORRIDOR_W:.1f} m",
            "area_sqm": round(corridor_sqm, 2),
            "width_m": CORRIDOR_W,
        },
    })

    # --- Core block (background highlight) ---
    core_sqm = core_len * SHORT_m
    features.append({
        "type": "Feature", "id": "core",
        "geometry": R(l_core_0, 0, l_core_1, SHORT_m),
        "properties": {
            "layer": "core",
            "label": "Core",
            "area_sqm": round(core_sqm, 2),
            "n_lifts": n_lifts,
            "n_stairs": n_stairs,
        },
    })

    # --- Individual staircase blocks ---
    for si in range(n_stairs):
        sx0 = l_stair_0 + si * stair_block_w
        sx1 = sx0 + STAIR_W
        features.append({
            "type": "Feature", "id": f"stair_{si + 1}",
            "geometry": R(sx0, s_stair_0, sx1, s_stair_1),
            "properties": {
                "layer": "stair",
                "index": si + 1,
                "label": f"S{si + 1}",
                "width_m": STAIR_W,
                "depth_m": STAIR_D,
                "tread_mm": 250,
                "riser_mm": 175,
                "compliant_width": STAIR_W >= 1.0,
            },
        })

    # --- Lift lobby ---
    if n_lifts > 0:
        lobby_sqm = lift_total_l * LIFT_LOBBY_D
        features.append({
            "type": "Feature", "id": "lift_lobby",
            "geometry": R(l_lift_0, s_lobby_0, l_lift_0 + lift_total_l, s_lobby_1),
            "properties": {
                "layer": "lobby",
                "label": "Lobby",
                "area_sqm": round(lobby_sqm, 2),
            },
        })

    # --- Individual lift shafts ---
    for li in range(n_lifts):
        lx0 = l_lift_0 + li * lift_shaft_w
        lx1 = lx0 + lift_shaft_w
        features.append({
            "type": "Feature", "id": f"lift_{li + 1}",
            "geometry": R(lx0, s_cabin_0, lx1, s_cabin_1),
            "properties": {
                "layer": "lift",
                "index": li + 1,
                "label": f"L{li + 1}",
                "cabin_w_m": LIFT_CABIN_W,
                "cabin_d_m": LIFT_CABIN_D,
                "cabin_sqm": round(LIFT_CABIN_W * LIFT_CABIN_D, 2),
            },
        })

    # ── 6. Units ──────────────────────────────────────────────────────────────
    # Regions along L where units can be placed (excluding core zone)
    unit_regions: List[Tuple[float, float]] = []
    if l_core_0 > 1.0:
        unit_regions.append((0.0, l_core_0))
    if L_m - l_core_1 > 1.0:
        unit_regions.append((l_core_1, L_m))

    unit_sides = [
        {"name": "south", "s0": 0.0,          "s1": s_corridor_0, "depth": unit_depth_south},
        {"name": "north", "s0": s_corridor_1, "s1": SHORT_m,       "depth": unit_depth_north},
    ]

    units: List[Dict] = []
    unit_seq = 0

    for side_idx, side in enumerate(unit_sides):
        depth = side["depth"]
        if depth < MIN_UNIT_DEPTH:
            continue

        # Pick unit type for this side (alternate if mix has >1 type)
        preferred_for_side = unit_mix_clean
        u_type = _best_unit_type(depth, preferred_for_side)
        if u_type is None:
            continue
        uw = _UNIT_W.get(u_type, 6.0)

        for region_l0, region_l1 in unit_regions:
            region_len = region_l1 - region_l0
            if region_len < 3.0:
                continue

            n_here = max(1, int(region_len / uw))
            # Actual unit width: divide region evenly so no gap at wall
            uw_actual = region_len / n_here

            for ui in range(n_here):
                ul0 = region_l0 + ui * uw_actual
                ul1 = ul0 + uw_actual
                unit_seq += 1
                gross_sqm  = uw_actual * depth
                carpet_sqm = gross_sqm * 0.82   # ~18% deduction for walls
                rera_sqm   = gross_sqm * 0.78   # stricter RERA carpet

                # Alternate unit types between units in the same row if mix allows
                if len(unit_mix_clean) > 1:
                    alt = unit_mix_clean[unit_seq % len(unit_mix_clean)]
                    if _UNIT_MIN_DEPTH.get(alt, 5.0) <= depth:
                        u_type_here = alt
                    else:
                        u_type_here = u_type
                else:
                    u_type_here = u_type

                units.append({
                    "type": "Feature",
                    "id": f"unit_{unit_seq}",
                    "geometry": R(ul0, side["s0"], ul1, side["s1"]),
                    "properties": {
                        "layer": "unit",
                        "unit_id": f"U{unit_seq:02d}",
                        "unit_type": u_type_here,
                        "index": unit_seq,
                        "area_sqm": round(gross_sqm, 2),
                        "carpet_area_sqm": round(carpet_sqm, 2),
                        "rera_carpet_sqm": round(rera_sqm, 2),
                        "side": side["name"],
                        "label": f"{u_type_here}",
                        "depth_m": round(depth, 2),
                        "width_m": round(uw_actual, 2),
                    },
                })

    features.extend(units)

    # ── 7. Metrics ────────────────────────────────────────────────────────────
    total_unit_sqm  = sum(u["properties"]["area_sqm"] for u in units)
    n_units_floor   = len(units)
    # FSI BUA = net unit area × floors (corridor + core are common areas, excluded)
    net_bua_sqm     = total_unit_sqm * max(1, n_floors)
    gross_bua_sqm   = footprint_sqm  * max(1, n_floors)
    fsi_net         = net_bua_sqm / plot_area_sqm if plot_area_sqm > 0 else 0.0
    fsi_gross       = gross_bua_sqm / plot_area_sqm if plot_area_sqm > 0 else 0.0
    efficiency_pct  = (total_unit_sqm / footprint_sqm * 100.0) if footprint_sqm > 0 else 0.0

    unit_type_counts: Dict[str, int] = {}
    for u in units:
        ut = u["properties"]["unit_type"]
        unit_type_counts[ut] = unit_type_counts.get(ut, 0) + 1

    gdcr = {
        "lift_required":        building_height_m > 10.0,
        "lift_provided":        n_lifts,
        "lift_ok":              n_lifts >= 1 if building_height_m > 10.0 else True,
        "stair_count":          n_stairs,
        "stair_width_m":        STAIR_W,
        "stair_width_ok":       STAIR_W >= 1.0,   # GDCR 1.0 m minimum
        "stair_tread_mm":       250,
        "stair_riser_mm":       175,
        "stair_geometry_ok":    True,
        "corridor_width_m":     CORRIDOR_W,
        "corridor_width_ok":    CORRIDOR_W >= 1.20,
        "storey_height_m":      storey_height_m,
        "clearance_habitable_ok": storey_height_m >= 2.75,
        "clearance_bathroom_ok":  storey_height_m >= 2.10,
    }

    metrics = {
        # Geometry
        "footprintSqm":        round(footprint_sqm, 2),
        "floorLengthM":        round(L_m, 2),
        "floorWidthM":         round(SHORT_m, 2),
        # Core & circulation
        "coreSqm":             round(core_sqm, 2),
        "corridorSqm":         round(corridor_sqm, 2),
        "circulationSqm":      round(core_sqm + corridor_sqm, 2),
        # Units
        "unitAreaPerFloorSqm": round(total_unit_sqm, 2),
        "nUnitsPerFloor":      n_units_floor,
        "unitTypeCounts":      unit_type_counts,
        # BUA / FSI
        "nFloors":             n_floors,
        "buildingHeightM":     building_height_m,
        "storeyHeightM":       storey_height_m,
        "netBuaSqm":           round(net_bua_sqm, 2),
        "grossBuaSqm":         round(gross_bua_sqm, 2),
        "achievedFSINet":      round(fsi_net, 4),
        "achievedFSIGross":    round(fsi_gross, 4),
        "efficiencyPct":       round(efficiency_pct, 1),
        # GDCR compliance
        "gdcr":                gdcr,
    }

    logger.info(
        "floor_plan_service: L=%.1fm S=%.1fm units=%d efficiency=%.1f%% n_lifts=%d n_stairs=%d",
        L_m, SHORT_m, n_units_floor, efficiency_pct, n_lifts, n_stairs,
    )

    return {
        "status":  "ok",
        "layout":  {"type": "FeatureCollection", "features": features},
        "metrics": metrics,
    }
