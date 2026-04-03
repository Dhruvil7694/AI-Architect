from __future__ import annotations

# Cached feasibility payloads with an older plot-area / DXF unit contract are ignored.
FEASIBILITY_CACHE_SCHEMA_VERSION = 2


def compat_to_dict(fp) -> dict:
    """Convert FloorPlanCompatibility to JSON-safe dict."""
    if fp is None:
        return {}
    return {
        "canFit1bhk": fp.can_fit_1bhk,
        "canFit2bhk": fp.can_fit_2bhk,
        "canFit3bhk": fp.can_fit_3bhk,
        "canFit4bhk": fp.can_fit_4bhk,
        "canFit5bhk": fp.can_fit_5bhk,
        "estimatedUnitsPerFloor": fp.estimated_units_per_floor,
        "footprintWidthM": round(fp.footprint_width_m, 1),
        "footprintDepthM": round(fp.footprint_depth_m, 1),
        "coreType": fp.core_type,
        "notes": fp.notes,
    }


def feasibility_to_dict(fmap) -> dict:
    """Convert FeasibilityMap dataclass to JSON-safe dict."""
    data = {
        "plotId": fmap.plot_id,
        "plotAreaSqm": round(fmap.plot_area_sqm, 1),
        "maxHeightM": fmap.max_height_m,
        "maxFloors": fmap.max_floors,
        "maxFSI": fmap.max_fsi,
        "maxGCPct": fmap.max_gc_pct,
        "roadWidthM": fmap.road_width_m,
        "maxFeasibleTowers": fmap.max_feasible_towers,
        "recommendedTowers": fmap.recommended_towers,
        "recommendedFloors": fmap.recommended_floors,
        "recommendationReason": fmap.recommendation_reason,
        "suggestions": fmap.suggestions,
        "towerOptions": [],
    }

    for t in fmap.tower_options:
        tower_dict = {
            "nTowers": t.n_towers,
            "isFeasible": t.is_feasible,
            "minFloors": t.min_floors,
            "maxFloors": t.max_floors,
            "estimatedFootprintSqm": t.estimated_footprint_sqm,
            "estimatedFsiAtMax": t.estimated_fsi_at_max,
            "heightBand": t.height_band,
            "footprintWidthM": t.footprint_width_m,
            "footprintDepthM": t.footprint_depth_m,
            "floorPlanNotes": t.floor_plan_notes,
            "reason": t.reason,
        }
        if t.floor_plan_compat:
            tower_dict["floorPlanCompat"] = compat_to_dict(t.floor_plan_compat)
        data["towerOptions"].append(tower_dict)

    if fmap.floor_plan_compat:
        data["floorPlanCompat"] = compat_to_dict(fmap.floor_plan_compat)

    data["permissibleBuildingTypes"] = fmap.permissible_building_types
    data["coreConfigs"] = fmap.core_configs
    data["sellableEstimate"] = fmap.sellable_estimate
    data["_feasibilityCacheSchemaVersion"] = FEASIBILITY_CACHE_SCHEMA_VERSION
    return data

