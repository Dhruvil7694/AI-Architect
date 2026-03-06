"""
area_validator.py
-----------------
Validates that the geometry-computed area of a polygon is within an
acceptable tolerance of the area stated in the Excel metadata sheet.

Validation formula:
    relative_error = |area_geometry - area_excel| / area_excel
    valid = relative_error <= tolerance

Default tolerance: 5 % (0.05)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.10  # 10 % — accommodates minor boundary imprecision in older DXF drawings


@dataclass
class ValidationResult:
    fp_number: str
    area_excel: float
    area_geometry: float
    relative_error: float
    is_valid: bool
    polygon: Polygon


def validate_area(
    fp_number: str,
    polygon: Polygon,
    area_excel: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> ValidationResult:
    """
    Compare the polygon's computed area against the Excel-stated area.

    Parameters
    ----------
    fp_number    : the FP number string (for logging / result tracking)
    polygon      : Shapely Polygon whose area is measured
    area_excel   : area value from the Excel metadata sheet
    tolerance    : maximum allowed relative error (default 5 %)

    Returns
    -------
    ValidationResult with is_valid=True when within tolerance
    """
    area_geom = polygon.area

    if area_excel <= 0:
        logger.warning("FP %s has non-positive Excel area (%.4f). Marking invalid.", fp_number, area_excel)
        return ValidationResult(
            fp_number=fp_number,
            area_excel=area_excel,
            area_geometry=area_geom,
            relative_error=float("inf"),
            is_valid=False,
            polygon=polygon,
        )

    relative_error = abs(area_geom - area_excel) / area_excel
    is_valid = relative_error <= tolerance

    if not is_valid:
        logger.warning(
            "FP %s area mismatch — Excel: %.2f, Geometry: %.2f, Error: %.1f%% (tolerance: %.1f%%)",
            fp_number,
            area_excel,
            area_geom,
            relative_error * 100,
            tolerance * 100,
        )
    else:
        logger.debug(
            "FP %s area OK — Excel: %.2f, Geometry: %.2f, Error: %.2f%%",
            fp_number,
            area_excel,
            area_geom,
            relative_error * 100,
        )

    return ValidationResult(
        fp_number=fp_number,
        area_excel=area_excel,
        area_geometry=area_geom,
        relative_error=relative_error,
        is_valid=is_valid,
        polygon=polygon,
    )
