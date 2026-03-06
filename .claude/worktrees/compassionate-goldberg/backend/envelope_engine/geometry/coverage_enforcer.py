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

from shapely.geometry import Polygon

from rules_engine.rules.loader import get_gdcr_config

logger = logging.getLogger(__name__)

# Bisection parameters for GC enforcement
_BISECT_ITERATIONS = 20
_BISECT_TOLERANCE  = 1e-4   # DXF feet (< 0.03 mm — more than adequate)


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

    # ── Enforce: bisect to find minimum additional buffer distance ─────────────
    target_area = (max_gc_pct / 100.0) * plot_area
    logger.info(
        "Ground coverage %.1f%% exceeds limit %.1f%%. "
        "Target area: %.1f sq.ft. Bisecting additional buffer.",
        actual_gc_pct, max_gc_pct, target_area,
    )

    lo, hi = 0.0, max(envelope.bounds[2] - envelope.bounds[0],
                       envelope.bounds[3] - envelope.bounds[1]) / 2.0

    clipped = envelope
    for _ in range(_BISECT_ITERATIONS):
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
        if (hi - lo) < _BISECT_TOLERANCE:
            break

    if clipped.is_empty:
        # Extreme case: even maximum buffer empties the polygon — return original
        logger.warning(
            "GC enforcement bisection produced empty polygon; "
            "returning un-clipped envelope."
        )
        return envelope, round(actual_gc_pct, 2), "OK"

    final_gc = clipped.area / plot_area * 100.0
    logger.info(
        "Ground coverage after clipping: %.1f%% (target ≤ %.1f%%)",
        final_gc, max_gc_pct,
    )
    return clipped, round(final_gc, 2), "CLIPPED"
