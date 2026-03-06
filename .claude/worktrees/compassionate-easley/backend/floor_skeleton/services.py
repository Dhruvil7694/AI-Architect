"""
floor_skeleton/services.py
---------------------------
Public API for the Floor Skeleton Generator.

Single entry point:

    generate_floor_skeleton(footprint, core_validation, dims) -> FloorSkeleton

Pipeline (plan §Step 6):

    1. Guard: NO_CORE_FIT → return NO_SKELETON sentinel immediately.
    2. Generate up to 5 CoreCandidates (validity-filtered).
    3. Build one FloorSkeleton per candidate × pattern.
    4. Evaluate each skeleton (area summary + 3 flags + audit log entry).
    5. Filter feasible: is_geometry_valid AND passes_min_unit_guard.
    6. Pre-sort + score → return optimal; or NO_SKELETON if none feasible.

The returned FloorSkeleton always has audit_log populated with one entry
per candidate attempted, so every shortfall is traceable.
"""

from __future__ import annotations

from shapely.geometry import box as shapely_box

from placement_engine.geometry.core_fit import (
    CoreDimensions,
    CoreValidationResult,
    NO_CORE_FIT,
)
from placement_engine.geometry import FootprintCandidate

from floor_skeleton.models import (
    FloorSkeleton,
    UnitZone,
    NO_SKELETON_PATTERN,
    NO_SKELETON_LABEL,
    AXIS_DEPTH_DOMINANT,
)
from floor_skeleton.core_placement_candidates import generate_candidates
from floor_skeleton.skeleton_builder import build_skeleton
from floor_skeleton.skeleton_evaluator import evaluate, select_best


def generate_floor_skeleton(
    footprint:       FootprintCandidate,
    core_validation: CoreValidationResult,
    dims:            CoreDimensions | None = None,
) -> FloorSkeleton:
    """
    Generate the optimal floor skeleton for a single tower footprint.

    Parameters
    ----------
    footprint       : FootprintCandidate from the placement engine.
                      Uses width_m and depth_m; polygon is in DXF feet
                      but the skeleton works in a LOCAL metres frame.
    core_validation : CoreValidationResult from validate_core_fit().
    dims            : CoreDimensions (default values used if None).

    Returns
    -------
    FloorSkeleton — the highest-scoring feasible candidate, or a
    NO_SKELETON sentinel if no candidate passed validation.
    """
    if dims is None:
        dims = CoreDimensions()

    # ── Guard: upstream core fit failed ───────────────────────────────────────
    if core_validation.core_fit_status == NO_CORE_FIT:
        return _no_skeleton_sentinel(
            reason="CoreValidationResult.core_fit_status == NO_CORE_FIT"
        )

    W   = footprint.width_m
    D   = footprint.depth_m
    cpw = core_validation.core_pkg_width_m
    cpd = core_validation.core_pkg_depth_m
    pat = core_validation.selected_pattern

    # ── Guard: degenerate dimensions ─────────────────────────────────────────
    if W <= 0 or D <= 0 or cpw <= 0 or cpd <= 0:
        return _no_skeleton_sentinel(
            reason=f"Degenerate dimensions: W={W} D={D} cpw={cpw} cpd={cpd}"
        )

    # ── Step 1: generate candidates ───────────────────────────────────────────
    candidates = generate_candidates(W, D, cpw, cpd, dims)
    if not candidates:
        return _no_skeleton_sentinel(
            reason="No valid candidate positions for this footprint"
        )

    # ── Steps 2-4: build and evaluate each skeleton ───────────────────────────
    all_skeletons: list[FloorSkeleton] = []
    audit_log:     list[dict]          = []

    for candidate in candidates:
        skeleton = build_skeleton(candidate, pat, W, D, dims)
        failures = evaluate(skeleton, dims)

        entry = {
            "label":                 candidate.label,
            "pattern":               skeleton.pattern_used,
            "is_geometry_valid":     skeleton.is_geometry_valid,
            "passes_min_unit_guard": skeleton.passes_min_unit_guard,
            "is_viable":             skeleton.is_architecturally_viable,
            "efficiency_ratio":      round(skeleton.efficiency_ratio, 4),
            "unit_area_sqm":         round(
                skeleton.area_summary.get("unit_area_sqm", 0.0), 4),
            "failures":              failures,
        }
        audit_log.append(entry)
        all_skeletons.append(skeleton)

    # ── Step 5: filter feasible candidates ───────────────────────────────────
    feasible = [
        s for s in all_skeletons
        if s.is_geometry_valid and s.passes_min_unit_guard
    ]

    # ── Step 6: select best or return NO_SKELETON ─────────────────────────────
    best = select_best(feasible)
    if best is None:
        sentinel = _no_skeleton_sentinel(
            reason="No feasible skeleton found after validation"
        )
        sentinel.audit_log = audit_log
        return sentinel

    # Attach UnitLocalFrame to each zone (Phase 1.5)
    if best.unit_zones:
        from floor_skeleton.frame_deriver import derive_local_frame
        for zone in best.unit_zones:
            zone.local_frame = derive_local_frame(best, zone)

    best.audit_log = audit_log
    return best


# ── NO_SKELETON sentinel ───────────────────────────────────────────────────────

def _no_skeleton_sentinel(reason: str = "") -> FloorSkeleton:
    """Return a fully populated FloorSkeleton with NO_SKELETON status."""
    dummy_fp = shapely_box(0, 0, 1, 1)
    dummy_core = shapely_box(0, 0, 0, 0)   # empty
    return FloorSkeleton(
        footprint_polygon=dummy_fp,
        core_polygon=dummy_core,
        corridor_polygon=None,
        unit_zones=[],
        pattern_used=NO_SKELETON_PATTERN,
        placement_label=NO_SKELETON_LABEL,
        area_summary={
            "footprint_area_sqm":  0.0,
            "core_area_sqm":       0.0,
            "corridor_area_sqm":   0.0,
            "unit_area_sqm":       0.0,
            "n_unit_zones":        0,
            "efficiency_ratio":    0.0,
            "core_ratio":          0.0,
            "circulation_ratio":   0.0,
            "non_habitable_ratio": 0.0,
            "unit_band_widths":    [],
            "unit_band_depths":    [],
            "area_check_passes":   False,
        },
        efficiency_ratio=0.0,
        is_geometry_valid=False,
        passes_min_unit_guard=False,
        is_architecturally_viable=False,
        audit_log=[{"reason": reason}],
    )
