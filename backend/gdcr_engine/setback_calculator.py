"""
gdcr_engine.setback_calculator
--------------------------------

Setback (margin) calculations per CGDCR 2017.

GDCR References
---------------
    road_side_margin  : Table 6.24
        logic : road_width_based OR height_based, whichever is higher.
        height_formula : H / 5
        minimum_road_side_margin : 1.5 m

    side_rear_margin  : Table 6.26
        based on building height bands.

    inter_building_margin : Table 6.25
        formula : max(H / 3, 3.0)
        applies to parallel facing walls.

All outputs are in metres.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from gdcr_engine.rules_loader import (
    get_road_side_margin_map,
    get_road_side_min_margin,
    get_side_rear_margin_map,
    get_gdcr_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class SetbackRequirements:
    """
    Required setbacks (margins) for a building in metres.

    All values are minimum requirements from GDCR.
    Actual provided values are not stored here; compare against them separately.
    """

    # Road-side (front) margin
    road_margin_table_m: float       # From Table 6.24 (road-width based)
    road_margin_height_m: float      # H / 5 formula
    road_margin_required_m: float    # max(table, height, minimum)

    # Side margin
    side_margin_required_m: float    # From Table 6.26 (height based)

    # Rear margin
    rear_margin_required_m: float    # From Table 6.26 (height based)

    # Inter-building spacing
    inter_building_required_m: float  # max(H/3, 3.0)

    # Inputs used (for traceability)
    road_width_m: float
    building_height_m: float


# ---------------------------------------------------------------------------
# Main calculator
# ---------------------------------------------------------------------------

def compute_setback_requirements(
    *,
    road_width_m: float,
    building_height_m: float,
    debug: bool = False,
) -> SetbackRequirements:
    """
    Compute all required setbacks per GDCR for given road width and height.

    Parameters
    ----------
    road_width_m       : Width of the adjacent road in metres.
    building_height_m  : Proposed building height in metres.
    debug              : Emit GDCR_DEBUG trace lines via logging.

    Returns
    -------
    SetbackRequirements
    """
    road_m = float(road_width_m)
    height_m = float(building_height_m)

    # ── Road-side margin ────────────────────────────────────────────────────
    road_margin_table = _road_side_margin_from_table(road_m)
    road_margin_height = _road_side_margin_from_height(height_m)
    road_margin_min = get_road_side_min_margin()
    road_margin_required = max(road_margin_table, road_margin_height, road_margin_min)

    # ── Side and rear margins ────────────────────────────────────────────────
    side_margin, rear_margin = _side_rear_margin(height_m)

    # ── Inter-building spacing ───────────────────────────────────────────────
    inter_building = _inter_building_margin(height_m)

    result = SetbackRequirements(
        road_margin_table_m=round(road_margin_table, 4),
        road_margin_height_m=round(road_margin_height, 4),
        road_margin_required_m=round(road_margin_required, 4),
        side_margin_required_m=round(side_margin, 4),
        rear_margin_required_m=round(rear_margin, 4),
        inter_building_required_m=round(inter_building, 4),
        road_width_m=road_m,
        building_height_m=height_m,
    )

    if debug:
        logger.info(
            "GDCR_DEBUG:SETBACK_REQUIREMENTS"
            " road_width_m=%.3f building_height_m=%.3f"
            " road_margin_table_m=%.4f road_margin_height_m=%.4f (H/5=%.4f)"
            " road_margin_required_m=%.4f"
            " side_margin_required_m=%.4f rear_margin_required_m=%.4f"
            " inter_building_required_m=%.4f",
            road_m, height_m,
            road_margin_table, road_margin_height, height_m / 5.0,
            road_margin_required,
            side_margin, rear_margin,
            inter_building,
        )

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _road_side_margin_from_table(road_width_m: float) -> float:
    """
    Look up road-side margin from GDCR Table 6.24 (road_width_margin_map).

    Returns the margin for the first entry where road_width_m <= road_max.
    Falls back to the last entry if no threshold is exceeded.
    """
    margin_map = get_road_side_margin_map()
    if not margin_map:
        return 1.5  # absolute minimum fallback

    for entry in margin_map:
        try:
            if road_width_m <= float(entry["road_max"]):
                return float(entry["margin"])
        except (KeyError, TypeError, ValueError):
            continue

    # Fallback: last entry
    try:
        return float(margin_map[-1]["margin"])
    except (KeyError, TypeError, ValueError):
        return 1.5


def _road_side_margin_from_height(building_height_m: float) -> float:
    """
    Compute road-side margin from height formula H/5 (GDCR Table 6.24).

    GDCR.yaml: road_side_margin.height_formula = "H / 5"
    """
    return building_height_m / 5.0


def _side_rear_margin(building_height_m: float) -> tuple[float, float]:
    """
    Look up side and rear margins from GDCR Table 6.26 (height_margin_map).

    Returns (side_margin_m, rear_margin_m).
    """
    margin_map = get_side_rear_margin_map()
    if not margin_map:
        return 3.0, 3.0  # minimum GDCR fallback

    for entry in margin_map:
        try:
            if building_height_m <= float(entry["height_max"]):
                return float(entry["side"]), float(entry["rear"])
        except (KeyError, TypeError, ValueError):
            continue

    # Fallback: last entry
    try:
        last = margin_map[-1]
        return float(last["side"]), float(last["rear"])
    except (KeyError, TypeError, ValueError):
        return 8.0, 8.0


def _inter_building_margin(building_height_m: float) -> float:
    """
    Compute inter-building margin from GDCR Table 6.25.

    Preferred mode (when configured):
        height_spacing_map lookup by building height.

    Fallback mode:
        max(H / 3, minimum_spacing_m)
    """
    try:
        gdcr = get_gdcr_config()
        inter_cfg = gdcr.get("inter_building_margin", {}) or {}
        minimum_m = float(inter_cfg.get("minimum_spacing_m", 3.0))
        spacing_map = inter_cfg.get("height_spacing_map") or []
        if spacing_map:
            for entry in spacing_map:
                try:
                    if building_height_m <= float(entry["height_max"]):
                        return max(float(entry["margin"]), minimum_m)
                except (KeyError, TypeError, ValueError):
                    continue
            try:
                return max(float(spacing_map[-1]["margin"]), minimum_m)
            except (KeyError, TypeError, ValueError):
                pass
    except Exception:
        minimum_m = 3.0

    return max(building_height_m / 3.0, minimum_m)


def validate_setbacks(
    *,
    required: SetbackRequirements,
    provided_road_margin_m: Optional[float] = None,
    provided_side_margin_m: Optional[float] = None,
    provided_rear_margin_m: Optional[float] = None,
    provided_inter_building_m: Optional[float] = None,
    debug: bool = False,
) -> list[dict]:
    """
    Compare provided setbacks against GDCR requirements.

    Returns a list of validation result dicts, one per checked dimension.
    Each dict: {"dimension", "required_m", "provided_m", "passed", "message"}
    """
    results = []

    checks = [
        (
            "road_margin",
            required.road_margin_required_m,
            provided_road_margin_m,
            "Road-side (front) margin",
        ),
        (
            "side_margin",
            required.side_margin_required_m,
            provided_side_margin_m,
            "Side margin",
        ),
        (
            "rear_margin",
            required.rear_margin_required_m,
            provided_rear_margin_m,
            "Rear margin",
        ),
        (
            "inter_building",
            required.inter_building_required_m,
            provided_inter_building_m,
            "Inter-building spacing",
        ),
    ]

    for dim, req, prov, label in checks:
        if prov is None:
            results.append({
                "dimension": dim,
                "required_m": req,
                "provided_m": None,
                "passed": None,
                "message": f"{label}: required >= {req:.3f} m (not provided — manual check needed).",
            })
        else:
            passed = float(prov) >= req - 1e-6
            msg = (
                f"{label}: OK ({prov:.3f} m >= {req:.3f} m)"
                if passed
                else f"{label}: FAIL ({prov:.3f} m < required {req:.3f} m)"
            )
            results.append({
                "dimension": dim,
                "required_m": req,
                "provided_m": float(prov),
                "passed": passed,
                "message": msg,
            })

    if debug:
        for r in results:
            logger.info(
                "GDCR_DEBUG:SETBACK_CHECK dimension=%s required_m=%.4f provided_m=%s passed=%s",
                r["dimension"], r["required_m"],
                f"{r['provided_m']:.4f}" if r["provided_m"] is not None else "None",
                r["passed"],
            )

    return results
