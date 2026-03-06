"""
gdcr_engine.fsi_calculator
---------------------------

FSI (Floor Space Index) and BUA (Built-Up Area) calculations per CGDCR 2017.

GDCR Reference
--------------
    Table 6.8, R1 zone, DW3 (Apartments):
        base_fsi               = 1.8
        tier 1 resulting_cap   = 2.7   (jantri 40%, no corridor)
        tier 2 resulting_cap   = 3.6   (jantri 40%, corridor required)
        tier 3 resulting_cap   = 4.0   (jantri 40%, corridor required)

    Corridor eligibility (eligible_if):
        road_width_min_m   >= 36 m
        buffer_distance_m  <= 200 m (from a 36 m or 45 m road)

Formulas
--------
    achieved_fsi     = total_bua_sqm / plot_area_sqm        (dimensionless)
    max_bua_sqm      = max_fsi * plot_area_sqm

FSI Exclusions (GDCR fsi_exclusions section)
--------------------------------------------
    The following areas are EXCLUDED from FSI computation:
        - Staircase (formula-based)
        - Lift well (formula-based)
        - Parking floors (100% excluded)
        - Refuge area (triggered above 25 m height)
        - Open-to-sky spaces
        - Loft (max 30% of floor area, height <= 1.2 m)

    NOTE: The current engine computes BUA as footprint * floors, which is a
    gross BUA estimate.  FSI exclusions reduce the effective counted BUA.
    Where exclusion-adjusted BUA is needed, use compute_adjusted_bua().

Units
-----
    All calculations in sq.m.
    FSI is dimensionless.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import floor
from typing import Optional, Tuple

from gdcr_engine.rules_loader import get_base_fsi, get_fsi_tiers, get_corridor_rule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FSIParameters:
    """
    GDCR FSI configuration for a specific plot/road context.

    All FSI values are dimensionless.
    All area values are in sq.m.
    """

    base_fsi: float
    max_fsi_non_corridor: float       # Highest tier not requiring corridor
    max_fsi_with_corridor: float      # Highest tier (corridor required)
    applicable_max_fsi: float         # Determined by corridor_eligible flag
    corridor_eligible: bool

    # Derived BUA limits (sq.m)
    max_bua_base_sqm: float           # = base_fsi * plot_area_sqm
    max_bua_applicable_sqm: float     # = applicable_max_fsi * plot_area_sqm
    max_bua_absolute_sqm: float       # = max_fsi_with_corridor * plot_area_sqm

    plot_area_sqm: float


@dataclass
class AchievedFSI:
    """Result of comparing achieved BUA against GDCR FSI limits."""

    plot_area_sqm: float
    total_bua_sqm: float
    achieved_fsi: float               # = total_bua_sqm / plot_area_sqm
    base_fsi: float
    applicable_max_fsi: float

    # Utilisation percentages
    base_fsi_utilization_pct: float   # achieved_fsi / base_fsi * 100
    max_fsi_utilization_pct: float    # achieved_fsi / applicable_max_fsi * 100

    # Headroom
    remaining_bua_sqm: float          # max_bua - total_bua (if positive)
    exceeds_base: bool
    exceeds_max: bool


# ---------------------------------------------------------------------------
# Main calculators
# ---------------------------------------------------------------------------

def compute_fsi_parameters(
    *,
    plot_area_sqm: float,
    corridor_eligible: bool = False,
    debug: bool = False,
) -> FSIParameters:
    """
    Compute GDCR FSI parameters for a given plot area and corridor eligibility.

    Parameters
    ----------
    plot_area_sqm    : Net plot area in sq.m.
    corridor_eligible: True if the plot is within 200 m of a road >= 36 m wide.
    debug            : Emit GDCR_DEBUG trace lines via logging.

    Returns
    -------
    FSIParameters
    """
    base = get_base_fsi()
    tiers = get_fsi_tiers()

    # Determine non-corridor max FSI: highest tier where corridor_required is False
    # (or absent).  If all tiers require a corridor, fall back to base.
    non_corridor_caps = [
        float(t.get("resulting_cap", 0.0))
        for t in tiers
        if not t.get("corridor_required", False)
    ]
    max_fsi_non_corridor = max(non_corridor_caps) if non_corridor_caps else base

    # Determine corridor max FSI: highest resulting_cap across ALL tiers.
    all_caps = [float(t.get("resulting_cap", 0.0)) for t in tiers]
    max_fsi_with_corridor = max(all_caps) if all_caps else base

    applicable_max_fsi = max_fsi_with_corridor if corridor_eligible else max_fsi_non_corridor

    max_bua_base = base * plot_area_sqm
    max_bua_applicable = applicable_max_fsi * plot_area_sqm
    max_bua_absolute = max_fsi_with_corridor * plot_area_sqm

    if debug:
        logger.info(
            "GDCR_DEBUG:FSI_PARAMETERS"
            " plot_area_sqm=%.4f corridor_eligible=%s"
            " base_fsi=%.2f max_fsi_non_corridor=%.2f max_fsi_with_corridor=%.2f"
            " applicable_max_fsi=%.2f"
            " max_bua_base_sqm=%.4f max_bua_applicable_sqm=%.4f max_bua_absolute_sqm=%.4f",
            plot_area_sqm, corridor_eligible,
            base, max_fsi_non_corridor, max_fsi_with_corridor,
            applicable_max_fsi,
            max_bua_base, max_bua_applicable, max_bua_absolute,
        )

    return FSIParameters(
        base_fsi=base,
        max_fsi_non_corridor=max_fsi_non_corridor,
        max_fsi_with_corridor=max_fsi_with_corridor,
        applicable_max_fsi=applicable_max_fsi,
        corridor_eligible=corridor_eligible,
        max_bua_base_sqm=round(max_bua_base, 4),
        max_bua_applicable_sqm=round(max_bua_applicable, 4),
        max_bua_absolute_sqm=round(max_bua_absolute, 4),
        plot_area_sqm=plot_area_sqm,
    )


def compute_achieved_fsi(
    *,
    plot_area_sqm: float,
    total_bua_sqm: float,
    corridor_eligible: bool = False,
    debug: bool = False,
) -> AchievedFSI:
    """
    Compare achieved BUA against GDCR FSI limits.

    Parameters
    ----------
    plot_area_sqm  : Net plot area in sq.m.
    total_bua_sqm  : Total counted BUA in sq.m (gross, before exclusions).
    corridor_eligible : True if corridor bonus FSI is available.
    debug          : Emit GDCR_DEBUG trace lines.

    Returns
    -------
    AchievedFSI with utilisation flags and headroom.
    """
    fsi_params = compute_fsi_parameters(
        plot_area_sqm=plot_area_sqm,
        corridor_eligible=corridor_eligible,
        debug=debug,
    )

    if plot_area_sqm <= 0.0:
        achieved = 0.0
    else:
        achieved = total_bua_sqm / plot_area_sqm

    base_util = (achieved / fsi_params.base_fsi * 100.0) if fsi_params.base_fsi > 0 else 0.0
    max_util = (achieved / fsi_params.applicable_max_fsi * 100.0) if fsi_params.applicable_max_fsi > 0 else 0.0

    remaining = fsi_params.max_bua_applicable_sqm - total_bua_sqm

    result = AchievedFSI(
        plot_area_sqm=plot_area_sqm,
        total_bua_sqm=round(total_bua_sqm, 4),
        achieved_fsi=round(achieved, 4),
        base_fsi=fsi_params.base_fsi,
        applicable_max_fsi=fsi_params.applicable_max_fsi,
        base_fsi_utilization_pct=round(base_util, 2),
        max_fsi_utilization_pct=round(max_util, 2),
        remaining_bua_sqm=round(remaining, 4),
        exceeds_base=achieved > fsi_params.base_fsi + 1e-6,
        exceeds_max=achieved > fsi_params.applicable_max_fsi + 1e-6,
    )

    if debug:
        logger.info(
            "GDCR_DEBUG:ACHIEVED_FSI"
            " plot_area_sqm=%.4f total_bua_sqm=%.4f"
            " achieved_fsi=%.4f base_fsi=%.2f applicable_max_fsi=%.2f"
            " base_fsi_util_pct=%.2f max_fsi_util_pct=%.2f"
            " remaining_bua_sqm=%.4f exceeds_base=%s exceeds_max=%s",
            plot_area_sqm, total_bua_sqm,
            result.achieved_fsi, result.base_fsi, result.applicable_max_fsi,
            result.base_fsi_utilization_pct, result.max_fsi_utilization_pct,
            result.remaining_bua_sqm, result.exceeds_base, result.exceeds_max,
        )

    return result


def estimate_bua_from_footprint(
    *,
    footprint_area_sqm: float,
    building_height_m: float,
    storey_height_m: float = 3.0,
) -> Tuple[int, float]:
    """
    Estimate gross BUA from footprint area and building height.

    Formula:
        num_floors = max(1, floor(building_height_m / storey_height_m))
        gross_bua_sqm = footprint_area_sqm * num_floors

    This is a gross estimate; FSI exclusions (staircase, parking, lift well)
    will reduce the counted BUA for regulatory purposes.

    Returns
    -------
    (num_floors, gross_bua_sqm)
    """
    if storey_height_m <= 0:
        raise ValueError("storey_height_m must be positive.")
    num_floors = max(1, floor(building_height_m / storey_height_m))
    gross_bua = footprint_area_sqm * num_floors
    return num_floors, round(gross_bua, 4)


def compute_max_floors_from_fsi(
    *,
    plot_area_sqm: float,
    footprint_area_sqm: float,
    max_fsi: float,
    storey_height_m: float = 3.0,
) -> Tuple[int, float]:
    """
    Derive maximum number of floors constrained by FSI and footprint.

    Formula:
        max_bua_sqm  = max_fsi * plot_area_sqm
        max_floors   = floor(max_bua_sqm / footprint_area_sqm)
        h_fsi_limit  = max_floors * storey_height_m

    Returns
    -------
    (max_floors, height_limit_m)  — (0, 0.0) when footprint >= max_bua.
    """
    if footprint_area_sqm <= 0 or plot_area_sqm <= 0:
        return 0, 0.0
    max_bua = max_fsi * plot_area_sqm
    max_floors = floor(max_bua / footprint_area_sqm)
    height_limit = max_floors * storey_height_m
    return max_floors, round(height_limit, 4)


def debug_fsi_trace(
    *,
    plot_area_sqm: float,
    road_width_m: float,
    max_fsi: float,
    total_bua_sqm: float,
    achieved_fsi: float,
    max_bua_sqm: float,
) -> str:
    """
    Return a formatted GDCR_DEBUG trace string for FSI values.

    Example output:
        GDCR_DEBUG:
          plot_area_sqm=3678.5320
          road_width_m=60.000
          max_fsi=4.0
          max_bua_sqm=14714.1280
          total_bua_sqm=12450.0000
          achieved_fsi=3.3842
    """
    return (
        "GDCR_DEBUG:\n"
        f"  plot_area_sqm={plot_area_sqm:.4f}\n"
        f"  road_width_m={road_width_m:.3f}\n"
        f"  max_fsi={max_fsi}\n"
        f"  max_bua_sqm={max_bua_sqm:.4f}\n"
        f"  total_bua_sqm={total_bua_sqm:.4f}\n"
        f"  achieved_fsi={achieved_fsi:.4f}"
    )
