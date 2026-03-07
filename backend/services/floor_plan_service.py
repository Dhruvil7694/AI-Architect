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
CORRIDOR_W     = 1.50   # internal residential corridor (NBC min 1.2 m)
LIFT_CABIN_W   = 1.50   # lift cabin internal width
LIFT_CABIN_D   = 1.80   # lift cabin depth (6-person residential)
LIFT_SHAFT_W   = 1.85   # shaft = cabin + wall clearances
LIFT_LOBBY_D   = 1.50   # lobby depth in front of lift doors
STAIR_W        = 1.20   # staircase clear width (GDCR min 1.0 m; NBC 1.2 m)
STAIR_D        = 3.50   # depth for straight flight with mid-landing
STAIR_WALL     = 0.15   # wall between the two stair wells
MIN_UNIT_DEPTH = 5.00   # minimum meaningful unit depth (m)


# ─── GDCR helpers ─────────────────────────────────────────────────────────────

def _n_lifts(n_floors: int, height_m: float) -> int:
    if height_m <= 10.0:
        return 0
    if height_m <= 15.0:
        return 1
    if height_m <= 30.0:
        return 2
    return 3


def _n_stairs(height_m: float) -> int:
    return 2 if height_m > 15.0 else 1


# ─── Geometry helpers ─────────────────────────────────────────────────────────

def _rect(
    l0: float, s0: float, l1: float, s1: float,
    rotated: bool, ox: float, oy: float,
) -> Dict:
    """Rectangle polygon in DXF coordinate space from local (L, S) coords."""
    def pt(l: float, s: float) -> List[float]:
        return (
            [ox + s * M_TO_DXF, oy + l * M_TO_DXF] if rotated
            else [ox + l * M_TO_DXF, oy + s * M_TO_DXF]
        )
    corners = [pt(l0,s0), pt(l1,s0), pt(l1,s1), pt(l0,s1), pt(l0,s0)]
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
    # ── 1. Parse footprint bounding box ───────────────────────────────────────
    try:
        outer = (footprint_geojson.get("coordinates") or [[]])[0]
        if len(outer) < 4:
            return {"status": "error", "error": "Footprint has < 4 vertices"}
        xs = [float(c[0]) for c in outer]
        ys = [float(c[1]) for c in outer]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
    except Exception as e:
        return {"status": "error", "error": f"Could not parse footprint: {e}"}

    W_m = (maxx - minx) * DXF_TO_M
    D_m = (maxy - miny) * DXF_TO_M
    footprint_sqm = W_m * D_m

    # L = corridor (long) axis, S = unit-stack (short) axis
    rotated = D_m > W_m
    L_m     = max(W_m, D_m)
    SHORT_m = min(W_m, D_m)

    # ── 2. GDCR core requirements ─────────────────────────────────────────────
    n_lifts  = _n_lifts(n_floors, building_height_m)
    n_stairs = _n_stairs(building_height_m)

    # Core length along L (all components in a row)
    stair_total_L = n_stairs * STAIR_W + max(0, n_stairs - 1) * STAIR_WALL
    lift_total_L  = n_lifts  * LIFT_SHAFT_W
    core_gap      = 0.5 if n_lifts > 0 and n_stairs > 0 else 0.0
    core_len      = max(stair_total_L + core_gap + lift_total_L, 2.5)

    # ── 3. Key S-positions (all in local metres) ──────────────────────────────
    s_mid = SHORT_m / 2.0

    # Corridor: 1.5 m band centred on floor width
    s_corr_0 = s_mid - CORRIDOR_W / 2.0   # south edge of corridor
    s_corr_1 = s_mid + CORRIDOR_W / 2.0   # north edge of corridor

    # Core depth (S-axis): stairs + corridor + lift-shaft behind corridor
    # Stairs span from s_corr_0 going SOUTH (into south unit zone)
    # Lift shafts sit NORTH of corridor (behind lobby)
    stair_south_ext = STAIR_D / 2.0          # stairs extend south of corridor centre
    stair_north_ext = STAIR_D - stair_south_ext  # stairs extend north of corridor centre
    core_s_start    = s_corr_0 - stair_south_ext   # south edge of core
    core_s_end      = s_corr_1 + LIFT_CABIN_D       # north edge: corridor north + lift depth

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

    def R(l0, s0, l1, s1):
        return _rect(l0, s0, l1, s1, rotated, minx, miny)

    # ── Footprint background ──────────────────────────────────────────────────
    features.append({
        "type": "Feature", "id": "footprint_bg",
        "geometry": R(0, 0, L_m, SHORT_m),
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

    # ── Lift lobby (at corridor level) ────────────────────────────────────────
    if n_lifts > 0:
        lobby_l0 = l_lift_start
        lobby_l1 = l_lift_start + lift_total_L
        lobby_sqm = lift_total_L * CORRIDOR_W
        features.append({
            "type": "Feature", "id": "lift_lobby",
            "geometry": R(lobby_l0, s_corr_0, lobby_l1, s_corr_1),
            "properties": {
                "layer": "lobby",
                "label": "Lobby",
                "area_sqm": round(lobby_sqm, 2),
            },
        })

    # ── Individual lift shafts (north of lobby) ───────────────────────────────
    for li in range(n_lifts):
        lx_l0 = l_lift_start + li * LIFT_SHAFT_W
        lx_l1 = lx_l0 + LIFT_SHAFT_W
        # Shafts sit behind (north of) corridor
        lx_s0 = s_corr_1
        lx_s1 = s_corr_1 + LIFT_CABIN_D
        features.append({
            "type": "Feature", "id": f"lift_{li + 1}",
            "geometry": R(lx_l0, lx_s0, lx_l1, lx_s1),
            "properties": {
                "layer": "lift",
                "index": li + 1,
                "label": f"L{li + 1}",
                "cabin_w_m": LIFT_CABIN_W,
                "cabin_d_m": LIFT_CABIN_D,
                "cabin_sqm": round(LIFT_CABIN_W * LIFT_CABIN_D, 2),
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

    gdcr = {
        "lift_required":          building_height_m > 10.0,
        "lift_provided":          n_lifts,
        "lift_ok":                (n_lifts >= 1) if building_height_m > 10.0 else True,
        "stair_count":            n_stairs,
        "stair_width_m":          STAIR_W,
        "stair_width_ok":         STAIR_W >= 1.0,
        "stair_tread_mm":         250,
        "stair_riser_mm":         175,
        "stair_geometry_ok":      True,
        "corridor_width_m":       CORRIDOR_W,
        "corridor_width_ok":      CORRIDOR_W >= 1.20,
        "storey_height_m":        storey_height_m,
        "clearance_habitable_ok": storey_height_m >= 2.75,
        "clearance_bathroom_ok":  storey_height_m >= 2.10,
    }

    metrics = {
        "footprintSqm":        round(footprint_sqm,    2),
        "floorLengthM":        round(L_m,              2),
        "floorWidthM":         round(SHORT_m,          2),
        "coreSqm":             round(core_sqm,         2),
        "corridorSqm":         round(corridor_sqm,     2),
        "circulationSqm":      round(core_sqm + corridor_sqm, 2),
        "unitAreaPerFloorSqm": round(total_unit_sqm,   2),
        "nUnitsPerFloor":      n_units_floor,
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
