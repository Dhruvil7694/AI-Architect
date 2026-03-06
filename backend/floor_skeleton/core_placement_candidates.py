"""
floor_skeleton/core_placement_candidates.py
-------------------------------------------
Generates up to 5 discrete CoreCandidate positions for a given footprint
in the local 2-D metres frame.

Five positions (see plan section "Step 1"):

    END_CORE_LEFT              — vertical strip at X = 0
    END_CORE_RIGHT             — vertical strip at X = W - cpw
    CENTER_CORE                — vertical strip centred at X = (W - cpw) / 2
    SIDE_CORE_ALONG_LONG_EDGE  — horizontal strip at Y = 0
    SIDE_CORE_ALONG_SHORT_EDGE — horizontal strip at Y = D - cpd

Validity guards filter out positions that would leave a unit zone smaller
than the minimum required width (min_unit_width_m from CoreDimensions).

Horizontal candidates are always treated as END_CORE-only (plan §Improvement 3):
their remaining zone must satisfy min_unit_width_m (not min_unit_depth_m).
"""

from __future__ import annotations

from shapely.geometry import box as shapely_box

from placement_engine.geometry.core_fit import CoreDimensions
from floor_skeleton.models import (
    CoreCandidate,
    LABEL_END_CORE_LEFT,
    LABEL_END_CORE_RIGHT,
    LABEL_CENTER_CORE,
    LABEL_SIDE_CORE_ALONG_LONG_EDGE,
    LABEL_SIDE_CORE_ALONG_SHORT_EDGE,
)


def generate_candidates(
    W:   float,
    D:   float,
    cpw: float,
    cpd: float,
    dims: CoreDimensions,
) -> list[CoreCandidate]:
    """
    Generate all valid CoreCandidate objects for a footprint of size W × D.

    Parameters
    ----------
    W    : Footprint width in metres (long dimension, X axis).
    D    : Footprint depth in metres (short dimension, Y axis).
    cpw  : Core package width in metres (from CoreValidationResult).
    cpd  : Core package depth in metres (= stair_run_m = 3.6 m).
    dims : CoreDimensions instance supplying min_unit_width_m.

    Returns
    -------
    List of valid CoreCandidate objects in canonical order.
    Any candidate whose remaining unit zone is too narrow is silently excluded.
    """
    muw = dims.min_unit_width_m   # minimum unit zone width
    candidates: list[CoreCandidate] = []

    # ── Vertical strip candidates ──────────────────────────────────────────────
    # These span the full depth D and are positioned along the X axis.
    # Remaining unit zone width = W - cpw.

    if W - cpw >= muw:
        # END_CORE_LEFT: core at x = 0
        candidates.append(CoreCandidate(
            label=LABEL_END_CORE_LEFT,
            core_box=shapely_box(0, 0, cpw, D),
            is_horizontal=False,
        ))

        # END_CORE_RIGHT: core at x = W - cpw
        candidates.append(CoreCandidate(
            label=LABEL_END_CORE_RIGHT,
            core_box=shapely_box(W - cpw, 0, W, D),
            is_horizontal=False,
        ))

    # CENTER_CORE: each side zone must be >= muw
    half_remaining = (W - cpw) / 2.0
    if half_remaining >= muw:
        cx0 = (W - cpw) / 2.0
        cx1 = cx0 + cpw
        candidates.append(CoreCandidate(
            label=LABEL_CENTER_CORE,
            core_box=shapely_box(cx0, 0, cx1, D),
            is_horizontal=False,
        ))

    # ── Horizontal strip candidates ────────────────────────────────────────────
    # These span the full width W and are positioned along the Y axis.
    # Restricted to END_CORE pattern only (plan §Improvement 3).
    # Remaining unit zone depth = D - cpd; must satisfy min_unit_width_m.

    remaining_d = D - cpd
    if remaining_d >= muw:
        # SIDE_CORE_ALONG_LONG_EDGE: core at y = 0
        candidates.append(CoreCandidate(
            label=LABEL_SIDE_CORE_ALONG_LONG_EDGE,
            core_box=shapely_box(0, 0, W, cpd),
            is_horizontal=True,
        ))

        # SIDE_CORE_ALONG_SHORT_EDGE: core at y = D - cpd
        candidates.append(CoreCandidate(
            label=LABEL_SIDE_CORE_ALONG_SHORT_EDGE,
            core_box=shapely_box(0, D - cpd, W, D),
            is_horizontal=True,
        ))

    return candidates
