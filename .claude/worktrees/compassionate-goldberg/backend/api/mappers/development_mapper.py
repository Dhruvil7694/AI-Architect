from __future__ import annotations

from typing import Dict, Any

from architecture.services.development_pipeline import DevelopmentFloorPlanResult
from utils.geometry_geojson import wkt_to_geojson


def map_development_result_to_dict(
    result: DevelopmentFloorPlanResult,
    geometry_format: str = "geojson",
) -> Dict[str, Any]:
    """
    Convert a DevelopmentFloorPlanResult into a JSON-serialisable dict.

    Rules:
      - Domain failures (status != "OK") return only status + failure metadata.
      - Success returns configuration, geometry, and per-tower layout DTOs.
      - Engine-internal contracts (e.g. raw_contract, building_layout internals)
        are never exposed directly.

    Geometry format:
      - geometry_format = "geojson" (default) → GeoJSON dicts.
      - geometry_format = "wkt"              → raw WKT strings.
    """
    if result.status != "OK":
        return {
            "status": result.status,
            "failure_reason": result.failure_reason,
            "failure_details": result.failure_details,
        }

    fmt = (geometry_format or "geojson").lower()
    use_geojson = fmt == "geojson"

    def _map_geom(wkt: str | None):
        if not wkt:
            return None
        if use_geojson:
            return wkt_to_geojson(wkt)
        return wkt

    placement_payload = None
    if result.placement_summary is not None:
        ps = result.placement_summary
        placement_payload = {
            "n_towers": ps.n_towers,
            "per_tower_footprint_sqft": ps.per_tower_footprint_sqft,
            "spacing_required_m": ps.spacing_required_m,
            "spacing_provided_m": ps.spacing_provided_m,
        }

    towers_payload = []
    for dto in result.tower_floor_layouts:
        area_metrics = None
        ab = getattr(dto, "area_breakdown", None)
        if ab is not None:
            area_metrics = {
                "gross_bua_sqm": ab.gross_built_up_sqm,
                "core_area_sqm": ab.core_area_sqm,
                "corridor_area_sqm": ab.corridor_area_sqm,
                "common_area_sqm": ab.common_area_total_sqm,
                "carpet_total_sqm": ab.rera_carpet_area_total_sqm,
                "carpet_per_unit": list(ab.carpet_per_unit),
                "efficiency_ratio": ab.efficiency_ratio_recomputed,
                "carpet_to_bua_ratio": ab.carpet_to_bua_ratio,
            }

        towers_payload.append(
            {
                "tower_index": dto.tower_index,
                "floor_id": dto.floor_id,
                "total_units": dto.total_units,
                "efficiency_ratio_floor": dto.efficiency_ratio_floor,
                "unit_area_sum_sqm": dto.unit_area_sum_sqm,
                "footprint": _map_geom(dto.footprint_polygon_wkt),
                "core": _map_geom(dto.core_polygon_wkt),
                "corridor": _map_geom(dto.corridor_polygon_wkt),
                "area_metrics": area_metrics,
            }
        )

    payload: Dict[str, Any] = {
        "status": "OK",
        "configuration": {
            "n_towers": result.n_towers,
            "floors": result.floors,
            "height_m": result.height_m,
            "achieved_fsi": result.achieved_fsi,
            "fsi_utilization_pct": result.fsi_utilization_pct,
            "total_bua_sqft": result.total_bua_sqft,
            "gc_utilization_pct": result.gc_utilization_pct,
            "controlling_constraint": result.controlling_constraint,
        },
        "geometry": {
            "envelope": _map_geom(result.envelope_wkt),
            "placement": placement_payload,
        },
        "towers": towers_payload,
    }

    # Optionally expose minimal building-level metadata if present.
    if result.building_layout is not None:
        bl = result.building_layout
        payload["building"] = {
            "building_id": bl.building_id,
            "total_floors": bl.total_floors,
            "total_units": bl.total_units,
            "total_unit_area": bl.total_unit_area,
            "total_residual_area": bl.total_residual_area,
            "building_efficiency": bl.building_efficiency,
            "building_height_m": bl.building_height_m,
        }

    return payload


