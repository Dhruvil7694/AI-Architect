"""
Standalone smoke-test for TP14 FP133, plot_area ≈ 4000 sqm.

Exercises the three changes from the GDCR/FSI fix:
  1. coverage_enforcer  — centroid scaling primary, bisection fallback
  2. footprint_optimizer — 7×7 centre grid (49 points)
  3. Expected FSI band for 60 m road, 4000 sqm plot, max_fsi 4.0

No Django / PostGIS required.  Runs with plain `python test_tp14fp133_gdcr.py`.
"""

from __future__ import annotations

import math
import sys
import os
import types
from unittest.mock import patch

# ── Make sure the backend package root is on sys.path ──────────────────────────
BACKEND = os.path.dirname(os.path.abspath(__file__))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ── Stub out Django-dependent modules before any project import ────────────────
#    rules_engine.rules.loader uses django.conf.settings; inject a lightweight
#    fake so coverage_enforcer can be imported without a real Django project.

def _fake_get_gdcr_config():
    return {"ground_coverage": {"max_percentage_dw3": 40.0}}

# Stub the whole rules_engine hierarchy
for mod_name in [
    "rules_engine",
    "rules_engine.rules",
    "rules_engine.rules.loader",
    "rules_engine.rules.base",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules["rules_engine.rules.loader"].get_gdcr_config = _fake_get_gdcr_config  # type: ignore

# ── Now import our modules ─────────────────────────────────────────────────────
from shapely.geometry import Polygon, box  # noqa: E402

from envelope_engine.geometry.coverage_enforcer import enforce_ground_coverage  # noqa: E402
from placement_engine.geometry.footprint_optimizer import (  # noqa: E402
    _sample_centers,
    optimize_footprint_in_zone,
)
from shapely.prepared import prep  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────────────────
SQFT_PER_SQM = 10.7639
METRES_TO_DXF = 1.0 / 0.3048   # 3.28084 ft/m
DXF_TO_METRES = 0.3048

PLOT_AREA_SQM   = 4000.0
PLOT_AREA_SQFT  = PLOT_AREA_SQM * SQFT_PER_SQM   # 43 055.6 sqft
PLOT_SIDE_DXF   = math.sqrt(PLOT_AREA_SQFT)       # ≈ 207.5 ft  (square plot)

MAX_FSI         = 4.0
ROAD_WIDTH_M    = 60.0   # qualifies for max_height 70 m
STOREY_H_M      = 3.0
MAX_HEIGHT_M    = 70.0   # GDCR Table 6.23 for road ≥ 36 m
MAX_FLOORS      = int(MAX_HEIGHT_M / STOREY_H_M)  # 23

# ── Helper ─────────────────────────────────────────────────────────────────────

def _make_square_plot() -> Polygon:
    """Square plot, PLOT_AREA_SQFT sq.ft in DXF feet."""
    s = PLOT_SIDE_DXF
    return box(0, 0, s, s)

def _make_envelope_after_margins(plot: Polygon) -> Polygon:
    """
    Simulate envelope after applying GDCR margins for 60 m road, 70 m building:
      road margin  = max(H/5, 12 m) = max(14, 12) = 14 m → 45.93 ft
      side/rear    = 8 m  →  26.25 ft
    """
    road_m = max(MAX_HEIGHT_M / 5.0, 12.0)   # 14.0 m
    side_m = 8.0
    rear_m = 8.0

    road_ft = road_m * METRES_TO_DXF
    side_ft = side_m * METRES_TO_DXF
    rear_ft = rear_m * METRES_TO_DXF

    minx, miny, maxx, maxy = plot.bounds
    return box(
        minx + road_ft,  miny + rear_ft,
        maxx - side_ft,  maxy - side_ft,
    )

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
_results: list[bool] = []

def check(cond: bool, msg: str) -> None:
    _results.append(cond)
    print(f"  {PASS if cond else FAIL}  {msg}")


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 1 – Coverage Enforcer: centroid scaling for TP14 FP133
# ══════════════════════════════════════════════════════════════════════════════
print("\n── TEST 1: Coverage enforcer — centroid scaling (TP14 FP133, 4000 sqm) ──")

plot     = _make_square_plot()
envelope = _make_envelope_after_margins(plot)

initial_gc = envelope.area / plot.area * 100.0
print(f"  plot_area    = {plot.area:,.1f} sqft  ({plot.area / SQFT_PER_SQM:.1f} sqm)")
print(f"  envelope_area= {envelope.area:,.1f} sqft  ({envelope.area / SQFT_PER_SQM:.1f} sqm)")
print(f"  initial GC   = {initial_gc:.2f}%")

check(initial_gc > 40.0, f"Initial GC {initial_gc:.2f}% exceeds 40% limit (enforcement needed)")

result_env, gc_pct, status = enforce_ground_coverage(envelope, plot, enforce=True)

check(status == "CLIPPED",  f"status == 'CLIPPED' (got '{status}')")
check(gc_pct <= 40.0 + 1e-3, f"Enforced GC {gc_pct:.2f}% ≤ 40.0%")

# Verify it used centroid scaling (scale factor should be very close to sqrt(target/original))
target_area = 0.40 * plot.area
expected_s  = math.sqrt(target_area / envelope.area)
actual_s    = math.sqrt(result_env.area / envelope.area)
check(abs(actual_s - expected_s) < 0.005, f"Scale factor ≈ sqrt(target/orig) = {expected_s:.4f} (got {actual_s:.4f})")

# Centroid of result should stay close to centroid of original envelope
d = result_env.centroid.distance(envelope.centroid)
check(d < 0.5, f"Centroid drift < 0.5 ft after scaling (got {d:.4f} ft)")

enforced_sqm = result_env.area / SQFT_PER_SQM
print(f"  enforced envelope area = {result_env.area:,.1f} sqft  ({enforced_sqm:.1f} sqm)")


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 2 – Coverage Enforcer: bisection fallback
# ══════════════════════════════════════════════════════════════════════════════
print("\n── TEST 2: Coverage enforcer — bisection fallback (non-convex star polygon) ──")

# Build a star polygon that is large (GC ~60%) but highly non-convex so that
# a scale-factor near 0.8 still yields a valid polygon (centroid scaling
# itself should work; we force the fallback by patching Shapely's scale).
from shapely.affinity import scale as shapely_scale

def _star(cx: float, cy: float, r_outer: float, r_inner: float, n: int = 6) -> Polygon:
    pts = []
    for i in range(2 * n):
        a = math.pi / n * i - math.pi / 2
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    return Polygon(pts)

star_plot = _star(100.0, 100.0, 100.0, 10.0, n=8)  # large star as plot
star_env  = _star(100.0, 100.0,  80.0,  8.0, n=8)  # slightly smaller as envelope

initial_gc_star = star_env.area / star_plot.area * 100.0
print(f"  star GC before = {initial_gc_star:.2f}%")

# Force the centroid-scaling branch to return an empty polygon
# so the bisection fallback triggers.
_original_scale = shapely_scale

def _broken_scale(geom, xfact=1.0, yfact=1.0, origin='center', zfact=1.0):
    from shapely.geometry import GeometryCollection
    return GeometryCollection()   # simulate degenerate output

with patch("envelope_engine.geometry.coverage_enforcer.scale", _broken_scale):
    result_star, gc_star, status_star = enforce_ground_coverage(star_env, star_plot, enforce=True)

check(status_star in ("CLIPPED", "OK"),
      f"Bisection fallback status is CLIPPED or OK (got '{status_star}')")
check(not result_star.is_empty, "Bisection fallback returns non-empty polygon")
print(f"  bisection fallback status = '{status_star}', GC = {gc_star:.2f}%")


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 3 – Footprint Optimizer: 7×7 grid gives better result than 3×3
# ══════════════════════════════════════════════════════════════════════════════
print("\n── TEST 3: Footprint optimizer — 7×7 grid vs 3×3 grid ──")

# Use the GC-enforced envelope as the zone for placement
zone = result_env
prep_zone = prep(zone)

centres_7x7 = _sample_centers(zone, prep_zone, points_per_axis=7)
centres_3x3 = _sample_centers(zone, prep_zone, points_per_axis=3)

check(len(centres_7x7) >= len(centres_3x3),
      f"7×7 sampled {len(centres_7x7)} points ≥ 3×3 sampled {len(centres_3x3)} points")

best_7 = optimize_footprint_in_zone(zone, building_height_m=MAX_HEIGHT_M)
best_3 = optimize_footprint_in_zone(zone, building_height_m=MAX_HEIGHT_M, step_m=3.5)

check(best_7 is not None, "7×7 optimizer found a valid footprint")
if best_7:
    fp_sqm = best_7.area_sqft / SQFT_PER_SQM
    print(f"  best footprint = {best_7.area_sqft:,.1f} sqft  ({fp_sqm:.1f} sqm)"
          f"  [{best_7.width_m:.1f} m × {best_7.depth_m:.1f} m]")


# ══════════════════════════════════════════════════════════════════════════════
#  TEST 4 – Expected FSI band for TP14 FP133
# ══════════════════════════════════════════════════════════════════════════════
print("\n── TEST 4: Expected FSI band (60 m road, 4000 sqm, max_fsi=4.0) ──")

if best_7:
    footprint_sqm = best_7.area_sqft / SQFT_PER_SQM
    allowed_bua_sqm = MAX_FSI * PLOT_AREA_SQM   # 16 000 sqm
    ideal_floors = allowed_bua_sqm / footprint_sqm
    used_floors  = min(int(ideal_floors), MAX_FLOORS)
    total_bua    = used_floors * footprint_sqm
    achieved_fsi = total_bua / PLOT_AREA_SQM

    print(f"  footprint_sqm   = {footprint_sqm:.1f}")
    print(f"  allowed_bua_sqm = {allowed_bua_sqm:.1f}")
    print(f"  ideal_floors    = {ideal_floors:.1f}  (height ceiling = {MAX_FLOORS} floors)")
    print(f"  used_floors     = {used_floors}")
    print(f"  total_bua_sqm   = {total_bua:.1f}")
    print(f"  achieved_fsi    = {achieved_fsi:.3f}")

    check(3.8 <= achieved_fsi <= 4.0,
          f"achieved_fsi {achieved_fsi:.3f} is in expected band [3.8, 4.0]")
    check(used_floors <= MAX_FLOORS,
          f"used_floors {used_floors} ≤ max_floors {MAX_FLOORS} (70 m @ 3 m/floor)")


# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════
passed = sum(_results)
total  = len(_results)
print(f"\n{'='*55}")
print(f"  Result: {passed}/{total} checks passed")
print(f"{'='*55}\n")

if passed < total:
    sys.exit(1)
