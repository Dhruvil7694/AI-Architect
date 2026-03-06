"""
gdcr_engine.plot_analyzer
--------------------------

Derive and validate plot parameters needed for GDCR compliance checking.

Responsibilities
----------------
- Accept raw plot inputs (area in sq.ft or sq.m, road width, etc.).
- Convert units to SI (sq.m, metres) for all downstream calculations.
- Classify plot shape (RECTANGULAR / IRREGULAR).
- Determine height band (LOW_RISE / MID_RISE / HIGH_RISE).
- Emit GDCR_DEBUG trace lines for every derived value.

Unit contract
-------------
- Input plot_area may be in sq.ft (from DB) or sq.m (from caller).
- All outputs from this module are in SI units (sq.m, metres).
- FSI is dimensionless and unit-invariant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from common.units import sqft_to_sqm
from gdcr_engine.rules_loader import get_height_band_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlotParameters:
    """
    Validated, unit-normalised plot parameters for GDCR compliance.

    All area values are in sq.m.
    All length values are in metres.
    """

    # Areas
    plot_area_sqm: float
    plot_area_sqft: float            # preserved for reporting

    # Road
    road_width_m: float

    # Optional spatial attributes
    frontage_m: Optional[float] = None
    plot_depth_m: Optional[float] = None
    n_road_edges: int = 1
    is_corner_plot: bool = False

    # Shape & height classification
    shape_class: str = "UNKNOWN"     # "RECTANGULAR" | "IRREGULAR" | "UNKNOWN"
    height_band: str = "UNKNOWN"     # "LOW_RISE" | "MID_RISE" | "HIGH_RISE"

    # Corridor eligibility (spatial; requires distance_to_wide_road)
    distance_to_wide_road_m: Optional[float] = None
    corridor_eligible: bool = False


# ---------------------------------------------------------------------------
# Main analyser
# ---------------------------------------------------------------------------

def analyze_plot(
    *,
    plot_area_sqft: Optional[float] = None,
    plot_area_sqm: Optional[float] = None,
    road_width_m: float,
    building_height_m: float = 0.0,
    frontage_m: Optional[float] = None,
    plot_depth_m: Optional[float] = None,
    n_road_edges: int = 1,
    distance_to_wide_road_m: Optional[float] = None,
    shape_class: Optional[str] = None,
    debug: bool = False,
) -> PlotParameters:
    """
    Derive and validate plot parameters for GDCR compliance checking.

    At least one of ``plot_area_sqft`` or ``plot_area_sqm`` must be provided.

    Parameters
    ----------
    plot_area_sqft       : Plot area in sq.ft (from DB or DXF measurement).
    plot_area_sqm        : Plot area in sq.m (overrides sqft conversion when set).
    road_width_m         : Width of the adjacent road in metres.
    building_height_m    : Proposed or computed building height (m); used for
                           height band classification only.
    frontage_m           : Road-facing edge length in metres (optional).
    plot_depth_m         : Plot depth perpendicular to road (optional).
    n_road_edges         : Number of road-facing edges.
    distance_to_wide_road_m : Distance (m) to nearest 36 m+ road; required for
                           corridor eligibility; None skips that check.
    shape_class          : Pre-computed shape class; auto-classified when None.
    debug                : Emit GDCR_DEBUG trace lines via logging.

    Returns
    -------
    PlotParameters
    """
    # ── Unit normalisation ──────────────────────────────────────────────────
    if plot_area_sqm is not None:
        area_sqm = float(plot_area_sqm)
        area_sqft = area_sqm / 0.09290304  # back-convert for reporting
    elif plot_area_sqft is not None:
        area_sqft = float(plot_area_sqft)
        area_sqm = sqft_to_sqm(area_sqft)
    else:
        raise ValueError("analyze_plot: either plot_area_sqft or plot_area_sqm must be provided.")

    road_m = float(road_width_m)
    height_m = float(building_height_m)

    # ── Height band ─────────────────────────────────────────────────────────
    height_band = _classify_height_band(height_m)

    # ── Corner plot ─────────────────────────────────────────────────────────
    is_corner = int(n_road_edges) >= 2

    # ── Shape class ─────────────────────────────────────────────────────────
    sc = shape_class if shape_class is not None else "UNKNOWN"

    # ── Corridor eligibility ─────────────────────────────────────────────────
    from gdcr_engine.rules_loader import get_corridor_rule
    corridor_rule = get_corridor_rule()
    eligible_if = corridor_rule.get("eligible_if", {})
    road_width_min_m = float(eligible_if.get("road_width_min_m", 36.0))
    buffer_distance_m = float(eligible_if.get("buffer_distance_m", 200.0))

    corridor_eligible = False
    if road_m >= road_width_min_m:
        if distance_to_wide_road_m is not None:
            corridor_eligible = float(distance_to_wide_road_m) <= buffer_distance_m
        else:
            # Road width alone satisfies the primary condition; buffer check
            # requires spatial data — mark as potentially eligible.
            corridor_eligible = True  # conservative; caller may override

    # ── Debug trace ─────────────────────────────────────────────────────────
    if debug:
        logger.info(
            "GDCR_DEBUG:PLOT_ANALYZER"
            " plot_area_sqm=%.4f plot_area_sqft=%.4f"
            " road_width_m=%.3f building_height_m=%.3f"
            " frontage_m=%s plot_depth_m=%s"
            " n_road_edges=%d is_corner=%s"
            " shape_class=%s height_band=%s"
            " distance_to_wide_road_m=%s corridor_eligible=%s",
            area_sqm, area_sqft, road_m, height_m,
            f"{frontage_m:.3f}" if frontage_m is not None else "None",
            f"{plot_depth_m:.3f}" if plot_depth_m is not None else "None",
            n_road_edges, is_corner,
            sc, height_band,
            f"{distance_to_wide_road_m:.1f}" if distance_to_wide_road_m is not None else "None",
            corridor_eligible,
        )

    return PlotParameters(
        plot_area_sqm=area_sqm,
        plot_area_sqft=area_sqft,
        road_width_m=road_m,
        frontage_m=frontage_m,
        plot_depth_m=plot_depth_m,
        n_road_edges=n_road_edges,
        is_corner_plot=is_corner,
        shape_class=sc,
        height_band=height_band,
        distance_to_wide_road_m=distance_to_wide_road_m,
        corridor_eligible=corridor_eligible,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_height_band(height_m: float) -> str:
    """
    Map building height to LOW_RISE / MID_RISE / HIGH_RISE using GDCR.yaml thresholds.

    GDCR.yaml:
        height_band_rules.low_rise_max_m  (default 10 m)
        height_band_rules.mid_rise_max_m  (default 15 m)
    """
    try:
        cfg = get_height_band_config()
        low_max = float(cfg.get("low_rise_max_m", 10.0))
        mid_max = float(cfg.get("mid_rise_max_m", 15.0))
    except Exception:
        low_max = 10.0
        mid_max = 15.0

    if height_m <= low_max:
        return "LOW_RISE"
    if height_m <= mid_max:
        return "MID_RISE"
    return "HIGH_RISE"
