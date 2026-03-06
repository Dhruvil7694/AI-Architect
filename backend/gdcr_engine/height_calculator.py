"""
gdcr_engine.height_calculator
------------------------------

Building height limit calculations per CGDCR 2017.

GDCR References
---------------
    height_rules.road_width_height_map  : Table 6.23
        road_max <= 9   → max_height 10 m
        road_max <= 12  → max_height 16.5 m
        road_max <= 18  → max_height 30 m
        road_max <= 36  → max_height 45 m
        road_max <= 999 → max_height 70 m

    access_rules:
        minimum_road_width_for_dw3 : 9 m
        if road < 9 m → DW3 not permitted, max_height capped at 10 m

Derived height limits
---------------------
    h_road_cap  : from road_width_height_map (absolute GDCR cap)
    h_fsi_limit : max_floors * storey_height, where
                  max_floors = floor(max_bua / footprint_area)
    h_effective : min(h_road_cap, h_fsi_limit)  — practical maximum

All outputs in metres.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import floor
from typing import Optional

from gdcr_engine.rules_loader import (
    get_height_map,
    get_min_road_width_dw3,
    get_gdcr_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class HeightLimits:
    """
    All height constraints applicable to a building.

    All values in metres.
    The controlling_constraint field names the most restrictive constraint.
    """

    # Road-width cap (GDCR Table 6.23)
    h_road_cap_m: float

    # DW3 access restriction cap (if road_width < 9 m)
    dw3_permitted: bool
    h_dw3_restriction_m: Optional[float]   # 10.0 if road < 9 m, else None

    # FSI-derived height limit
    h_fsi_limit_m: Optional[float]         # None if footprint area not provided
    max_floors_fsi: Optional[int]          # Floor count limited by FSI

    # Effective maximum height (most restrictive of all limits)
    h_effective_m: float
    controlling_constraint: str            # "ROAD_WIDTH_CAP" | "FSI_LIMIT" | "DW3_ACCESS"

    # Derived storey count at effective height
    max_floors: int
    storey_height_m: float

    # Inputs (for traceability)
    road_width_m: float


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------

def compute_height_limits(
    *,
    road_width_m: float,
    plot_area_sqm: Optional[float] = None,
    footprint_area_sqm: Optional[float] = None,
    max_fsi: Optional[float] = None,
    storey_height_m: float = 3.0,
    debug: bool = False,
) -> HeightLimits:
    """
    Compute all applicable height limits for a building.

    Parameters
    ----------
    road_width_m       : Width of the adjacent road in metres.
    plot_area_sqm      : Net plot area (sq.m); required for FSI-based limit.
    footprint_area_sqm : Tower footprint area (sq.m); required for FSI limit.
    max_fsi            : Applicable maximum FSI; if None, FSI limit is not computed.
    storey_height_m    : Storey height assumed for floor-count conversion.
    debug              : Emit GDCR_DEBUG trace lines.

    Returns
    -------
    HeightLimits
    """
    road_m = float(road_width_m)

    # ── Road-width cap (Table 6.23) ──────────────────────────────────────────
    h_road_cap = _height_from_road_width(road_m)

    # ── DW3 access restriction ───────────────────────────────────────────────
    min_rw_dw3 = get_min_road_width_dw3()
    dw3_permitted = road_m >= min_rw_dw3
    h_dw3_restriction: Optional[float] = None
    if not dw3_permitted:
        # Per GDCR access_rules.if_road_width_less_than_9.max_height
        try:
            gdcr = get_gdcr_config()
            h_dw3_restriction = float(
                gdcr["access_rules"]["if_road_width_less_than_9"]["max_height"]
            )
        except (KeyError, TypeError, ValueError):
            h_dw3_restriction = 10.0

    # ── FSI-derived height limit ─────────────────────────────────────────────
    h_fsi_limit: Optional[float] = None
    max_floors_fsi: Optional[int] = None

    if (
        plot_area_sqm is not None
        and footprint_area_sqm is not None
        and max_fsi is not None
        and plot_area_sqm > 0
        and footprint_area_sqm > 0
    ):
        max_bua = max_fsi * plot_area_sqm
        mf = floor(max_bua / footprint_area_sqm)
        max_floors_fsi = mf
        h_fsi_limit = mf * storey_height_m if mf > 0 else 0.0

    # ── Effective maximum height ─────────────────────────────────────────────
    candidates = [h_road_cap]
    if h_dw3_restriction is not None:
        candidates.append(h_dw3_restriction)
    if h_fsi_limit is not None:
        candidates.append(h_fsi_limit)
    h_effective = min(candidates)

    # ── Controlling constraint ────────────────────────────────────────────────
    if not dw3_permitted and h_dw3_restriction is not None and h_effective <= h_dw3_restriction + 1e-6:
        controlling = "DW3_ACCESS"
    elif h_fsi_limit is not None and h_effective <= h_fsi_limit + 1e-6 and h_fsi_limit < h_road_cap - 1e-6:
        controlling = "FSI_LIMIT"
    else:
        controlling = "ROAD_WIDTH_CAP"

    # ── Floor count at effective height ─────────────────────────────────────
    max_floors = max(0, floor(h_effective / storey_height_m)) if h_effective > 0 else 0

    result = HeightLimits(
        h_road_cap_m=round(h_road_cap, 4),
        dw3_permitted=dw3_permitted,
        h_dw3_restriction_m=h_dw3_restriction,
        h_fsi_limit_m=round(h_fsi_limit, 4) if h_fsi_limit is not None else None,
        max_floors_fsi=max_floors_fsi,
        h_effective_m=round(h_effective, 4),
        controlling_constraint=controlling,
        max_floors=max_floors,
        storey_height_m=storey_height_m,
        road_width_m=road_m,
    )

    if debug:
        logger.info(
            "GDCR_DEBUG:HEIGHT_LIMITS"
            " road_width_m=%.3f h_road_cap_m=%.4f"
            " dw3_permitted=%s h_dw3_restriction_m=%s"
            " h_fsi_limit_m=%s max_floors_fsi=%s"
            " h_effective_m=%.4f max_floors=%d"
            " controlling_constraint=%s storey_height_m=%.3f",
            road_m, h_road_cap,
            dw3_permitted,
            f"{h_dw3_restriction:.4f}" if h_dw3_restriction is not None else "None",
            f"{h_fsi_limit:.4f}" if h_fsi_limit is not None else "None",
            str(max_floors_fsi),
            h_effective, max_floors,
            controlling, storey_height_m,
        )

    return result


def get_height_band(height_m: float) -> str:
    """
    Map building height to LOW_RISE / MID_RISE / HIGH_RISE using GDCR.yaml thresholds.

    Delegates to plot_analyzer._classify_height_band to keep a single definition.
    """
    from gdcr_engine.plot_analyzer import _classify_height_band
    return _classify_height_band(height_m)


def compute_storey_count(
    height_m: float,
    storey_height_m: float = 3.0,
) -> int:
    """
    Compute number of full storeys for a given height and storey height.

    Formula: max(0, floor(height_m / storey_height_m))
    """
    if storey_height_m <= 0:
        raise ValueError("storey_height_m must be positive.")
    return max(0, floor(height_m / storey_height_m))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _height_from_road_width(road_width_m: float) -> float:
    """
    Return max permissible building height from GDCR Table 6.23.

    Finds first entry where road_width_m <= road_max and returns max_height.
    Falls back to last entry if no threshold matches.
    Returns infinity if map is empty (permissive fallback).
    """
    height_map = get_height_map()
    if not height_map:
        return float("inf")

    for entry in height_map:
        try:
            if road_width_m <= float(entry["road_max"]):
                return float(entry["max_height"])
        except (KeyError, TypeError, ValueError):
            continue

    try:
        return float(height_map[-1]["max_height"])
    except (KeyError, TypeError, ValueError):
        return float("inf")
