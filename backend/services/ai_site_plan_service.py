"""
services/ai_site_plan_service.py
---------------------------------
Orchestrator for AI-powered site plan generation.

Pipeline: build context -> prompt -> GPT-4o -> validate -> retry loop -> convert
to FootprintCandidate objects for the existing result assembly pipeline.

Falls back to None on any AI failure so the caller can use the deterministic engine.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import Polygon, box
from shapely.affinity import rotate as shapely_rotate

from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config
from common.units import (
    DXF_TO_METRES,
    METRES_TO_DXF,
    dxf_plane_area_to_sqm,
)
from placement_engine.geometry import FootprintCandidate
from placement_engine.geometry.spacing_enforcer import required_spacing_m
from services.ai_site_plan_prompt import build_site_plan_prompt
from services.ai_site_plan_validator import validate_ai_site_plan

logger = logging.getLogger(__name__)


def generate_ai_site_plan(
    plot,
    envelope_result,
    fsi_decision,
    inputs: Dict[str, Any],
    road_info: Dict[str, Any],
    final_envelope: Optional[Polygon] = None,
    zone_polygons: Optional[List] = None,
) -> Optional[Dict[str, Any]]:
    """
    Attempt AI-powered tower layout generation.

    Returns dict with footprints/floor_count/n_placed/generation_source,
    or None on failure (caller falls back to deterministic).
    """
    config = get_ai_config()
    if not config.api_key:
        logger.warning("AI site plan: no API key configured, skipping.")
        return None

    plot_area_sqm = float(plot.plot_area_sqm)
    road_width_m = float(road_info.get("road_width_m", 0))
    building_height_m = float(road_info.get("building_height_m", 30))
    storey_height_m = float(road_info.get("storey_height_m", 3.0))
    max_floors = int(road_info.get("max_floors", 20))
    spacing_m = required_spacing_m(building_height_m)

    max_fsi = road_info.get("max_fsi")
    if max_fsi is None and fsi_decision is not None:
        max_fsi = float(getattr(fsi_decision, "max_fsi", 0))
    max_fsi = float(max_fsi or 0)

    max_bua_sqm = road_info.get("max_bua_sqm")
    if max_bua_sqm is None:
        max_bua_sqm = plot_area_sqm * max_fsi if max_fsi > 0 else 0
    max_bua_sqm = float(max_bua_sqm or 0)

    envelope_poly = final_envelope or envelope_result.envelope_polygon
    if envelope_poly is None or envelope_poly.is_empty:
        logger.warning("AI site plan: no envelope polygon, skipping.")
        return None

    envelope_area_sqm = dxf_plane_area_to_sqm(
        float(envelope_result.envelope_area_sqft or 0)
    )
    gc_pct = float(envelope_result.ground_coverage_pct or 0)

    try:
        from architecture.regulatory_accessors import get_cop_required_fraction
        cop_required_sqm = plot_area_sqm * get_cop_required_fraction()
    except Exception:
        cop_required_sqm = 0

    # Parse tower count — handle "auto", numeric strings, and ints
    raw_tc = inputs.get("towerCount", "auto")
    if isinstance(raw_tc, (int, float)):
        n_towers = max(1, int(raw_tc))
    elif isinstance(raw_tc, str) and raw_tc != "auto":
        try:
            n_towers = max(1, int(raw_tc))
        except (TypeError, ValueError):
            n_towers = 2
    else:
        n_towers = 2

    context = {
        "plot_polygon": None,
        "envelope_polygon": envelope_poly,
        "plot_area_sqm": plot_area_sqm,
        "envelope_area_sqm": envelope_area_sqm,
        "road_width_m": road_width_m,
        "building_height_m": building_height_m,
        "max_fsi": max_fsi,
        "max_bua_sqm": max_bua_sqm,
        "ground_coverage_pct": gc_pct,
        "cop_required_sqm": cop_required_sqm,
        "spacing_required_m": spacing_m,
        "storey_height_m": storey_height_m,
        "max_floors": max_floors,
        "n_towers_requested": n_towers,
        "building_type": inputs.get("building_type", inputs.get("buildingType", 2)),
        "segment": inputs.get("segment", "mid"),
        "unit_mix": inputs.get("unitMix", []),
        "units_per_core": inputs.get("units_per_core", inputs.get("unitsPerCore", 4)),
        "zone_polygons": zone_polygons or [],
    }

    logger.info(
        "AI site plan context: plot_area=%.0f max_fsi=%.3f max_bua=%.0f "
        "envelope_area=%.0f spacing=%.1f max_floors=%d n_towers=%d",
        plot_area_sqm, max_fsi, max_bua_sqm,
        envelope_area_sqm, spacing_m, max_floors, n_towers,
    )

    max_retries = config.site_plan_max_retries
    error_feedback = ""

    for attempt in range(1, max_retries + 1):
        logger.info("AI site plan: attempt %d/%d", attempt, max_retries)

        system_prompt, user_prompt = build_site_plan_prompt(context, error_feedback)

        raw = call_openai(
            model=config.site_plan_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=config.site_plan_timeout_s,
            max_tokens=config.site_plan_max_tokens,
            temperature=0.2 if attempt == 1 else 0.4,
        )
        if raw is None:
            logger.warning("AI site plan: GPT returned None on attempt %d", attempt)
            continue

        logger.info("AI site plan: received response (%d chars)", len(raw))

        parsed = parse_json_response(raw)
        if parsed is None:
            logger.warning("AI site plan: JSON parse failed on attempt %d, raw[:200]=%s", attempt, raw[:200])
            error_feedback = "Response was not valid JSON. Return only a JSON object."
            continue

        errors = validate_ai_site_plan(parsed, context)
        if errors:
            error_feedback = "\n".join(f"- {e}" for e in errors)
            logger.warning(
                "AI site plan: validation failed attempt %d:\n%s",
                attempt, error_feedback,
            )
            continue

        ox_dxf = float(context.get("_origin_x_dxf", 0))
        oy_dxf = float(context.get("_origin_y_dxf", 0))
        footprints, floor_count = _towers_to_footprint_candidates(
            parsed["towers"], envelope_poly, storey_height_m,
            origin_x_dxf=ox_dxf, origin_y_dxf=oy_dxf,
        )
        if not footprints:
            error_feedback = "Could not convert towers to valid footprint polygons."
            logger.warning("AI site plan: footprint conversion failed on attempt %d", attempt)
            continue

        logger.info(
            "AI site plan: SUCCESS on attempt %d — %d towers, %d floors",
            attempt, len(footprints), floor_count,
        )
        return {
            "footprints": footprints,
            "floor_count": floor_count,
            "n_placed": len(footprints),
            "generation_source": "ai",
            "design_rationale": parsed.get("designRationale", ""),
        }

    logger.warning("AI site plan: all %d attempts failed, falling back to deterministic.", max_retries)
    return None


def _towers_to_footprint_candidates(
    towers: List[Dict[str, Any]],
    envelope_poly_dxf: Polygon,
    storey_height_m: float,
    origin_x_dxf: float = 0.0,
    origin_y_dxf: float = 0.0,
) -> Tuple[List[FootprintCandidate], int]:
    """
    Convert AI tower dicts (local metres, origin-shifted) to FootprintCandidate
    objects (absolute DXF feet) compatible with the existing result assembly.

    The AI places towers in a local coordinate system where (0,0) = envelope
    lower-left. We translate back by adding origin_x/y_dxf after converting
    metres -> DXF.
    """
    candidates: List[FootprintCandidate] = []
    floor_count = 0

    for i, t in enumerate(towers):
        try:
            cx_local_m = float(t["centerX"])
            cy_local_m = float(t["centerY"])
            w_m = float(t["widthM"])
            d_m = float(t["depthM"])
            floors = int(t["floors"])
            orientation = float(t.get("orientationDeg", 0))

            if floors > floor_count:
                floor_count = floors

            # Convert local metres -> absolute DXF feet
            cx_dxf = cx_local_m * METRES_TO_DXF + origin_x_dxf
            cy_dxf = cy_local_m * METRES_TO_DXF + origin_y_dxf
            w_dxf = w_m * METRES_TO_DXF
            d_dxf = d_m * METRES_TO_DXF

            half_w = w_dxf / 2.0
            half_d = d_dxf / 2.0
            rect = box(cx_dxf - half_w, cy_dxf - half_d, cx_dxf + half_w, cy_dxf + half_d)

            if abs(orientation) > 0.01:
                rect = shapely_rotate(rect, orientation, origin="centroid", use_radians=False)

            area_sqft = rect.area

            candidates.append(FootprintCandidate(
                footprint_polygon=rect,
                area_sqft=area_sqft,
                width_dxf=w_dxf,
                depth_dxf=d_dxf,
                width_m=w_m,
                depth_m=d_m,
                orientation_angle_deg=orientation,
                orientation_label="AI_GENERATED",
                grid_resolution_dxf=0.0,
                source_component_index=i,
            ))
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("AI site plan: failed to convert tower %d: %s", i, e)
            continue

    return candidates, floor_count
