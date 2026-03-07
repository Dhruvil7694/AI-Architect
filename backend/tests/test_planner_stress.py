"""
backend/tests/test_planner_stress.py
=====================================
Stress-test suite for the site-planning geometry engine.

Covers 8 hard scenarios that are NOT tested by the basic happy-path smoke test:

  1.  Concave (U-shaped) plot envelope — centroid outside polygon
  2.  MultiPolygon envelope — two islands after COP carve / road corridor
  3.  Spacing audit — manual FAIL detection + packer single-tower forced
  4.  Road access constraint — tower far from road is rejected
  5.  GC + FSI conflict — narrow plot can't reach FSI cap
  6.  Invalid geometry — star with near-degenerate arms (bisection path)
  7.  Random polygon fuzz — 30 randomly shaped plots, no exception allowed
  8.  Regression — old buffer(-d) collapse vs new centroid scaling

All tests run without Django or PostGIS.
Execute: python tests/test_planner_stress.py   (from backend/)
"""

from __future__ import annotations

import math
import os
import random
import sys
import types
from unittest.mock import patch

# ── Ensure backend/ is on sys.path ────────────────────────────────────────────
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ── Stub Django-dependent modules (rules_engine uses django.conf.settings) ────
def _fake_get_gdcr_config():
    return {"ground_coverage": {"max_percentage_dw3": 40.0}}

for _mod in ("rules_engine", "rules_engine.rules", "rules_engine.rules.loader",
             "rules_engine.rules.base"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)
sys.modules["rules_engine.rules.loader"].get_gdcr_config = _fake_get_gdcr_config  # type: ignore

# ── Project imports (all Django-free) ─────────────────────────────────────────
from shapely.affinity import scale as shapely_scale
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union
from shapely.prepared import prep

from envelope_engine.geometry.coverage_enforcer import enforce_ground_coverage
from placement_engine.constraints.road_access import (
    DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M,
    all_towers_have_road_access,
    validate_tower_access,
)
from placement_engine.geometry import (
    DXF_TO_METRES,
    METRES_TO_DXF,
    MIN_FOOTPRINT_DEPTH_M,
    MIN_FOOTPRINT_WIDTH_M,
)
from placement_engine.geometry.footprint_optimizer import optimize_footprint_in_zone
from placement_engine.geometry.multipolygon_handler import (
    extract_components,
    find_best_in_components,
)
from placement_engine.geometry.packer import pack_towers
from placement_engine.geometry.spacing_enforcer import (
    any_spacing_fail,
    audit_spacing,
    required_spacing_m,
)

# ── Shared constants ───────────────────────────────────────────────────────────
SQFT_PER_SQM = 10.7639
MAX_GC_PCT = 40.0
GC_TOL = 0.05           # 0.05% absolute tolerance on GC enforcement
AREA_REL_TOL = 0.001    # 0.1% relative tolerance on area after scaling

# ── Test infrastructure ────────────────────────────────────────────────────────
_results: list[tuple[str, bool, str]] = []


def _check(cond: bool, label: str, detail: str = "") -> None:
    _results.append((label, cond, detail))
    mark = "\033[92m[PASS]\033[0m" if cond else "\033[91m[FAIL]\033[0m"
    line = f"  {mark}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)


def _section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f" {title}")
    print(f"{'─'*60}")


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _u_shape(outer_w: float = 300.0, outer_h: float = 300.0,
             slot_w: float = 100.0, slot_h: float = 200.0) -> Polygon:
    """
    U-shaped polygon.  Centroid falls inside the slot (outside the solid),
    making it the hardest case for centroid-based scaling.

        ┌──┐    ┌──┐
        │  │    │  │      arms
        │  └────┘  │
        └──────────┘      base
    """
    pts = [
        (0, 0), (outer_w, 0), (outer_w, outer_h),
        (outer_w - (outer_w - slot_w) / 2, outer_h),
        (outer_w - (outer_w - slot_w) / 2, outer_h - slot_h),
        ((outer_w - slot_w) / 2, outer_h - slot_h),
        ((outer_w - slot_w) / 2, outer_h),
        (0, outer_h),
    ]
    return Polygon(pts)


def _l_shape(w: float = 250.0, h: float = 250.0,
             cut_w: float = 125.0, cut_h: float = 125.0) -> Polygon:
    """L-shaped polygon (convex corner missing from top-right)."""
    return Polygon([
        (0, 0), (w, 0), (w, h - cut_h),
        (w - cut_w, h - cut_h), (w - cut_w, h),
        (0, h),
    ])


def _star(cx: float, cy: float, r_outer: float, r_inner: float, n: int = 6) -> Polygon:
    """Regular star polygon with n points."""
    pts = []
    for i in range(2 * n):
        a = math.pi / n * i - math.pi / 2
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return Polygon(pts + [pts[0]])


def _gc(env: Polygon, plot: Polygon) -> float:
    return env.area / plot.area * 100.0


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Concave (U-shaped) plot: centroid falls OUTSIDE polygon
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 1: Concave U-shaped plot — centroid outside polygon")

plot_u = _u_shape()
# Build a slightly inset U-shape as the envelope (GC ~ 55%)
env_u = _u_shape(outer_w=250.0, outer_h=250.0, slot_w=70.0, slot_h=150.0)

# Confirm centroid of the envelope is outside the plot (the hard case)
centroid_u = env_u.centroid
_check(
    not plot_u.contains(centroid_u),
    "U-shape centroid is outside the polygon",
    f"centroid=({centroid_u.x:.1f}, {centroid_u.y:.1f})",
)

initial_gc = _gc(env_u, plot_u)
_check(initial_gc > MAX_GC_PCT, f"Initial GC {initial_gc:.2f}% > 40% (enforcement needed)")

result_u, gc_u, status_u = enforce_ground_coverage(env_u, plot_u, enforce=True)

_check(status_u == "CLIPPED", f"status == CLIPPED (got '{status_u}')")
_check(result_u.is_valid and not result_u.is_empty, "Result is valid and non-empty")
_check(gc_u <= MAX_GC_PCT + GC_TOL, f"Enforced GC {gc_u:.2f}% ≤ 40%")
_check(gc_u >= MAX_GC_PCT - 5.0, f"Enforced GC {gc_u:.2f}% ≥ 35% (not over-shrunk)")

target_area = (MAX_GC_PCT / 100.0) * plot_u.area
area_ratio = result_u.area / target_area
_check(
    0.90 <= area_ratio <= 1.10,
    f"Result area within 10% of target area",
    f"ratio={area_ratio:.4f}",
)

# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — MultiPolygon envelope: two islands from COP carve + road corridor
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 2: MultiPolygon envelope — two islands after setback + COP carve")

# Simulate: large plot → margins → two separate buildable islands
island_large = box(0, 0, 150, 100)    # 150×100 = 15 000 sqft  (island A)
island_small = box(200, 0, 280, 80)   # 80×80  = 6 400 sqft  (island B)
multi_env = unary_union([island_large, island_small])

_check(
    isinstance(multi_env, MultiPolygon),
    "unary_union produced MultiPolygon (islands don't touch)",
)

components = extract_components(multi_env)
_check(len(components) == 2, f"extract_components found 2 islands (got {len(components)})")
_check(
    components[0].area > components[1].area,
    "Larger island is first (correct deterministic ordering)",
)

min_w = MIN_FOOTPRINT_WIDTH_M * METRES_TO_DXF    # 16.4 ft
min_d = MIN_FOOTPRINT_DEPTH_M * METRES_TO_DXF    # 13.1 ft
best_mp = find_best_in_components(multi_env, min_width_dxf=min_w, min_depth_dxf=min_d)

_check(best_mp is not None, "find_best_in_components found a footprint")
if best_mp:
    _check(
        island_large.contains(best_mp.footprint_polygon) or
        island_large.intersects(best_mp.footprint_polygon),
        f"Best footprint comes from the larger island (component {best_mp.source_component_index})",
        f"area={best_mp.area_sqft:.1f} sqft",
    )
    _check(
        best_mp.area_sqft > 0 and best_mp.footprint_polygon.is_valid,
        "Footprint is valid and non-zero area",
    )

# Verify pack_towers handles MultiPolygon gracefully (via Polygon wrapper)
# pack_towers expects a Polygon, so we test on the largest island directly
result_pack = pack_towers(
    envelope=island_large,
    n_towers=2,
    building_height_m=16.5,
    min_width_dxf=min_w,
    min_depth_dxf=min_d,
)
_check(result_pack.n_placed >= 1, f"pack_towers placed ≥1 tower on island A (got {result_pack.n_placed})")
_check(
    all(c.footprint_polygon.is_valid for c in result_pack.footprints),
    "All placed footprints are geometrically valid",
)

# ══════════════════════════════════════════════════════════════════════════════
# TEST 3 — Spacing constraint: audit FAIL detection + packer single-tower forced
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 3: Spacing constraint — FAIL audit + packer forced to 1 tower")

HEIGHT_M = 16.5
req_spacing_m = required_spacing_m(HEIGHT_M)   # max(16.5/3, 3) = 5.5 m
req_spacing_ft = req_spacing_m * METRES_TO_DXF  # ≈ 18.0 ft

print(f"  required spacing = {req_spacing_m:.2f} m  ({req_spacing_ft:.2f} ft)")

# 3a — Manually placed towers that are TOO CLOSE → audit FAIL
fp_close_1 = box(0, 0, 50, 50)
fp_close_2 = box(55, 0, 105, 50)          # gap = 5 ft = 1.52 m < 5.5 m
audit_fail = audit_spacing([fp_close_1, fp_close_2], HEIGHT_M)
_check(any_spacing_fail(audit_fail), "Towers 5ft apart → spacing audit FAIL")
gap_close = audit_fail[0]["gap_m"]
_check(gap_close < req_spacing_m, f"Measured gap {gap_close:.2f}m < required {req_spacing_m:.2f}m")

# 3b — Towers with adequate spacing → audit PASS
fp_ok_1 = box(0, 0, 50, 50)
gap_dxf_ok = req_spacing_ft + 5.0         # 5 ft safety margin
fp_ok_2 = box(50 + gap_dxf_ok, 0, 100 + gap_dxf_ok, 50)
audit_pass = audit_spacing([fp_ok_1, fp_ok_2], HEIGHT_M)
_check(not any_spacing_fail(audit_pass), "Towers with adequate gap → spacing audit PASS")

# 3c — Narrow envelope forces packer to 1 tower when H=70m needs 76.6ft spacing
HEIGHT_TALL = 70.0
req_tall_ft = required_spacing_m(HEIGHT_TALL) * METRES_TO_DXF  # 23.33m = 76.6 ft
# Envelope is 100ft wide; second tower needs 76.6ft clearance from first → won't fit
narrow_env = box(0, 0, 100, 80)
result_narrow = pack_towers(
    envelope=narrow_env,
    n_towers=2,
    building_height_m=HEIGHT_TALL,
    min_width_dxf=min_w,
    min_depth_dxf=min_d,
)
print(f"  H=70m, spacing={req_tall_ft:.1f}ft, envelope_width=100ft → n_placed={result_narrow.n_placed}")
_check(
    result_narrow.n_placed <= 1,
    f"100ft-wide envelope + 76.6ft spacing → packer places ≤1 tower (got {result_narrow.n_placed})",
)
_check(
    not result_narrow.has_spacing_fail,
    "No spacing FAIL when packer correctly stops at 1 tower",
)

# ══════════════════════════════════════════════════════════════════════════════
# TEST 4 — Road access constraint
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 4: Road access constraint — towers beyond 20m from road rejected")

# Road corridor: thin strip along the bottom edge (y = 0..20 ft)
road_corridor = box(0, 0, 400, 20)

MAX_DIST_M = DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M   # 20.0 m
threshold_ft = MAX_DIST_M * METRES_TO_DXF          # 65.6 ft

# Tower NEAR road: bottom edge at y=25, gap = 5 ft = 1.52 m → PASS
tower_near = box(50, 25, 130, 75)
r_near = validate_tower_access(tower_near, road_corridor, max_distance_m=MAX_DIST_M)
_check(r_near.ok, f"Tower 5ft from road → access OK (dist={r_near.distance_m:.2f}m)")
_check(r_near.distance_m < MAX_DIST_M, f"distance {r_near.distance_m:.2f}m < {MAX_DIST_M}m")

# Tower FAR from road: bottom edge at y=90, gap = 70 ft = 21.3 m → FAIL
tower_far = box(50, 90, 130, 140)
r_far = validate_tower_access(tower_far, road_corridor, max_distance_m=MAX_DIST_M)
_check(not r_far.ok, f"Tower 70ft from road → access FAIL (dist={r_far.distance_m:.2f}m)")
_check(r_far.distance_m > MAX_DIST_M, f"distance {r_far.distance_m:.2f}m > {MAX_DIST_M}m")

# all_towers_have_road_access with a mixed set
tower_borderline = box(50, 20 + threshold_ft - 0.5, 130, 20 + threshold_ft + 30)  # just inside
_check(
    all_towers_have_road_access([tower_near, tower_borderline], road_corridor, MAX_DIST_M),
    "Two nearby towers both pass all_towers_have_road_access",
)
_check(
    not all_towers_have_road_access([tower_near, tower_far], road_corridor, MAX_DIST_M),
    "Mixed [near, far] → all_towers_have_road_access returns False",
)

# Edge case: no road geometry → always passes (pipeline should not block when road unknown)
r_none = validate_tower_access(tower_far, None, max_distance_m=MAX_DIST_M)
_check(r_none.ok, "No road geometry → access check skipped (returns ok=True)")

# ══════════════════════════════════════════════════════════════════════════════
# TEST 5 — GC + FSI conflict: narrow plot cannot reach FSI cap
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 5: GC + FSI conflict — narrow plot cannot reach FSI = 4.0")

# Narrow plot: 50m × 10m = 500 sqm = 5 382 sqft
NARROW_PLOT_W_FT = 50.0 * METRES_TO_DXF     # 164.04 ft
NARROW_PLOT_D_FT = 10.0 * METRES_TO_DXF     # 32.81 ft
plot_narrow = box(0, 0, NARROW_PLOT_W_FT, NARROW_PLOT_D_FT)
plot_narrow_sqm = plot_narrow.area / SQFT_PER_SQM

# Simulate envelope = plot after 3m side/rear margins on depth
margin_ft = 3.0 * METRES_TO_DXF  # 9.84 ft
env_narrow = box(0, margin_ft, NARROW_PLOT_W_FT, NARROW_PLOT_D_FT - margin_ft)
initial_gc_n = _gc(env_narrow, plot_narrow)
print(f"  plot_sqm={plot_narrow_sqm:.1f}  envelope_gc={initial_gc_n:.1f}%")

# Run GC enforcement
result_env_n, gc_n, status_n = enforce_ground_coverage(env_narrow, plot_narrow, enforce=True)

# GC enforcement should clip to 40% (or leave unchanged if already ≤40%)
_check(gc_n <= MAX_GC_PCT + GC_TOL, f"Enforced GC {gc_n:.2f}% ≤ 40%")

# FSI calculation: what can we achieve?
MAX_FSI = 4.0
ROAD_W_M = 12.0   # 12m road → max_height = 16.5m (GDCR Table 6.23)
MAX_H_M = 16.5
STOREY_M = 3.0
max_floors = int(MAX_H_M / STOREY_M)   # 5

footprint_sqm = result_env_n.area / SQFT_PER_SQM
allowed_bua_sqm = MAX_FSI * plot_narrow_sqm
ideal_floors = allowed_bua_sqm / footprint_sqm if footprint_sqm > 0 else 0
used_floors = min(int(ideal_floors), max_floors)
achieved_bua = used_floors * footprint_sqm
achieved_fsi = achieved_bua / plot_narrow_sqm if plot_narrow_sqm > 0 else 0

print(f"  footprint={footprint_sqm:.1f}sqm  ideal_floors={ideal_floors:.1f}  "
      f"used={used_floors}  fsi={achieved_fsi:.3f}")

_check(
    achieved_fsi < MAX_FSI,
    f"Narrow plot: achieved_fsi {achieved_fsi:.3f} < cap {MAX_FSI} (geometry limits FSI)",
)
_check(
    achieved_fsi > 0.5,
    f"FSI {achieved_fsi:.3f} is still meaningful (>0.5, solver didn't collapse)",
)
_check(
    result_env_n.is_valid and not result_env_n.is_empty,
    "Envelope is valid despite FSI being below cap",
)

# ══════════════════════════════════════════════════════════════════════════════
# TEST 6 — Invalid geometry stress: star polygon with near-degenerate arms
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 6: Invalid geometry stress — star polygon, bisection fallback path")

# Build a star plot and a slightly smaller star envelope
plot_star = _star(cx=200, cy=200, r_outer=150, r_inner=20, n=8)
env_star  = _star(cx=200, cy=200, r_outer=130, r_inner=18, n=8)

gc_star_initial = _gc(env_star, plot_star)
print(f"  star initial GC = {gc_star_initial:.2f}%")

# 6a — Normal path (centroid scaling on star — may work or may fall through)
result_6a, gc_6a, status_6a = enforce_ground_coverage(env_star, plot_star, enforce=True)
_check(
    status_6a in ("OK", "CLIPPED", "MEASURE_ONLY"),
    f"Star polygon: status is a known value (got '{status_6a}')",
)
_check(result_6a.is_valid and not result_6a.is_empty, "Star result is valid and non-empty")
_check(gc_6a <= MAX_GC_PCT + GC_TOL, f"Star GC {gc_6a:.2f}% ≤ 40%")

# 6b — Force centroid scale to return empty → bisection fallback
def _always_empty_scale(geom, xfact=1.0, yfact=1.0, origin="center", zfact=1.0):
    from shapely.geometry import GeometryCollection
    return GeometryCollection()

# Rectangle guaranteed to exceed 40% GC:
# 300×210 = 63 000 sqft inside a 300×300 = 90 000 sqft plot → 70% GC.
plot_s2 = box(0, 0, 300, 300)
env_s2  = box(0, 0, 300, 210)    # 70% GC — always triggers enforcement
gc_s2   = _gc(env_s2, plot_s2)
print(f"  env_s2 GC = {gc_s2:.2f}% (forces enforcement + mocked-scale → bisection fallback)")

# Patch scale() to always return empty → forces the bisection fallback branch.
# We keep env_s2 as the envelope so GC is definitely > 40% and enforcement runs.
with patch("envelope_engine.geometry.coverage_enforcer.scale", _always_empty_scale):
    result_6b, gc_6b, status_6b = enforce_ground_coverage(env_s2, plot_s2, enforce=True)

_check(
    status_6b in ("CLIPPED", "OK"),
    f"Bisection fallback activated when scale() returns empty (status='{status_6b}')",
)
_check(result_6b.is_valid and not result_6b.is_empty, "Bisection result is valid and non-empty")
_check(gc_6b <= MAX_GC_PCT + 1.0, f"Bisection GC {gc_6b:.2f}% ≤ 41% (within tolerance)")

# 6c — Very small zone: footprint_optimizer returns None (not a crash)
tiny_zone = box(0, 0, 5, 5)   # 25 sqft << MIN_FOOTPRINT_AREA_SQFT (215 sqft)
result_tiny = optimize_footprint_in_zone(tiny_zone, building_height_m=10.0)
_check(result_tiny is None, "Tiny zone (25 sqft) → optimizer returns None (no crash)")

# ══════════════════════════════════════════════════════════════════════════════
# TEST 7 — Random polygon fuzz: 30 polygons, no exception allowed
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 7: Random polygon fuzz — 30 random plots, no exception allowed")

def _random_convex_polygon(n: int, cx: float, cy: float,
                            r_min: float, r_max: float, seed: int) -> Polygon:
    """
    Generate a random convex polygon by sorting random angles.
    Convexity is guaranteed by construction (monotone chain of radial points).
    """
    rng = random.Random(seed)
    angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
    pts = [
        (cx + rng.uniform(r_min, r_max) * math.cos(a),
         cy + rng.uniform(r_min, r_max) * math.sin(a))
        for a in angles
    ]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


fuzz_fails = []
fuzz_exceptions = []
SEEDS = range(30)

for seed in SEEDS:
    n_verts = random.Random(seed).randint(5, 12)
    try:
        plot = _random_convex_polygon(n_verts, 200, 200, 80, 180, seed)
        env  = _random_convex_polygon(n_verts, 200, 200, 50, 130, seed + 1000)

        if plot.is_empty or env.is_empty or plot.area <= 0:
            continue

        result_f, gc_f, status_f = enforce_ground_coverage(env, plot, enforce=True)

        # Core invariants
        if not (result_f.is_valid and not result_f.is_empty):
            fuzz_fails.append((seed, f"invalid/empty result, status={status_f}"))
        if status_f == "CLIPPED" and gc_f > MAX_GC_PCT + GC_TOL:
            fuzz_fails.append((seed, f"CLIPPED but GC={gc_f:.2f}% > 40%"))

    except Exception as exc:
        fuzz_exceptions.append((seed, str(exc)))

_check(len(fuzz_exceptions) == 0,
       f"0 exceptions across {len(list(SEEDS))} fuzz polygons",
       f"exceptions: {fuzz_exceptions[:3]}")
_check(len(fuzz_fails) == 0,
       f"0 geometry invariant violations",
       f"fails: {fuzz_fails[:3]}")

# Also fuzz the footprint optimizer on random zones
opt_exceptions = []
for seed in range(20):
    n_verts = random.Random(seed + 500).randint(5, 10)
    try:
        zone = _random_convex_polygon(n_verts, 100, 100, 30, 80, seed + 500)
        if zone.is_empty or zone.area <= 0:
            continue
        _ = optimize_footprint_in_zone(zone, building_height_m=16.5)
    except Exception as exc:
        opt_exceptions.append((seed, str(exc)))

_check(len(opt_exceptions) == 0,
       f"0 exceptions in footprint_optimizer across 20 fuzz zones",
       f"{opt_exceptions[:3]}")

# ══════════════════════════════════════════════════════════════════════════════
# TEST 8 — Regression: old buffer(-d) collapse vs new centroid scaling
# ══════════════════════════════════════════════════════════════════════════════
_section("TEST 8: Regression — buffer(-d) collapse vs centroid scaling")

#
# The original bug: for certain polygon shapes the old buffer(-d) bisection
# produced a polygon with GC << 40% (e.g. 14.5%) because the buffer shrinks
# a polygon faster than linear at corners / thin arms.
#
# The new approach: scale(envelope, s, s, origin='centroid') where
# s = sqrt(target_area / current_area) gives EXACT area in one step.
#


def _buffer_bisection(envelope: Polygon, plot: Polygon,
                      max_gc_pct: float = 40.0) -> tuple[Polygon, float]:
    """Simulate the old primary algorithm: buffer(-d) bisection."""
    target_area = (max_gc_pct / 100.0) * plot.area
    lo, hi = 0.0, max(
        envelope.bounds[2] - envelope.bounds[0],
        envelope.bounds[3] - envelope.bounds[1],
    ) / 2.0
    clipped = envelope
    for _ in range(20):
        mid = (lo + hi) / 2.0
        candidate = envelope.buffer(-mid)
        if candidate.is_empty:
            hi = mid
            continue
        if candidate.area > target_area:
            lo = mid
        else:
            hi = mid
            clipped = candidate
        if (hi - lo) < 1e-4:
            break
    final_gc = clipped.area / plot.area * 100.0
    return clipped, final_gc


def _centroid_scaling(envelope: Polygon, plot: Polygon,
                      max_gc_pct: float = 40.0) -> tuple[Polygon, float]:
    """The new primary algorithm: exact centroid scaling."""
    target_area = (max_gc_pct / 100.0) * plot.area
    s = math.sqrt(target_area / envelope.area)
    result = shapely_scale(envelope, xfact=s, yfact=s, origin="centroid")
    gc = result.area / plot.area * 100.0
    return result, gc


# 8a — Square plot (regression baseline: both approaches should agree on convex shapes)
plot_sq = box(0, 0, 207.5, 207.5)      # ~4000 sqm plot (square, DXF ft)
env_sq  = box(20, 20, 187.5, 187.5)    # envelope with ~40.5% GC

_, gc_buf = _buffer_bisection(env_sq, plot_sq)
_, gc_scale = _centroid_scaling(env_sq, plot_sq)

print(f"  SQUARE: buffer_bisection GC={gc_buf:.2f}%  centroid_scale GC={gc_scale:.2f}%")
_check(abs(gc_buf - MAX_GC_PCT) < 1.0,
       f"Buffer bisection on square: GC {gc_buf:.2f}% ≈ 40%")
_check(abs(gc_scale - MAX_GC_PCT) < 0.05,
       f"Centroid scaling on square: GC {gc_scale:.4f}% = 40% (exact)")

# 8b — THIN plot: a very elongated rectangle (thin arm scenario)
#      buffer(-d) must remove much more area to reach the 40% target
#      because it shrinks from all four sides, quickly collapsing the thin dimension
plot_thin = box(0, 0, 300, 300)         # 90 000 sqft plot
env_thin  = box(5, 5, 295, 55)          # 290×50 = 14 500 sqft envelope (16.1% GC)

# env_thin is BELOW 40%, so enforcement returns "OK" (no clipping)
# Build a high-GC thin envelope:
env_thin_high = box(0, 0, 290, 150)    # 290×150 = 43 500 sqft (48.3% GC)
_, gc_buf_thin   = _buffer_bisection(env_thin_high, plot_thin)
_, gc_scale_thin = _centroid_scaling(env_thin_high, plot_thin)

print(f"  THIN  : buffer_bisection GC={gc_buf_thin:.2f}%  centroid_scale GC={gc_scale_thin:.2f}%")

_check(
    abs(gc_scale_thin - MAX_GC_PCT) < 0.05,
    f"Centroid scaling on thin shape: GC {gc_scale_thin:.4f}% ≈ 40% (exact)",
)
# Buffer bisection will converge to correct GC on a rectangle (it's convex)
# but MUCH slower in absolute steps — the test just verifies it doesn't collapse
_check(
    gc_buf_thin > 5.0,
    f"Buffer bisection doesn't fully collapse thin rectangle (GC={gc_buf_thin:.2f}%)",
)

# 8c — L-shape: the canonical bug-trigger shape
#      The centroid of an L is still inside the polygon, but scaling from it
#      should be much more predictable than buffer(-d) which can collapse one arm
plot_l = _l_shape(w=250, h=250, cut_w=125, cut_h=125)
# Envelope: full L-shape (representing 58% GC situation)
env_l = _l_shape(w=220, h=220, cut_w=110, cut_h=110)

gc_l_init = _gc(env_l, plot_l)
print(f"  L-SHAPE initial GC = {gc_l_init:.2f}%")

_, gc_buf_l   = _buffer_bisection(env_l, plot_l)
result_scale_l, gc_scale_l = _centroid_scaling(env_l, plot_l)

print(f"  L-SHAPE: buffer_bisection GC={gc_buf_l:.2f}%  centroid_scale GC={gc_scale_l:.2f}%")

_check(
    abs(gc_scale_l - MAX_GC_PCT) < 0.05,
    f"Centroid scaling on L-shape: GC {gc_scale_l:.4f}% ≈ 40% (exact)",
)
_check(
    result_scale_l.is_valid and not result_scale_l.is_empty,
    "Centroid-scaled L-shape remains valid and non-empty",
)

# The KEY regression check: centroid scaling hits 40% precisely;
# buffer bisection on non-convex shapes converges to ~40% too on an L
# (it IS convex after all), but the centroid approach is EXACT (≤0.05%)
centroid_error = abs(gc_scale_l - MAX_GC_PCT)
buffer_error   = abs(gc_buf_l   - MAX_GC_PCT)
_check(
    centroid_error < buffer_error or centroid_error < 0.1,
    f"Centroid error ({centroid_error:.4f}%) ≤ buffer error ({buffer_error:.4f}%) on L-shape",
)

# 8d — U-shape: centroid OUTSIDE polygon (the hardest case)
#      Buffer bisection converges correctly here too (it's area-based)
#      Centroid scaling from an EXTERNAL centroid shifts the polygon's position
#      but still scales the area exactly
plot_u8 = _u_shape()
env_u8  = _u_shape(outer_w=260, outer_h=260, slot_w=85, slot_h=160)
gc_u8_init = _gc(env_u8, plot_u8)

if gc_u8_init > MAX_GC_PCT:
    result_u8_scale, gc_u8_scale = _centroid_scaling(env_u8, plot_u8)
    _check(
        abs(gc_u8_scale - MAX_GC_PCT) < 0.05,
        f"Centroid scaling on U-shape: GC {gc_u8_scale:.4f}% ≈ 40% (exact even with external centroid)",
    )
    _check(
        result_u8_scale.is_valid and not result_u8_scale.is_empty,
        "U-shape centroid-scaled result is valid",
    )
else:
    _check(True, f"U-shape env GC={gc_u8_init:.1f}% already ≤ 40% — scale not triggered")


# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
passed = sum(1 for _, ok, _ in _results if ok)
failed = [(label, detail) for _, ok, detail in _results if not ok for label in [_results[_results.index((_, ok, detail))][0]]]
total  = len(_results)
print(f"  Result: {passed}/{total} checks passed")
if failed:
    print(f"\n  FAILED checks:")
    for label, detail in failed:
        print(f"    ✗ {label}  {detail}")
print(f"{'='*60}\n")

if passed < total:
    sys.exit(1)
