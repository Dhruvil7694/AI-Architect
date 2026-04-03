"""
services/plot_exploration_service.py
------------------------------------
Orchestrator for the Plot Exploration endpoint.

Pipeline:
1. Load Plot → 2. Feasibility → 3. FSI Policy → 4. Road edges →
5. Setback annotations → 6. AI scenarios → 7. Sellable estimates →
8. Validate/clamp → 9. Fallback if AI fails
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.utils import timezone

from services.plot_service import get_plot_by_public_id
from architecture.services.feasibility_advisor import compute_feasibility_map
from architecture.services.feasibility_serializer import (
    FEASIBILITY_CACHE_SCHEMA_VERSION,
    feasibility_to_dict,
)
from architecture.regulatory.fsi_policy import (
    resolve_fsi_policy,
    infer_zone_from_plot,
    infer_authority,
)
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta
from ai_layer.client import call_openai, parse_json_response
from ai_layer.config import get_ai_config
from services.plot_exploration_prompt import build_exploration_prompt

logger = logging.getLogger(__name__)

# ── Sellable ratio interpolation table ─────────────────────────────────────
# (achieved_fsi, sellable_sqyd_per_sqyd_of_plot)
_SELLABLE_TABLE = [
    (1.8, 28.0),
    (2.7, 42.0),
    (3.6, 54.0),
    (4.0, 60.0),
]

# Segment average carpet areas (sqm)
_SEGMENT_AVG_CARPET = {
    "budget": 45.0,
    "mid": 65.0,
    "premium": 85.0,
    "luxury": 110.0,
}


def _interpolate_sellable_ratio(fsi: float) -> float:
    """Linear interpolation of sellable per sq.yd from FSI."""
    if fsi <= _SELLABLE_TABLE[0][0]:
        return _SELLABLE_TABLE[0][1]
    if fsi >= _SELLABLE_TABLE[-1][0]:
        return _SELLABLE_TABLE[-1][1]
    for i in range(len(_SELLABLE_TABLE) - 1):
        f0, s0 = _SELLABLE_TABLE[i]
        f1, s1 = _SELLABLE_TABLE[i + 1]
        if f0 <= fsi <= f1:
            t = (fsi - f0) / (f1 - f0) if f1 != f0 else 0.0
            return s0 + t * (s1 - s0)
    return _SELLABLE_TABLE[-1][1]


def _estimate_sellable(plot_area_sqm: float, fsi: float, segment: str) -> dict:
    """Compute sellable area estimates from FSI and segment."""
    plot_area_sqyd = plot_area_sqm / 0.8361
    sellable_per_sqyd = _interpolate_sellable_ratio(fsi)
    sellable_sqyd = plot_area_sqyd * sellable_per_sqyd
    sellable_sqm = sellable_sqyd * 0.8361
    avg_unit_area = _SEGMENT_AVG_CARPET.get(segment, 65.0)
    estimated_total_units = int(sellable_sqm / avg_unit_area) if avg_unit_area > 0 else 0
    return {
        "estimatedSellableAreaSqm": round(sellable_sqm, 0),
        "sellablePerSqYd": round(sellable_per_sqyd, 1),
        "estimatedTotalUnits": estimated_total_units,
    }


def _build_setback_annotations(plot, road_edge_indices: list[int]) -> tuple[list, list, list]:
    """
    Compute per-edge setback annotations and envelope coordinates.

    Returns (setback_distances, road_edges_annotated, envelope_coords).
    """
    setback_distances = []
    road_edges_annotated = []

    if plot.geom is None:
        return setback_distances, road_edges_annotated, []

    coords = list(plot.geom.coords[0])
    n_edges = len(coords) - 1
    road_width_m = float(plot.road_width_m or 0.0)

    for i in range(n_edges):
        is_road = i in road_edge_indices
        edge_type = "road" if is_road else "side"
        if is_road:
            distance_m = _get_road_margin(road_width_m)
            road_edges_annotated.append({
                "edgeIndex": i,
                "roadWidthM": road_width_m,
                "setbackM": distance_m,
            })
        else:
            distance_m = 3.0
            if n_edges >= 3 and road_edge_indices:
                opp = (road_edge_indices[0] + n_edges // 2) % n_edges
                if i == opp:
                    edge_type = "rear"

        setback_distances.append({
            "edgeIndex": i,
            "distanceM": distance_m,
            "type": edge_type,
        })

    envelope_coords_list = []
    try:
        from shapely.geometry import shape as shapely_shape
        plot_shapely = shapely_shape({
            "type": "Polygon",
            "coordinates": [[(c[0], c[1]) for c in coords]],
        })
        min_setback_dxf = min(s["distanceM"] for s in setback_distances) / 0.3048 if setback_distances else 10.0
        envelope = plot_shapely.buffer(-min_setback_dxf)
        if not envelope.is_empty and envelope.geom_type == "Polygon":
            envelope_coords_list = [list(c) for c in envelope.exterior.coords]
    except Exception:
        pass

    return setback_distances, road_edges_annotated, envelope_coords_list


def _get_road_margin(road_width_m: float) -> float:
    """Get road margin from GDCR Table 6.24 simplified."""
    if road_width_m <= 15:
        return 3.0
    elif road_width_m <= 18:
        return 4.5
    elif road_width_m <= 30:
        return 6.0
    else:
        return 9.0


def _build_unit_compatibility(fmap_dict: dict) -> dict:
    """Extract unit compatibility from feasibility's recommended tower option."""
    compat = fmap_dict.get("floorPlanCompat", {})
    return {
        "1BHK": compat.get("canFit1bhk", True),
        "2BHK": compat.get("canFit2bhk", True),
        "3BHK": compat.get("canFit3bhk", True),
        "4BHK": compat.get("canFit4bhk", False),
    }


def _generate_ai_scenarios(context: dict) -> Optional[list[dict]]:
    """Call GPT-4o to generate 3 development scenarios."""
    config = get_ai_config()
    system_prompt, user_prompt = build_exploration_prompt(context)

    raw = call_openai(
        model=config.exploration_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_s=config.exploration_timeout_s,
        temperature=0.3,
        rate_limit_kind="advisor",
        max_tokens=config.exploration_max_tokens,
    )

    if raw is None:
        logger.warning("AI exploration call returned None")
        return None

    parsed = parse_json_response(raw)
    if parsed is None:
        logger.warning("AI exploration response failed to parse. First 500 chars: %s", raw[:500])
        return None

    scenarios = parsed.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) == 0:
        logger.warning("AI returned no scenarios")
        return None

    return scenarios


def _generate_fallback_scenarios(fmap_dict: dict, context: dict) -> list[dict]:
    """Deterministic fallback when AI is unavailable."""
    max_towers = context["maxFeasibleTowers"]
    max_floors = context["maxFloors"]
    recommended_towers = fmap_dict.get("recommendedTowers", 1)
    recommended_floors = fmap_dict.get("recommendedFloors", max_floors)
    compat = context["unitCompatibility"]
    compatible = [k for k, v in compat.items() if v]

    btypes = context.get("permissibleBuildingTypes", [])
    bt_id = btypes[-1]["id"] if btypes else 2

    scenarios = [
        {
            "id": "high_density",
            "label": "High Density",
            "description": "Maximize sellable area with compact units",
            "towers": max_towers,
            "floors": max_floors,
            "buildingType": bt_id,
            "segment": "budget",
            "unitMix": compatible[:2] if len(compatible) >= 2 else compatible,
            "unitsPerCore": 6,
            "estimatedFSI": context["maxFSI"],
            "tradeoffNote": "Maximum unit count, smaller open spaces",
        },
        {
            "id": "balanced",
            "label": "Balanced",
            "description": "Good mix of density and livability",
            "towers": max(1, recommended_towers),
            "floors": recommended_floors,
            "buildingType": btypes[len(btypes) // 2]["id"] if btypes else 2,
            "segment": "mid",
            "unitMix": ["2BHK", "3BHK"] if "2BHK" in compatible and "3BHK" in compatible else compatible[:2],
            "unitsPerCore": 4,
            "estimatedFSI": round(context["baseFSI"] * 1.5, 2),
            "tradeoffNote": "Balanced density and open space",
        },
        {
            "id": "premium",
            "label": "Premium",
            "description": "Fewer towers, larger units, premium positioning",
            "towers": 1,
            "floors": recommended_floors,
            "buildingType": btypes[0]["id"] if btypes else 1,
            "segment": "luxury",
            "unitMix": compatible[-2:] if len(compatible) >= 2 else compatible,
            "unitsPerCore": 4,
            "estimatedFSI": context["baseFSI"],
            "tradeoffNote": "Maximum value per unit, large open spaces",
        },
    ]
    return scenarios


def _clamp_scenario(scenario: dict, context: dict) -> dict:
    """Validate and clamp a scenario to respect constraints."""
    scenario["towers"] = max(1, min(scenario.get("towers", 1), context["maxFeasibleTowers"]))
    scenario["floors"] = max(1, min(scenario.get("floors", 1), context["maxFloors"]))
    scenario["estimatedFSI"] = min(scenario.get("estimatedFSI", 1.8), context["maxFSI"])

    permissible_ids = {bt["id"] for bt in context.get("permissibleBuildingTypes", [])}
    if scenario.get("buildingType") not in permissible_ids and permissible_ids:
        scenario["buildingType"] = max(permissible_ids)

    compat = context.get("unitCompatibility", {})
    scenario["unitMix"] = [u for u in scenario.get("unitMix", []) if compat.get(u, False)]
    if not scenario["unitMix"]:
        scenario["unitMix"] = [k for k, v in compat.items() if v][:2]

    return scenario


def explore_plot(plot_id: str) -> dict[str, Any]:
    """
    Main orchestrator for plot exploration.

    Returns a dict matching the ExplorationResponse schema.
    """
    # 1. Load plot
    plot = get_plot_by_public_id(plot_id)
    road_width_m = float(plot.road_width_m or 0.0)

    # 2. Compute or load cached feasibility
    has_cached = (
        plot.cached_feasibility_json is not None
        and abs(float(plot.cached_feasibility_storey_height_m or 0.0) - 3.0) < 1e-9
        and int(
            plot.cached_feasibility_json.get("_feasibilityCacheSchemaVersion", 0)
        )
        == FEASIBILITY_CACHE_SCHEMA_VERSION
    )
    if has_cached:
        fmap_dict = dict(plot.cached_feasibility_json)
    else:
        fmap = compute_feasibility_map(plot=plot, storey_height_m=3.0)
        fmap_dict = feasibility_to_dict(fmap)
        plot.cached_feasibility_json = fmap_dict
        plot.cached_feasibility_storey_height_m = 3.0
        plot.cached_metrics_updated_at = timezone.now()
        plot.save(update_fields=[
            "cached_feasibility_json",
            "cached_feasibility_storey_height_m",
            "cached_metrics_updated_at",
        ])

    fmap_dict.pop("_feasibilityCacheSchemaVersion", None)

    # 3. FSI policy
    fsi_policy = resolve_fsi_policy(
        plot=plot,
        road_width_m=road_width_m,
    )

    # 4. Road edges
    road_edge_indices, _fallback_used = detect_road_edges_with_meta(plot.geom, None)

    # 5. Setback annotations
    setback_distances, road_edges_annotated, envelope_coords = _build_setback_annotations(
        plot, road_edge_indices
    )

    # 6. Build context for AI + response
    zone = infer_zone_from_plot(plot)
    authority = infer_authority()
    plot_area_sqm = fmap_dict.get("plotAreaSqm", 0.0)
    unit_compat = _build_unit_compatibility(fmap_dict)

    context = {
        "plotAreaSqm": plot_area_sqm,
        "roadWidthM": road_width_m,
        "zone": zone,
        "authority": authority,
        "maxHeightM": fmap_dict.get("maxHeightM", 0.0),
        "maxFloors": fmap_dict.get("maxFloors", 0),
        "maxFSI": fmap_dict.get("maxFSI", 0.0),
        "baseFSI": fsi_policy.base_fsi,
        "maxGCPct": fmap_dict.get("maxGCPct", 0.0),
        "maxFeasibleTowers": fmap_dict.get("maxFeasibleTowers", 0),
        "corridorEligible": fsi_policy.corridor_eligible,
        "corridorReason": fsi_policy.notes[0] if fsi_policy.notes else "",
        "unitCompatibility": unit_compat,
        "permissibleBuildingTypes": fmap_dict.get("permissibleBuildingTypes", []),
    }

    # 7. AI scenarios (with fallback)
    ai_scenarios = _generate_ai_scenarios(context)
    if ai_scenarios is None:
        logger.info("Using fallback scenarios for plot %s", plot_id)
        scenarios = _generate_fallback_scenarios(fmap_dict, context)
    else:
        scenarios = ai_scenarios

    # 8. Clamp and add sellable estimates
    for s in scenarios:
        s = _clamp_scenario(s, context)
        sellable = _estimate_sellable(
            plot_area_sqm,
            s.get("estimatedFSI", 1.8),
            s.get("segment", "mid"),
        )
        s.update(sellable)

    # 9. Build premium tiers from FSI policy
    from rules_engine.rules.loader import get_gdcr_config
    gdcr = get_gdcr_config() or {}
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    raw_tiers = fsi_cfg.get("premium_tiers") or []
    premium_tiers = []
    for t in raw_tiers:
        premium_tiers.append({
            "fromFSI": float(t.get("from_fsi", 0)),
            "toFSI": float(t.get("resulting_cap", 0)),
            "rate": float(t.get("premium_pct", 0)) / 100.0,
        })

    # 10. Build response
    return {
        "plotSummary": {
            "plotId": plot_id,
            "areaSqm": round(plot_area_sqm, 1),
            "roadWidthM": road_width_m,
            "zone": zone,
            "authority": authority,
            "designation": getattr(plot, "designation", "") or "",
        },
        "constraints": {
            "maxHeightM": context["maxHeightM"],
            "maxFloors": context["maxFloors"],
            "maxFSI": context["maxFSI"],
            "baseFSI": context["baseFSI"],
            "corridorEligible": context["corridorEligible"],
            "corridorReason": context["corridorReason"],
            "maxGroundCoverPct": context["maxGCPct"],
            "maxFeasibleTowers": context["maxFeasibleTowers"],
            "setbacks": {
                "road": _get_road_margin(road_width_m),
                "side": 3.0,
                "rear": 3.0,
            },
            "premiumTiers": premium_tiers,
            "permissibleBuildingTypes": fmap_dict.get("permissibleBuildingTypes", []),
        },
        "unitCompatibility": unit_compat,
        "scenarios": scenarios,
        "plotAnnotations": {
            "roadEdges": road_edges_annotated,
            "setbackDistances": setback_distances,
            "envelopeCoords": envelope_coords,
        },
    }
