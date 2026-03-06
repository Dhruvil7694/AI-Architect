"""
floor_skeleton/skeleton_evaluator.py
--------------------------------------
Validation, area summary, feasibility flags, and scored selection.

Pipeline (plan §Steps 3-5):

    Step 3  compute_area_summary()   — fills area_summary + efficiency_ratio
    Step 4a check_geometry()         — sets is_geometry_valid
    Step 4b check_min_unit_guard()   — sets passes_min_unit_guard
    Step 4c check_viability()        — sets is_architecturally_viable
    Step 5  select_best()            — deterministic pre-sort + tuple scoring

Three-tier terminology:
    Feasible = is_geometry_valid AND passes_min_unit_guard  (scoring gate)
    Viable   = is_architecturally_viable                    (flag only)
    Optimal  = highest-scoring feasible candidate           (final result)
"""

from __future__ import annotations

from shapely.ops import unary_union

from placement_engine.geometry.core_fit import CoreDimensions
from floor_skeleton.models import (
    FloorSkeleton,
    AXIS_DEPTH_DOMINANT,
    AXIS_WIDTH_DOMINANT,
    LABEL_ORDER,
    VIABILITY_THRESHOLD,
)

# Pattern constants
PATTERN_DOUBLE = "DOUBLE_LOADED"
PATTERN_SINGLE = "SINGLE_LOADED"
PATTERN_END    = "END_CORE"

_AREA_TOL = 1e-6    # floating-point area tolerance for overlap and partition checks


# ── Step 3 — Area Summary ──────────────────────────────────────────────────────

def compute_area_summary(skeleton: FloorSkeleton) -> None:
    """
    Populate skeleton.area_summary and skeleton.efficiency_ratio in-place.

    All areas in sq.m. All ratios in [0.0, 1.0].
    """
    fp_area   = skeleton.footprint_polygon.area
    core_area = skeleton.core_polygon.area
    corr_area = (skeleton.corridor_polygon.area
                 if skeleton.corridor_polygon is not None else 0.0)
    unit_area = sum(z.polygon.area for z in skeleton.unit_zones)
    n_zones   = len(skeleton.unit_zones)

    eff_ratio  = unit_area / fp_area  if fp_area > 0 else 0.0
    core_ratio = core_area / fp_area  if fp_area > 0 else 0.0
    circ_ratio = corr_area / fp_area  if fp_area > 0 else 0.0
    nonhab     = (core_area + corr_area) / fp_area if fp_area > 0 else 0.0

    area_check = abs((core_area + corr_area + unit_area) - fp_area) < _AREA_TOL

    skeleton.area_summary = {
        # Base areas
        "footprint_area_sqm":  round(fp_area,   4),
        "core_area_sqm":       round(core_area, 4),
        "corridor_area_sqm":   round(corr_area, 4),
        "unit_area_sqm":       round(unit_area, 4),
        "n_unit_zones":        n_zones,
        # Primary ratios
        "efficiency_ratio":    round(eff_ratio,  6),
        "core_ratio":          round(core_ratio, 6),
        "circulation_ratio":   round(circ_ratio, 6),
        "non_habitable_ratio": round(nonhab,     6),
        # Per-zone dimensional breakdown
        "unit_band_widths":    [round(z.zone_width_m, 3) for z in skeleton.unit_zones],
        "unit_band_depths":    [round(z.zone_depth_m, 3) for z in skeleton.unit_zones],
        # Integrity
        "area_check_passes":   area_check,
    }
    skeleton.efficiency_ratio = eff_ratio


# ── Step 4a — Structural checks ───────────────────────────────────────────────

def check_geometry(skeleton: FloorSkeleton) -> list[str]:
    """
    Run structural validity checks (plan §4a).

    Sets skeleton.is_geometry_valid.
    Returns a list of failure reason strings (empty = all passed).
    """
    failures: list[str] = []

    # 1. All zone polygons valid and non-empty
    all_polys = [skeleton.core_polygon]
    if skeleton.corridor_polygon is not None:
        all_polys.append(skeleton.corridor_polygon)
    for uz in skeleton.unit_zones:
        all_polys.append(uz.polygon)

    for i, poly in enumerate(all_polys):
        if poly is None or poly.is_empty:
            failures.append(f"polygon[{i}] is empty")
        elif not poly.is_valid:
            failures.append(f"polygon[{i}] is invalid: {poly.explain_validity()}")

    # 2. No negative dimensions in any UnitZone
    for i, uz in enumerate(skeleton.unit_zones):
        if uz.zone_width_m <= 0:
            failures.append(f"unit_zone[{i}].zone_width_m <= 0 ({uz.zone_width_m})")
        if uz.zone_depth_m <= 0:
            failures.append(f"unit_zone[{i}].zone_depth_m <= 0 ({uz.zone_depth_m})")

    # 3. Area partition check
    if not skeleton.area_summary.get("area_check_passes", False):
        core_a = skeleton.area_summary.get("core_area_sqm", 0)
        corr_a = skeleton.area_summary.get("corridor_area_sqm", 0)
        unit_a = skeleton.area_summary.get("unit_area_sqm", 0)
        fp_a   = skeleton.area_summary.get("footprint_area_sqm", 0)
        diff   = abs((core_a + corr_a + unit_a) - fp_a)
        failures.append(f"area partition fails: diff={diff:.2e}")

    # 4. No pairwise overlaps (union of all zones ≈ footprint area)
    if not failures:   # skip if already failed
        zone_polys = [skeleton.core_polygon]
        if skeleton.corridor_polygon is not None:
            zone_polys.append(skeleton.corridor_polygon)
        for uz in skeleton.unit_zones:
            zone_polys.append(uz.polygon)
        union_area = unary_union(zone_polys).area
        fp_area    = skeleton.footprint_polygon.area
        if abs(union_area - fp_area) > _AREA_TOL:
            failures.append(
                f"zones overlap or gap: union_area={union_area:.6f} "
                f"!= footprint_area={fp_area:.6f}"
            )

    # 5. All zones within footprint
    if not failures:
        fp = skeleton.footprint_polygon
        for i, uz in enumerate(skeleton.unit_zones):
            if not uz.polygon.within(fp.buffer(_AREA_TOL)):
                failures.append(f"unit_zone[{i}] extends outside footprint")

    skeleton.is_geometry_valid = (len(failures) == 0)
    return failures


# ── Step 4b — Minimum unit geometry guard ─────────────────────────────────────

def check_min_unit_guard(
    skeleton: FloorSkeleton,
    dims:     CoreDimensions,
) -> list[str]:
    """
    Check that every unit zone satisfies minimum habitable dimensions (plan §4b).

    Uses UnitZone.zone_width_m / zone_depth_m (explicit builder fields, not
    bounding-box inference) and the orientation_axis tag to determine which
    check applies.

    Sets skeleton.passes_min_unit_guard.
    Returns list of failure reason strings.
    """
    failures: list[str] = []
    muw = dims.min_unit_width_m
    mud = dims.min_unit_depth_m
    pat = skeleton.pattern_used

    for i, uz in enumerate(skeleton.unit_zones):
        if uz.orientation_axis == AXIS_DEPTH_DOMINANT:
            # Vertical-core unit band — short side is zone_width_m
            if uz.zone_width_m < muw:
                failures.append(
                    f"unit_zone[{i}] DEPTH_DOMINANT zone_width_m "
                    f"{uz.zone_width_m:.3f} < min_unit_width_m {muw}"
                )
            # Long-side depth check applies for DOUBLE and SINGLE only
            if pat in (PATTERN_DOUBLE, PATTERN_SINGLE):
                if uz.zone_depth_m < mud:
                    failures.append(
                        f"unit_zone[{i}] DEPTH_DOMINANT zone_depth_m "
                        f"{uz.zone_depth_m:.3f} < min_unit_depth_m {mud}"
                    )
        else:
            # WIDTH_DOMINANT — horizontal core; short side is zone_depth_m
            if uz.zone_depth_m < muw:
                failures.append(
                    f"unit_zone[{i}] WIDTH_DOMINANT zone_depth_m "
                    f"{uz.zone_depth_m:.3f} < min_unit_width_m {muw}"
                )
            # No long-side check for END_CORE horizontal (full slab width)

    skeleton.passes_min_unit_guard = (len(failures) == 0)
    return failures


# ── Step 4c — Architectural viability flag ────────────────────────────────────

def check_viability(skeleton: FloorSkeleton) -> None:
    """
    Set is_architecturally_viable flag (plan §4c).

    Flag only — never used as a scoring gate.
    """
    skeleton.is_architecturally_viable = (
        skeleton.efficiency_ratio >= VIABILITY_THRESHOLD
    )


# ── Full evaluation pipeline for one skeleton ─────────────────────────────────

def evaluate(skeleton: FloorSkeleton, dims: CoreDimensions) -> list[str]:
    """
    Run all three validation checks for a single skeleton.

    Returns combined list of all failure reasons (empty = feasible).
    """
    compute_area_summary(skeleton)
    geo_failures  = check_geometry(skeleton)
    unit_failures = check_min_unit_guard(skeleton, dims)
    check_viability(skeleton)
    return geo_failures + unit_failures


# ── Step 5 — Deterministic Sort + Scoring + Selection ────────────────────────

def select_best(
    skeletons: list[FloorSkeleton],
) -> FloorSkeleton | None:
    """
    Select the optimal skeleton from a list of feasible candidates.

    Step 5a — Pre-sort deterministically:
        sort key: (-total_unit_area, -efficiency_ratio, label_index)

    Step 5b — Scoring tuple (highest wins):
        (total_unit_area, efficiency_ratio, n_unit_zones, -label_index)

    Returns None if the input list is empty.
    """
    if not skeletons:
        return None

    def label_index(s: FloorSkeleton) -> int:
        try:
            return LABEL_ORDER.index(s.placement_label)
        except ValueError:
            return len(LABEL_ORDER)

    # Step 5a — pre-sort to guarantee stable ordering before tuple comparison
    pre_sorted = sorted(
        skeletons,
        key=lambda s: (
            -s.area_summary.get("unit_area_sqm", 0.0),
            -s.efficiency_ratio,
            label_index(s),
        ),
    )

    # Step 5b — scoring tuple
    def score(s: FloorSkeleton) -> tuple:
        return (
            s.area_summary.get("unit_area_sqm", 0.0),  # 1. absolute usable area
            s.efficiency_ratio,                          # 2. efficiency %
            len(s.unit_zones),                           # 3. architectural bonus
            -label_index(s),                             # 4. canonical tie-break
        )

    return max(pre_sorted, key=score)
