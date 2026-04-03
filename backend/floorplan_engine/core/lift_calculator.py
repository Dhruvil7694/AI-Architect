"""
floorplan_engine/core/lift_calculator.py
----------------------------------------
Determine lift count and generate shaft geometry in a local (0, 0) frame.

R1-4: ``distribute_lifts`` handles odd counts — ceil/floor split with
the service lift staying in the main (first) bank.
"""

from __future__ import annotations

import math

from shapely.geometry import box

from floorplan_engine.config import CoreConfig, resolve_lift_count
from floorplan_engine.models import LiftResult


def calculate_lifts(n_floors: int, config: CoreConfig) -> LiftResult:
    """
    Compute lift count and generate shaft polygons in a local frame.

    Shaft polygons are axis-aligned boxes starting at (0, 0), placed
    side-by-side along the X axis.  They will be repositioned later by
    ``core_layout.assemble_core_block``.
    """
    n = resolve_lift_count(n_floors)
    w, d = config.lift_shaft_w, config.lift_shaft_d

    shaft_polys = [box(i * w, 0, (i + 1) * w, d) for i in range(n)]

    return LiftResult(
        n_lifts=n,
        shaft_geoms=[],       # DualGeom populated after frame is known
        total_width_m=n * w,
        total_depth_m=d,
        # stash raw local polys for core_layout
    ), shaft_polys


def distribute_lifts(n_lifts: int, n_cores: int) -> list[int]:
    """
    Distribute lifts across core blocks (R1-4).

    Core A (index 0) gets ``ceil(n/2)`` — the main bank including
    the service lift.  Core B gets the remainder.

    Returns a list of length ``n_cores`` with lift counts per block.
    """
    if n_cores <= 1:
        return [n_lifts]
    a = math.ceil(n_lifts / 2)
    b = n_lifts - a
    return [a, b]
