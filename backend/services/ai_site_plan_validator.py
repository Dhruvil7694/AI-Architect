"""
services/ai_site_plan_validator.py
-----------------------------------
Validate an AI-generated tower layout against GDCR constraints.

Returns a list of human-readable error strings. Empty list = valid.
Errors are fed back to GPT on retry so it can self-correct.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

from shapely.geometry import Polygon, box
from shapely.affinity import rotate as shapely_rotate

from common.units import METRES_TO_DXF, DXF_TO_METRES
from placement_engine.geometry.spacing_enforcer import required_spacing_m
from placement_engine.geometry.core_fit import validate_core_fit

logger = logging.getLogger(__name__)

MIN_TOWER_DIM_M = 12.0


def _build_tower_polygon_m(tower: Dict[str, Any]) -> Polygon:
    """Build a Shapely polygon in metres from an AI tower dict."""
    cx = float(tower["centerX"])
    cy = float(tower["centerY"])
    w = float(tower["widthM"])
    d = float(tower["depthM"])
    half_w, half_d = w / 2.0, d / 2.0
    rect = box(cx - half_w, cy - half_d, cx + half_w, cy + half_d)
    orientation = float(tower.get("orientationDeg", 0))
    if abs(orientation) > 0.01:
        rect = shapely_rotate(rect, orientation, origin="centroid", use_radians=False)
    return rect


def validate_ai_site_plan(
    ai_result: Dict[str, Any],
    context: Dict[str, Any],
) -> List[str]:
    """
    Validate AI-generated tower layout.

    Parameters
    ----------
    ai_result : parsed JSON from GPT with "towers" list
    context   : same context dict passed to the prompt builder, containing
                envelope_polygon (Shapely, DXF feet), plot_area_sqm, max_bua_sqm,
                building_height_m, storey_height_m, max_floors, spacing_required_m,
                ground_coverage_pct

    Returns
    -------
    List of error strings (empty = all checks pass)
    """
    errors: List[str] = []

    towers = ai_result.get("towers")
    if not towers or not isinstance(towers, list):
        return ["Missing or empty 'towers' array in AI response."]

    for i, t in enumerate(towers):
        tid = t.get("id", f"T{i+1}")
        for key in ("centerX", "centerY", "widthM", "depthM", "floors"):
            if key not in t:
                errors.append(f"{tid}: missing required field '{key}'.")
        try:
            w = float(t.get("widthM", 0))
            d = float(t.get("depthM", 0))
            if w < MIN_TOWER_DIM_M:
                errors.append(f"{tid}: widthM={w:.1f}m < minimum {MIN_TOWER_DIM_M}m.")
            if d < MIN_TOWER_DIM_M:
                errors.append(f"{tid}: depthM={d:.1f}m < minimum {MIN_TOWER_DIM_M}m.")
        except (TypeError, ValueError):
            errors.append(f"{tid}: widthM/depthM must be numeric.")

        try:
            floors = int(t.get("floors", 0))
            max_floors = int(context.get("max_floors", 99))
            if floors < 1:
                errors.append(f"{tid}: floors={floors} must be >= 1.")
            elif floors > max_floors:
                errors.append(f"{tid}: floors={floors} exceeds max_floors={max_floors}.")
        except (TypeError, ValueError):
            errors.append(f"{tid}: floors must be an integer.")

    if errors:
        return errors

    envelope_poly = context.get("envelope_polygon")
    if envelope_poly is None:
        return errors

    ox_dxf = float(context.get("_origin_x_dxf", 0))
    oy_dxf = float(context.get("_origin_y_dxf", 0))
    envelope_m = _shapely_dxf_to_local_metres(envelope_poly, ox_dxf, oy_dxf)
    building_height_m = float(context.get("building_height_m", 30))
    storey_height_m = float(context.get("storey_height_m", 3.0))
    spacing_m = float(context.get("spacing_required_m", required_spacing_m(building_height_m)))
    max_bua_sqm = float(context.get("max_bua_sqm", 0))
    plot_area_sqm = float(context.get("plot_area_sqm", 0))
    gc_limit_pct = float(context.get("ground_coverage_pct", 100))

    tower_polys_m: List[Polygon] = []
    total_bua_sqm = 0.0
    total_footprint_sqm = 0.0

    for i, t in enumerate(towers):
        tid = t.get("id", f"T{i+1}")
        poly_m = _build_tower_polygon_m(t)
        tower_polys_m.append(poly_m)

        if not envelope_m.contains(poly_m):
            overlap = poly_m.intersection(envelope_m).area
            coverage_pct = (overlap / poly_m.area * 100) if poly_m.area > 0 else 0
            if coverage_pct < 90.0:
                errors.append(
                    f"{tid}: footprint extends outside envelope "
                    f"(only {coverage_pct:.0f}% contained). "
                    f"Move center inward or reduce dimensions."
                )

        floors = int(t["floors"])
        fp_area = poly_m.area
        total_footprint_sqm += fp_area
        total_bua_sqm += fp_area * floors

        w_m = float(t["widthM"])
        d_m = float(t["depthM"])
        height_m = floors * storey_height_m
        core_result = validate_core_fit(w_m, d_m, height_m)
        if core_result.core_fit_status != "VALID":
            errors.append(
                f"{tid}: core fit check failed ({core_result.selected_pattern}). "
                f"Footprint {w_m:.1f}x{d_m:.1f}m cannot accommodate "
                f"building core at {floors} floors."
            )

    if len(tower_polys_m) >= 2:
        for i in range(len(tower_polys_m)):
            for j in range(i + 1, len(tower_polys_m)):
                gap = tower_polys_m[i].distance(tower_polys_m[j])
                if gap < spacing_m - 0.5:
                    errors.append(
                        f"T{i+1}-T{j+1}: spacing={gap:.1f}m < required {spacing_m:.1f}m. "
                        f"Increase distance between towers."
                    )

    if max_bua_sqm > 0 and total_bua_sqm > max_bua_sqm * 1.05:
        errors.append(
            f"Total BUA {total_bua_sqm:.0f} sqm exceeds limit {max_bua_sqm:.0f} sqm by "
            f"{((total_bua_sqm / max_bua_sqm) - 1) * 100:.0f}%. Reduce floors or tower size."
        )

    if plot_area_sqm > 0 and gc_limit_pct > 0:
        gc_actual = (total_footprint_sqm / plot_area_sqm) * 100
        if gc_actual > gc_limit_pct * 1.05:
            errors.append(
                f"Ground coverage {gc_actual:.1f}% exceeds limit {gc_limit_pct:.1f}%. "
                f"Reduce tower footprint sizes."
            )

    return errors


def _shapely_dxf_to_local_metres(poly, origin_x_dxf: float, origin_y_dxf: float) -> Polygon:
    """Translate + scale a Shapely polygon from DXF feet to local metres (origin-shifted)."""
    from shapely.affinity import translate, scale as shapely_scale
    shifted = translate(poly, xoff=-origin_x_dxf, yoff=-origin_y_dxf)
    return shapely_scale(shifted, xfact=DXF_TO_METRES, yfact=DXF_TO_METRES, origin=(0, 0))
