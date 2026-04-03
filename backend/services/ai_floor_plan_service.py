"""
services/ai_floor_plan_service.py
-----------------------------------
Main orchestrator for the hybrid AI floor plan generator.

Pipeline: prompt → GPT-4o → validate → convert to GeoJSON → render SVG
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from ai_layer.client import call_llm, call_openai, parse_json_response
from ai_layer.config import get_ai_config
from services.ai_floor_plan_prompt import (
    build_system_prompt,
    build_user_prompt,
    n_lifts_required,
    n_stairs_required,
    CORRIDOR_W,
    LIFT_SHAFT_W,
    STAIR_W,
    WALL_T,
)
from services.ai_floor_plan_validator import validate_ai_floor_plan
from services.ai_to_geojson_converter import convert_ai_layout_to_geojson
from services.svg_blueprint_renderer import render_blueprint_svg
from services.unit_layout_engine import layout_floor
from ai_layer.image_client import generate_image, generate_image_gemini, generate_image_recraft
from services.floor_plan_image_prompt import (
    PROMPT_VARIANT_SUFFIXES,
    build_architectural_prompt,
    compile_recraft_prompt,
    score_generated_images,
)

logger = logging.getLogger(__name__)

# DXF conversion factor
DXF_TO_M = 0.3048
M_TO_DXF = 1.0 / DXF_TO_M


def generate_ai_floor_plan(
    footprint_geojson: Dict[str, Any],
    n_floors: int,
    building_height_m: float,
    units_per_core: int = 4,
    building_type: int = 2,
    segment: str = "mid",
    unit_mix: Optional[List[str]] = None,
    storey_height_m: float = 3.0,
    plot_area_sqm: float = 0.0,
    design_brief: str = "",
    image_model: str = "dalle3",
) -> Dict[str, Any]:
    """
    Generate an AI-powered floor plan for a single tower.

    Parameters
    ----------
    footprint_geojson : GeoJSON Polygon (DXF feet coordinates)
    n_floors, building_height_m : tower parameters
    units_per_core : 2/4/6 units sharing one core
    building_type : 1 (low-rise), 2 (mid-rise), 3 (high-rise)
    segment : budget/mid/premium/luxury
    unit_mix : e.g. ["2BHK", "3BHK"]
    design_brief : optional free-text design instructions
    image_model : "dalle3" | "gemini" | "recraft" | "ideogram" | "flux" | "svg_only"

    Returns
    -------
    dict with: status, source, layout (GeoJSON), svg_blueprint, metrics, design_notes,
               architectural_image, image_model_used, layout_authority_note
    """
    import time
    _t_start = time.monotonic()

    unit_mix = unit_mix or []

    # ---- 1. Parse footprint dimensions ----
    floor_width_m, floor_depth_m = _footprint_dimensions(footprint_geojson)
    if floor_width_m <= 0 or floor_depth_m <= 0:
        return _error_response("Could not determine footprint dimensions")

    # Ensure width >= depth (width is the long axis)
    if floor_depth_m > floor_width_m:
        floor_width_m, floor_depth_m = floor_depth_m, floor_width_m

    mix_label = "+".join(unit_mix) if unit_mix else "auto"
    logger.info(
        "[FP] ── START: %.1fm x %.1fm | %dF | %d units/core | %s | seg=%s | img=%s",
        floor_width_m, floor_depth_m, n_floors, units_per_core, mix_label, segment, image_model,
    )

    # ---- 2. Compute derived parameters ----
    total_units_estimate = units_per_core * n_floors
    n_lifts = n_lifts_required(building_height_m, total_units_estimate)
    n_stairs = n_stairs_required(building_height_m)
    logger.info(
        "[FP] ── Step 1/7: Derived params — lifts=%d stairs=%d total_units≈%d",
        n_lifts, n_stairs, total_units_estimate,
    )

    # ---- 3. Build prompts ----
    logger.info("[FP] ── Step 2/7: Building LLM prompt")
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        floor_width_m=floor_width_m,
        floor_depth_m=floor_depth_m,
        n_floors=n_floors,
        building_height_m=building_height_m,
        units_per_core=units_per_core,
        segment=segment,
        unit_mix=unit_mix,
        n_lifts=n_lifts,
        n_stairs=n_stairs,
        design_brief=design_brief,
    )

    # ---- 4. Call AI with retry (model-agnostic) ----
    config = get_ai_config()
    model_choice = config.floor_plan_ai_model  # "claude" or "gpt-4o"
    timeout = config.floor_plan_timeout_s
    max_tokens_setting = config.floor_plan_max_tokens
    logger.info("[FP] ── Step 3/7: LLM layout generation (model=%s, timeout=%.0fs)", model_choice, timeout)

    ai_layout = None
    design_notes = ""
    last_errors: List[str] = []

    for attempt in range(3):
        import time as _time
        _t_llm = _time.monotonic()
        prompt = user_prompt
        if attempt > 0 and last_errors:
            logger.info("[FP]    Retry attempt %d/3 — injecting %d error(s) into prompt", attempt + 1, len(last_errors))
            prompt += (
                "\n\nPREVIOUS ATTEMPT HAD ERRORS — please fix:\n"
                + "\n".join(f"  - {e}" for e in last_errors)
            )

        raw = call_llm(
            model_choice=model_choice,
            system_prompt=system_prompt,
            user_prompt=prompt,
            timeout_s=timeout,
            temperature=0.2,
            max_tokens=max_tokens_setting,
        )

        _llm_elapsed = _time.monotonic() - _t_llm
        if not raw:
            logger.warning("[FP]    LLM returned empty response (attempt %d, %.1fs)", attempt + 1, _llm_elapsed)
            continue

        logger.info("[FP]    LLM responded (attempt %d, %d chars, %.1fs)", attempt + 1, len(raw), _llm_elapsed)

        parsed = _parse_ai_response(raw)
        if not parsed:
            logger.warning("[FP]    JSON parse failed (attempt %d) — first 300 chars: %s", attempt + 1, raw[:300])
            last_errors = ["Response was not valid JSON"]
            continue

        # Validate structure
        validation = validate_ai_floor_plan(
            parsed, floor_width_m, floor_depth_m, n_lifts, n_stairs,
        )

        if validation["valid"]:
            ai_layout = validation["repaired_layout"]
            design_notes = parsed.get("design_notes", "")
            n_units_gen = len(ai_layout.get("units", []))
            n_rooms_gen = sum(len(u.get("rooms", [])) for u in ai_layout.get("units", []))
            logger.info(
                "[FP]    Validation PASSED (attempt %d) — %d units, %d rooms total, warnings=%d",
                attempt + 1, n_units_gen, n_rooms_gen, len(validation.get("warnings", [])),
            )
            if validation["warnings"]:
                logger.info("[FP]    Warnings: %s", validation["warnings"])
            break
        else:
            last_errors = validation["errors"]
            logger.warning("[FP]    Validation FAILED (attempt %d): %s", attempt + 1, last_errors)

    if ai_layout is None:
        logger.error("[FP]    All 3 LLM attempts failed. Last errors: %s", last_errors)
        return _error_response(
            f"AI floor plan generation failed after 3 attempts. Last errors: {last_errors}"
        )

    # ---- 4b. Check if AI provided room-level layouts ----
    units_have_rooms = all(
        len(u.get("rooms", [])) > 0 for u in ai_layout.get("units", [])
    )

    if not units_have_rooms:
        # Fallback: recompute envelopes and inject deterministic rooms
        logger.warning("AI returned units without rooms — falling back to deterministic layout")
        ai_layout = _recompute_unit_envelopes(
            ai_layout, floor_width_m, floor_depth_m,
            units_per_core, n_lifts, n_stairs,
        )
        ai_layout = _inject_deterministic_rooms(ai_layout, segment)
    else:
        # AI provided rooms — validate completeness and enforce GDCR
        from services.ai_floor_plan_validator import (
            check_room_completeness, enforce_gdcr_minimums, check_ventilation,
        )
        for unit in ai_layout.get("units", []):
            completeness_errors = check_room_completeness(unit)
            if completeness_errors:
                logger.warning("Room completeness issues in %s: %s",
                               unit.get("id"), completeness_errors)
            # Enforce GDCR minimums
            rooms = unit.get("rooms", [])
            adjusted_rooms, gdcr_warnings = enforce_gdcr_minimums(rooms)
            unit["rooms"] = adjusted_rooms
            if gdcr_warnings:
                logger.info("GDCR adjustments for %s: %s",
                            unit.get("id"), gdcr_warnings)
            # Check ventilation
            vent_errors = check_ventilation(unit, adjusted_rooms)
            if vent_errors:
                logger.warning("Ventilation issues in %s: %s",
                               unit.get("id"), vent_errors)

    # ---- 5. Snap coordinates ----
    logger.info("[FP] ── Step 4/7: Snapping to structural grid + aligning wet zones")
    ai_layout = _snap_to_structural_grid(ai_layout, floor_width_m)
    ai_layout = _align_wet_zone_stacks(ai_layout)

    # ---- 6. Convert to GeoJSON ----
    logger.info("[FP] ── Step 5/7: Converting to GeoJSON")
    geojson_layout = convert_ai_layout_to_geojson(
        ai_layout, floor_width_m, floor_depth_m,
    )

    # ---- 7. Compute metrics ----
    metrics = _compute_metrics(
        ai_layout, geojson_layout, floor_width_m, floor_depth_m,
        n_floors, building_height_m, storey_height_m, n_lifts, n_stairs,
    )
    logger.info(
        "[FP]    Metrics: %d units/floor | %.1f%% efficiency | net BUA %.0f sqm | FSI %.3f",
        metrics.get("nUnitsPerFloor", 0), metrics.get("efficiencyPct", 0),
        metrics.get("netBuaSqm", 0), metrics.get("achievedFSINet", 0),
    )

    # ---- 8. Render SVG fallback (always, fast) ----
    logger.info("[FP] ── Step 6/7: Rendering SVG blueprint (%.1fm x %.1fm)", floor_width_m, floor_depth_m)
    title = f"Typical Floor Plan — {units_per_core} units/core — {segment.title()}"
    svg_blueprint = render_blueprint_svg(
        geojson_layout, floor_width_m, floor_depth_m, title=title,
    )
    logger.info("[FP]    SVG ready (%d chars)", len(svg_blueprint) if svg_blueprint else 0)

    # ---- 9. Build image prompt (model-specific) ----
    # For Recraft: use the deterministic Layer 1→1.5→2 pipeline which produces
    # Surat-norm, spatially-anchored natural language optimised for Recraft V4.
    # For all other models: use the compressed DALL-E style prompt.
    if image_model == "recraft":
        arch_prompt = _build_recraft_prompt(
            floor_width_m, floor_depth_m, units_per_core,
            unit_mix, segment, n_lifts, n_stairs,
        ) or build_architectural_prompt(
            ai_layout, metrics,
            segment=segment, units_per_core=units_per_core,
            design_brief=design_brief,
            design_notes=design_notes or ai_layout.get("design_notes"),
        )
    else:
        arch_prompt = build_architectural_prompt(
            ai_layout,
            metrics,
            segment=segment,
            units_per_core=units_per_core,
            design_brief=design_brief,
            design_notes=design_notes or ai_layout.get("design_notes"),
        )
    n_words = len(arch_prompt.split())
    logger.info(
        "[FP]    Image prompt built — chars=%d words≈%d",
        len(arch_prompt),
        n_words,
    )

    # ---- 10. Generate image (model-routed, best-effort) ----
    architectural_image = None
    image_model_used = "svg_only"

    if image_model != "svg_only" and config.floor_plan_image_enabled:
        import time as _time
        _t_img = _time.monotonic()
        logger.info("[FP] ── Step 7/7: Image generation (model=%s)", image_model)
        try:
            n_variants = max(1, int(getattr(config, "floor_plan_image_variants", 4)))
            arch_img, img_meta = _generate_images_for_model(
                image_model, arch_prompt, config,
                ai_layout=ai_layout,
                n_variants=n_variants,
            )
            architectural_image = arch_img
            image_model_used = image_model
            _img_elapsed = _time.monotonic() - _t_img
            logger.info(
                "[FP]    Image done in %.1fs — variants=%s picked=%s arch=%s",
                _img_elapsed,
                img_meta.get("n_generated"),
                img_meta.get("picked_index"),
                "OK" if arch_img else "NONE",
            )
        except Exception as e:
            logger.warning("[FP]    Image generation error (%s): %s", image_model, e, exc_info=False)
    else:
        logger.info("[FP] ── Step 7/7: Skipping image generation (model=%s)", image_model)

    import time as _time2
    _total_elapsed = _time2.monotonic() - _t_start
    logger.info(
        "[FP] ── DONE in %.1fs | arch=%s svg=YES | model=%s",
        _total_elapsed,
        "YES" if architectural_image else "NO",
        image_model_used,
    )

    # ---- 11. Assemble response ----
    layout_authority_note = (
        "The SVG blueprint and layout JSON are dimensionally authoritative. "
        "The raster preview is a schematic illustration and may not match exact "
        "measurements or room adjacency."
    )
    return {
        "status": "ok",
        "source": "ai",
        "layout": geojson_layout,
        "layout_json": ai_layout,
        "architectural_image": architectural_image,
        "svg_blueprint": svg_blueprint,
        "metrics": metrics,
        "design_notes": design_notes,
        "image_model_used": image_model_used,
        "layout_authority_note": layout_authority_note,
    }


# ---- Helpers ----

def _footprint_dimensions(geojson: Dict[str, Any]) -> Tuple[float, float]:
    """Extract width and depth in metres from a GeoJSON Polygon (DXF feet)."""
    coords = geojson.get("coordinates", [[]])[0]
    if len(coords) < 3:
        return 0.0, 0.0

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    width_dxf = max(xs) - min(xs)
    depth_dxf = max(ys) - min(ys)

    return round(width_dxf * DXF_TO_M, 2), round(depth_dxf * DXF_TO_M, 2)


def _parse_ai_response(raw: str) -> Optional[Dict]:
    """Parse the AI response, handling markdown code fences."""
    stripped = raw.strip()

    # Strip markdown fences
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        stripped = "\n".join(lines).strip()

    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _compute_metrics(
    ai_layout: Dict,
    geojson_layout: Dict,
    floor_width_m: float,
    floor_depth_m: float,
    n_floors: int,
    building_height_m: float,
    storey_height_m: float,
    n_lifts: int,
    n_stairs: int,
) -> Dict[str, Any]:
    """Compute floor plan metrics from the AI layout."""
    footprint_sqm = floor_width_m * floor_depth_m

    core = ai_layout.get("core", {})
    core_sqm = core.get("w", 0) * core.get("h", 0)

    corridor = ai_layout.get("corridor", {})
    corridor_sqm = corridor.get("w", 0) * corridor.get("h", 0)

    units = ai_layout.get("units", [])
    unit_areas = [u.get("w", 0) * u.get("h", 0) for u in units]
    total_unit_area = sum(unit_areas)

    balcony_area = sum(
        u.get("balcony", {}).get("w", 0) * u.get("balcony", {}).get("h", 0)
        for u in units
        if u.get("balcony") and isinstance(u.get("balcony"), dict)
    )

    circulation_sqm = core_sqm + corridor_sqm
    n_units = len(units)

    unit_type_counts: Dict[str, int] = {}
    for u in units:
        utype = u.get("type", "UNKNOWN")
        unit_type_counts[utype] = unit_type_counts.get(utype, 0) + 1

    efficiency = total_unit_area / max(footprint_sqm, 1) * 100

    return {
        "footprintSqm": round(footprint_sqm, 1),
        "floorLengthM": round(floor_width_m, 1),
        "floorWidthM": round(floor_depth_m, 1),
        "coreSqm": round(core_sqm, 1),
        "corridorSqm": round(corridor_sqm, 1),
        "circulationSqm": round(circulation_sqm, 1),
        "balconySqmPerFloor": round(balcony_area, 1),
        "unitAreaPerFloorSqm": round(total_unit_area, 1),
        "nUnitsPerFloor": n_units,
        "nTotalUnits": n_units * n_floors,
        "unitTypeCounts": unit_type_counts,
        "nFloors": n_floors,
        "buildingHeightM": round(building_height_m, 1),
        "storeyHeightM": storey_height_m,
        "netBuaSqm": round(total_unit_area * n_floors, 1),
        "grossBuaSqm": round(footprint_sqm * n_floors, 1),
        "achievedFSINet": round(total_unit_area * n_floors / max(footprint_sqm, 1), 3),
        "achievedFSIGross": round(n_floors, 1),
        "efficiencyPct": round(efficiency, 1),
        "nLifts": n_lifts,
        "nStairs": n_stairs,
    }


def _recompute_unit_envelopes(
    ai_layout: Dict[str, Any],
    floor_width_m: float,
    floor_depth_m: float,
    units_per_core: int,
    n_lifts: int,
    n_stairs: int,
) -> Dict[str, Any]:
    """
    Completely replace GPT-generated spatial positions with deterministic ones.

    GPT is kept only for the list of unit TYPES (1BHK/2BHK/3BHK/4BHK) and the
    design_notes string.  All bounding boxes (core, corridor, unit envelopes)
    are recomputed from floor geometry so the layout always fills the plate.

    Core placement rules:
    ──────────────────────────────────────────────────────────────────────
    • n ≥ 4 units/core (≥ 2 per side): core centred on X-axis.
      Units fill [0 → core_x] and [core_x+core_w → floor_width_m] on each side.

    • 2 units/core (1 per side): core at the RIGHT end of the corridor.
      The single south and north unit each spans [0 → core_x] (full plate
      width minus core depth), so there is no wasted space.

    • 3 units/core: 2 on south, 1 on north.  Core centred.

    Corridor always spans the full floor width.
    """
    import copy
    from services.ai_floor_plan_prompt import (
        LIFT_SHAFT_W, LIFT_SHAFT_D, STAIR_W, STAIR_D, LOBBY_D,
        CORRIDOR_W, WALL_T,
    )

    result = copy.deepcopy(ai_layout)

    # ── Core sizing ───────────────────────────────────────────────────────────
    n_lifts_safe  = max(n_lifts, 1)
    n_stairs_safe = max(n_stairs, 1)
    core_w = round(max(
        LIFT_SHAFT_W * n_lifts_safe + STAIR_W * n_stairs_safe + WALL_T * 4,
        4.0,
    ), 2)
    core_h = round(max(STAIR_D + LOBBY_D + WALL_T * 2, 5.5), 2)

    # ── Corridor geometry ──────────────────────────────────────────────────────
    corridor_y    = round((floor_depth_m - CORRIDOR_W) / 2.0, 2)
    south_band_h  = corridor_y                               # depth of south units
    north_band_h  = round(floor_depth_m - corridor_y - CORRIDOR_W, 2)

    # ── Unit counts per side ───────────────────────────────────────────────────
    n_south = units_per_core // 2
    n_north = units_per_core - n_south
    if n_south == 0:
        n_south, n_north = 1, max(units_per_core - 1, 1)

    # ── Core X position ────────────────────────────────────────────────────────
    if units_per_core <= 2:
        # Single unit per side → core at right end, units fill the full left width
        core_x = round(floor_width_m - core_w, 2)
    else:
        # Multi-unit per side → core centred
        core_x = round((floor_width_m - core_w) / 2.0, 2)

    core_y = 0.0   # core spans full floor depth

    # ── Build new core dict ────────────────────────────────────────────────────
    # Construct lift + stair positions inside the core
    new_lifts = []
    lx = core_x + WALL_T
    for _ in range(n_lifts_safe):
        new_lifts.append({"x": round(lx, 2), "y": round(WALL_T, 2),
                          "w": LIFT_SHAFT_W, "h": LIFT_SHAFT_D})
        lx += LIFT_SHAFT_W

    new_stairs = []
    sx = core_x + WALL_T
    stair_y = round(LIFT_SHAFT_D + WALL_T * 2, 2)
    for _ in range(n_stairs_safe):
        new_stairs.append({"x": round(sx, 2), "y": stair_y,
                           "w": STAIR_W, "h": STAIR_D})
        sx += STAIR_W + WALL_T

    lobby = {
        "x": core_x, "y": round(corridor_y - LOBBY_D / 2, 2),
        "w": core_w, "h": LOBBY_D,
    }

    result["core"] = {
        "x": core_x, "y": core_y, "w": core_w, "h": floor_depth_m,
        "lifts":  new_lifts,
        "stairs": new_stairs,
        "lobby":  lobby,
    }

    # ── Corridor ───────────────────────────────────────────────────────────────
    result["corridor"] = {
        "x": 0.0, "y": corridor_y,
        "w": floor_width_m, "h": CORRIDOR_W,
    }

    # ── Build unit X ranges on each side ──────────────────────────────────────
    # Available columns: [0 → core_x] and [core_x+core_w → floor_width_m]
    left_w  = core_x
    right_w = round(floor_width_m - core_x - core_w, 2)

    def _unit_columns(n: int) -> List[Tuple[float, float]]:
        """Return (x, w) for n units filling the available columns."""
        if n == 1:
            # Single unit: fill ONLY the left segment (core at right end)
            # OR fill both segments if core is centred (n>=2 case won't enter here)
            if units_per_core <= 2:
                return [(0.0, left_w)]
            # Centred core, 1 unit → left segment only (shouldn't normally occur)
            return [(0.0, left_w)]
        # Multiple units: split evenly between left and right segments
        n_left  = n // 2
        n_right = n - n_left
        cols: List[Tuple[float, float]] = []
        if n_left > 0 and left_w > 0:
            uw = round(left_w / n_left, 2)
            for i in range(n_left):
                cols.append((round(i * uw, 2), uw))
        if n_right > 0 and right_w > 0:
            uw = round(right_w / n_right, 2)
            rx0 = core_x + core_w
            for i in range(n_right):
                cols.append((round(rx0 + i * uw, 2), uw))
        return cols

    south_cols = _unit_columns(n_south)
    north_cols = _unit_columns(n_north)

    # ── Preserve GPT unit types in order ──────────────────────────────────────
    gpt_units  = result.get("units", [])
    gpt_south  = [u for u in gpt_units if u.get("side", "south") == "south"]
    gpt_north  = [u for u in gpt_units if u.get("side", "south") != "south"]

    # Fallback unit types if GPT didn't provide enough
    from services.ai_floor_plan_prompt import ROOM_LIST
    _DEFAULT_MIX = {
        "budget": ["1BHK", "2BHK"], "mid": ["2BHK", "3BHK"],
        "premium": ["3BHK", "3BHK"], "luxury": ["3BHK", "4BHK"],
    }

    def _get_type(gpt_list: List[Dict], idx: int) -> str:
        if idx < len(gpt_list):
            return gpt_list[idx].get("type", "2BHK")
        return "2BHK"

    new_units: List[Dict] = []
    for i, (ux, uw) in enumerate(south_cols):
        new_units.append({
            "id": f"U{len(new_units) + 1}",
            "type": _get_type(gpt_south, i),
            "side": "south",
            "x": ux, "y": 0.0,
            "w": uw, "h": south_band_h,
        })
    for i, (ux, uw) in enumerate(north_cols):
        new_units.append({
            "id": f"U{len(new_units) + 1}",
            "type": _get_type(gpt_north, i),
            "side": "north",
            "x": ux, "y": round(corridor_y + CORRIDOR_W, 2),
            "w": uw, "h": north_band_h,
        })

    result["units"] = new_units
    logger.info(
        "Recomputed envelopes: core at X=%.1f w=%.1f, "
        "%d south units, %d north units",
        core_x, core_w, len(south_cols), len(north_cols),
    )
    return result


def _inject_deterministic_rooms(
    ai_layout: Dict[str, Any],
    segment: str,
) -> Dict[str, Any]:
    """
    Replace GPT-generated room coordinates with deterministic layout.

    Strips any 'rooms' and 'balcony' that GPT provided (unreliable geometry)
    and replaces them with output from unit_layout_engine.  Mirroring is
    determined from unit positions so symmetric pairs around the core are
    genuine horizontal mirror images.  Falls back to keeping the original GPT
    rooms for a unit if the engine raises an error.
    """
    import copy
    result = copy.deepcopy(ai_layout)

    units = result.get("units", [])

    # Compute floor mid-X for mirror detection
    all_cx = [u["x"] + u["w"] / 2.0 for u in units if "x" in u and "w" in u]
    mid_x = (sum(all_cx) / len(all_cx)) if all_cx else 0.0

    for i, unit in enumerate(units):
        stripped = {k: v for k, v in unit.items()
                    if k not in ("rooms", "balcony")}
        cx = unit.get("x", 0) + unit.get("w", 0) / 2.0
        mirror = cx > mid_x
        try:
            from services.unit_layout_engine import generate_unit_rooms
            result["units"][i] = generate_unit_rooms(
                stripped, segment=segment, mirror=mirror,
            )
        except Exception as exc:
            logger.warning(
                "unit_layout_engine failed for unit %s (%s): %s — keeping GPT rooms",
                unit.get("id", i), unit.get("type", "?"), exc,
            )
            result["units"][i] = unit

    return result


def _align_wet_zone_stacks(
    ai_layout: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Align wet-room X left-edges to common plumbing stack lines.

    For each pair of adjacent units on the same side of the corridor
    (i.e. units whose X ranges share a boundary), collect all wet rooms
    (bathroom, toilet, kitchen, utility) and compute a consensus left-edge X
    for each wet room slot by averaging the left-edges across the pair.
    The room widths are adjusted to keep the same right edge.

    This ensures that, when looking at the building section, plumbing drops
    land in the same vertical shaft across all units.
    """
    import copy

    _WET = {"bathroom", "toilet", "kitchen", "utility"}
    SNAP_TOL = 0.30   # metres — how close two X edges must be to merge

    result = copy.deepcopy(ai_layout)
    units = result.get("units", [])

    # Group units by side
    by_side: Dict[str, List[Dict]] = {}
    for u in units:
        s = u.get("side", "south")
        by_side.setdefault(s, []).append(u)

    for side_units in by_side.values():
        # Sort by X so adjacent pairs are consecutive
        side_units.sort(key=lambda u: u.get("x", 0))

        for i in range(len(side_units) - 1):
            ua = side_units[i]
            ub = side_units[i + 1]

            # Only process if the two units actually share a wall
            a_right = ua.get("x", 0) + ua.get("w", 0)
            b_left  = ub.get("x", 0)
            if abs(a_right - b_left) > 0.10:
                continue

            wet_a = [r for r in ua.get("rooms", []) if r.get("type") in _WET]
            wet_b = [r for r in ub.get("rooms", []) if r.get("type") in _WET]

            if not wet_a or not wet_b:
                continue

            # Build a shared left-edge list.  Walk through both wet-room lists
            # and pair rooms by approximate X position (nearest match).
            for ra in wet_a:
                best = min(wet_b, key=lambda rb: abs(rb["x"] - ra["x"]))
                if abs(best["x"] - ra["x"]) < SNAP_TOL:
                    # Snap both to average
                    avg_x = round((ra["x"] + best["x"]) / 2.0, 2)
                    # Adjust widths to keep right edge constant
                    ra["w"] = round(ra["w"] + (ra["x"] - avg_x), 2)
                    ra["x"] = avg_x
                    best["w"] = round(best["w"] + (best["x"] - avg_x), 2)
                    best["x"] = avg_x

    return result


def _snap_to_structural_grid(
    ai_layout: Dict[str, Any],
    floor_width_m: float,
    grid_m: float = 4.5,
    min_room_w: float = 2.0,
) -> Dict[str, Any]:
    """
    Snap room X boundaries to the nearest structural column grid line.

    Strategy:
    1. Derive a set of grid lines across the floor width at multiples of grid_m.
    2. For every room in every unit, snap the room's right edge (x + w) to the
       nearest grid line, then adjust width while keeping x fixed.
    3. Skip snapping when it would reduce a room below min_room_w.

    This does not snap Y boundaries — zone depths are computed from GDCR
    minimums and changing them would risk compliance violations.
    """
    import copy

    def nearest_grid(val: float, grid: float) -> float:
        return round(round(val / grid) * grid, 3)

    result = copy.deepcopy(ai_layout)
    for unit in result.get("units", []):
        ux = unit.get("x", 0.0)
        uw = unit.get("w", 0.0)
        for room in unit.get("rooms", []):
            rx = room.get("x", 0.0)
            rw = room.get("w", 0.0)
            # Snap the right edge of the room
            right_edge = rx + rw
            snapped_right = nearest_grid(right_edge, grid_m)
            # Clamp snapped right edge within unit bounds
            snapped_right = max(rx + min_room_w,
                                min(snapped_right, ux + uw))
            new_w = round(snapped_right - rx, 3)
            if new_w >= min_room_w:
                room["w"] = new_w
    return result


def _build_recraft_prompt(
    floor_width_m: float,
    floor_depth_m: float,
    units_per_core: int,
    unit_mix: List[str],
    segment: str,
    n_lifts: int,
    n_stairs: int,
) -> Optional[str]:
    """
    Build a Recraft-optimised prompt via the deterministic Layer 1→1.5→2 pipeline.

    Layer 1 (unit_programme): derives RoomProgramme from GDCR/segment rules.
    Layer 1.5 (layout_engine): places rooms with absolute coordinates.
    Layer 2 (compile_recraft_prompt): converts RoomLayout list to natural-language prompt.

    Returns None on any error so callers can fall back to build_architectural_prompt.
    """
    try:
        from services.unit_programme import compute_net_usable, derive_room_programme
        from services.layout_engine import generate_unit_layout

        # Derive unit bounding box from floor plate geometry
        core_w = max(LIFT_SHAFT_W * n_lifts + STAIR_W * n_stairs + WALL_T * 4, 4.0)
        avail_width = floor_width_m - core_w
        n_units_per_side = max(1, units_per_core // 2)
        unit_w = round(avail_width / n_units_per_side, 2)
        unit_d = round((floor_depth_m - CORRIDOR_W) / 2, 2)

        unit_type = (unit_mix[0] if unit_mix else "2BHK").upper()
        cap_segment = segment.capitalize()

        # Layer 1: Room programme
        net_usable = compute_net_usable(
            tower_footprint_sqm=floor_width_m * floor_depth_m,
            core_area_sqm=core_w * floor_depth_m,
            units_per_core=units_per_core,
            floor_plate_depth_m=floor_depth_m,
        )
        programme = derive_room_programme(unit_type, cap_segment, net_usable, units_per_core)

        # Layer 1.5: Spatial layout
        layouts, _result = generate_unit_layout(programme, unit_w, unit_d, units_per_core)

        # Layer 2: Recraft prompt
        return compile_recraft_prompt(
            layouts=layouts,
            unit_w=unit_w,
            unit_d=unit_d,
            unit_type=unit_type,
            n_units=units_per_core,
            segment=cap_segment,
        )
    except Exception as exc:
        logger.warning("[FP]    _build_recraft_prompt failed (%s) — using fallback prompt", exc)
        return None


def _generate_one_image(
    image_model: str,
    prompt: str,
    config,
) -> Optional[str]:
    """Single image API call for the configured provider."""
    if image_model == "dalle3":
        return generate_image(
            prompt,
            size=getattr(config, "dalle_size", "1792x1024"),
            quality=getattr(config, "dalle_quality", "hd"),
            style="natural",
        )

    if image_model == "gemini":
        api_key = getattr(config, "gemini_api_key", None)
        if not api_key:
            logger.warning("[FP]    gemini: GEMINI_API_KEY not configured — skipping image")
            return None
        model = getattr(config, "gemini_image_model", "imagen-4.0-generate-001")
        timeout = float(getattr(config, "gemini_image_timeout_s", 120.0))
        return generate_image_gemini(prompt, api_key, model, timeout)

    if image_model == "recraft":
        api_key = getattr(config, "recraft_api_key", None)
        if not api_key:
            logger.warning("[FP]    recraft: RECRAFT_API_KEY not configured — skipping image")
            return None
        return generate_image_recraft(
            prompt,
            api_key,
            model=getattr(config, "recraft_model", "recraftv4"),
            size=getattr(config, "recraft_size", "16:9"),
            n=1,
            style=getattr(config, "recraft_style", None),
            negative_prompt=getattr(config, "recraft_negative_prompt", None),
            timeout_s=float(getattr(config, "recraft_timeout_s", 120.0)),
        )

    if image_model == "ideogram":
        api_key = getattr(config, "ideogram_api_key", None)
        if not api_key:
            logger.warning("[FP]    ideogram: IDEOGRAM_API_KEY not configured — skipping image")
            return None
        try:
            import httpx
            import base64 as b64mod
            headers = {"Api-Key": api_key, "Content-Type": "application/json"}
            resp = httpx.post(
                "https://api.ideogram.ai/generate",
                headers=headers,
                json={
                    "image_request": {
                        "prompt": prompt,
                        "aspect_ratio": "ASPECT_16_9",
                        "model": "V_2",
                        "magic_prompt_option": "OFF",
                    }
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            url = resp.json()["data"][0]["url"]
            img_bytes = httpx.get(url, timeout=60.0).content
            return b64mod.b64encode(img_bytes).decode()
        except Exception as e:
            logger.warning("[FP]    ideogram error: %s", e)
            return None

    if image_model == "flux":
        fal_key = getattr(config, "fal_key", None)
        if not fal_key:
            logger.warning("[FP]    flux: FAL_KEY not configured — skipping image")
            return None
        try:
            import httpx
            import base64 as b64mod
            headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}
            resp = httpx.post(
                "https://fal.run/fal-ai/flux/dev",
                headers=headers,
                json={"prompt": prompt, "image_size": "landscape_16_9", "num_images": 1},
                timeout=120.0,
            )
            resp.raise_for_status()
            url = resp.json()["images"][0]["url"]
            img_bytes = httpx.get(url, timeout=60.0).content
            return b64mod.b64encode(img_bytes).decode()
        except Exception as e:
            logger.warning("[FP]    flux error: %s", e)
            return None

    logger.warning("[FP]    Unknown image_model=%s — skipping image", image_model)
    return None


def _variant_prompt(base: str, index: int, n_variants: int) -> str:
    if n_variants <= 1:
        return base
    suf = PROMPT_VARIANT_SUFFIXES[index % len(PROMPT_VARIANT_SUFFIXES)]
    if not suf:
        return base
    return f"{base}, {suf}"


def _generate_images_for_model(
    image_model: str,
    arch_prompt: str,
    config,
    *,
    ai_layout: Optional[Dict[str, Any]] = None,
    n_variants: int = 4,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Generate multiple prompt variants, score, return best base64 PNG + meta for logging.
    """
    meta: Dict[str, Any] = {
        "n_requested": n_variants,
        "n_generated": 0,
        "picked_index": None,
        "scores": [],
    }
    if image_model not in (
        "dalle3", "gemini", "recraft", "ideogram", "flux",
    ):
        logger.warning("[FP]    Unknown image_model=%s — skipping image", image_model)
        return None, meta

    images: List[Optional[str]] = []
    for i in range(max(1, n_variants)):
        vp = _variant_prompt(arch_prompt, i, n_variants)
        logger.debug("[FP:img] variant %d prompt_len=%d", i, len(vp))
        one = _generate_one_image(image_model, vp, config)
        images.append(one)
        if one:
            meta["n_generated"] += 1

    best, score_meta = score_generated_images(images, ai_layout)
    meta.update(score_meta)
    return best, meta


def _error_response(detail: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "source": "ai",
        "error": detail,
        "layout": {"type": "FeatureCollection", "features": []},
        "svg_blueprint": "",
        "metrics": {},
        "design_notes": "",
    }
