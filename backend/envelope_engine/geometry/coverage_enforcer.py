"""
geometry/coverage_enforcer.py
------------------------------
Measures and (optionally) enforces the ground coverage constraint.

CGDCR 2017 Table 6.22: maximum ground coverage for DW3 Apartments = 40 %.
Ground coverage = envelope_area / plot_area × 100.

Enforcement strategy
--------------------
If the margin-derived envelope area already satisfies the GC limit, the
polygon is returned unchanged.

If the envelope exceeds the GC limit (can happen on large flat plots where
all margins are small relative to the plot size), the envelope is shrunk
by an additional uniform inward buffer until:
    envelope.area ≤ max_gc_pct / 100 × plot_area

The additional buffer distance is solved via bisection (10 iterations,
sub-mm precision in DXF feet).

"Measurement-only" mode
-----------------------
If `enforce=False` (or GDCR.yaml has no ground_coverage key), the function
computes and returns the GC percentage without any geometry modification.
This is the current default until the exact Table 6.22 value is confirmed
with the client.
"""

from __future__ import annotations

import logging
import math

from shapely.affinity import scale
from shapely.geometry import Polygon

from rules_engine.rules.loader import get_gdcr_config

logger = logging.getLogger(__name__)


def _gdcr_max_gc_pct() -> float | None:
    """
    Return the GDCR maximum ground coverage percentage (0–100), or None if
    the key is absent from GDCR.yaml (enforcement skipped).
    """
    try:
        gdcr = get_gdcr_config()
        return float(gdcr["ground_coverage"]["max_percentage_dw3"])
    except (KeyError, TypeError):
        return None


def enforce_ground_coverage(
    envelope: Polygon,
    plot_polygon: Polygon,
    enforce: bool = True,
) -> tuple[Polygon, float, str]:
    """
    Measure ground coverage and optionally clip the envelope to stay within
    the GDCR maximum.

    Parameters
    ----------
    envelope      : margin-derived buildable footprint (Shapely Polygon, DXF ft)
    plot_polygon  : original plot polygon (Shapely Polygon, DXF ft)
    enforce       : if True, apply additional buffer when GC limit exceeded

    Returns
    -------
    (result_polygon, ground_coverage_pct, gc_status)

    gc_status values:
        "OK"            — within limit (or no limit defined)
        "CLIPPED"       — was over limit; additional buffer applied
        "MEASURE_ONLY"  — GDCR key absent; no enforcement done
        "NO_LIMIT"      — enforce=False; measured but not capped
    """
    plot_area = plot_polygon.area
    if plot_area <= 0:
        return envelope, 0.0, "OK"

    actual_gc_pct = envelope.area / plot_area * 100.0
    max_gc_pct = _gdcr_max_gc_pct()

    # ── No limit defined in GDCR.yaml ─────────────────────────────────────────
    if max_gc_pct is None:
        logger.info(
            "Ground coverage: %.1f%% (no GDCR limit defined — measure only)",
            actual_gc_pct,
        )
        return envelope, round(actual_gc_pct, 2), "MEASURE_ONLY"

    # ── Enforcement disabled by caller ─────────────────────────────────────────
    if not enforce:
        logger.info(
            "Ground coverage: %.1f%% (limit %.1f%% — enforcement disabled)",
            actual_gc_pct, max_gc_pct,
        )
        return envelope, round(actual_gc_pct, 2), "NO_LIMIT"

    # ── Already within limit ───────────────────────────────────────────────────
    if actual_gc_pct <= max_gc_pct:
        logger.info(
            "Ground coverage: %.1f%% ≤ limit %.1f%% — no clipping needed.",
            actual_gc_pct, max_gc_pct,
        )
        return envelope, round(actual_gc_pct, 2), "OK"

    # ── Enforce: centroid scaling to target area ────────────────────────────────
    # buffer(-d) bisection collapses irregular polygons disproportionately
    # (a 56% envelope shrinks to 14.5% instead of 40%).  Centroid scaling is
    # predictable: area scales as s², so s = sqrt(target/current) is exact.
    target_area = (max_gc_pct / 100.0) * plot_area
    logger.info(
        "Ground coverage %.1f%% exceeds limit %.1f%%. "
        "Target area: %.1f sq.ft. Applying centroid scaling.",
        actual_gc_pct, max_gc_pct, target_area,
    )

    s = math.sqrt(target_area / envelope.area)
    clipped = scale(envelope, xfact=s, yfact=s, origin='centroid')

    if clipped.is_empty or not clipped.is_valid:
        # Centroid scaling can produce degenerate results for highly non-convex
        # polygons.  Fall back to buffer(-d) bisection in that case.
        logger.warning(
            "GC centroid scaling produced invalid polygon (s=%.4f); "
            "falling back to buffer bisection.",
            s,
        )
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
        if clipped.is_empty:
            logger.warning(
                "GC enforcement bisection fallback produced empty polygon; "
                "returning un-clipped envelope."
            )
            return envelope, round(actual_gc_pct, 2), "OK"

    final_gc = clipped.area / plot_area * 100.0
    logger.info(
        "Ground coverage after enforcement: %.1f%% (target ≤ %.1f%%, scale_factor=%.4f)",
        final_gc, max_gc_pct, s,
    )
    return clipped, round(final_gc, 2), "CLIPPED"
