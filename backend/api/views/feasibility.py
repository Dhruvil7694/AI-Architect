from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from services.plot_service import get_plot_by_public_id
from architecture.services.feasibility_advisor import (
    compute_feasibility_map,
    validate_user_request,
)
from ai_planner.feasibility_suggestions import generate_feasibility_suggestions

logger = logging.getLogger(__name__)


def _compat_to_dict(fp) -> dict:
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


def _feasibility_to_dict(fmap) -> dict:
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
        # Include per-tower floor plan compatibility
        if t.floor_plan_compat:
            tower_dict["floorPlanCompat"] = _compat_to_dict(t.floor_plan_compat)
        data["towerOptions"].append(tower_dict)

    # Global floor plan compat (from recommended config)
    if fmap.floor_plan_compat:
        data["floorPlanCompat"] = _compat_to_dict(fmap.floor_plan_compat)

    # New input constraints
    data["permissibleBuildingTypes"] = fmap.permissible_building_types
    data["coreConfigs"] = fmap.core_configs
    data["sellableEstimate"] = fmap.sellable_estimate

    return data


class FeasibilityAPIView(APIView):
    """
    GET /api/development/feasibility/{plot_id}/

    Returns per-tower-count feasibility (floors, footprint, FSI), regulatory
    limits, floor plan compatibility, and suggestions.
    """

    permission_classes = [AllowAny]

    def get(self, request, plot_id: str, *args, **kwargs):
        try:
            plot = get_plot_by_public_id(plot_id)
        except Exception:
            return Response(
                {"detail": "Plot not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        storey_height_m = float(request.query_params.get("storey_height_m", 3.0))

        try:
            fmap = compute_feasibility_map(
                plot=plot,
                storey_height_m=storey_height_m,
            )
        except Exception as exc:
            logger.exception("Feasibility computation failed for %s: %s", plot_id, exc)
            return Response(
                {"detail": "Feasibility computation failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        fmap_dict = _feasibility_to_dict(fmap)

        # Generate suggestions (rule-based; AI-enhanced when key is set)
        try:
            suggestions = generate_feasibility_suggestions(fmap_dict)
            fmap_dict["suggestions"] = suggestions
        except Exception as exc:
            logger.warning("Suggestions failed: %s", exc)

        return Response(fmap_dict, status=status.HTTP_200_OK)


class FeasibilityValidateAPIView(APIView):
    """
    POST /api/development/feasibility/{plot_id}/validate/

    Validate user inputs against plot feasibility.
    """

    permission_classes = [AllowAny]

    def post(self, request, plot_id: str, *args, **kwargs):
        try:
            plot = get_plot_by_public_id(plot_id)
        except Exception:
            return Response(
                {"detail": "Plot not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = request.data
        storey_height_m = float(data.get("storeyHeightM", 3.0))

        try:
            fmap = compute_feasibility_map(
                plot=plot,
                storey_height_m=storey_height_m,
            )
        except Exception as exc:
            logger.exception("Feasibility computation failed for %s: %s", plot_id, exc)
            return Response(
                {"detail": "Feasibility computation failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        validation = validate_user_request(
            feasibility=fmap,
            requested_towers=data.get("towerCount", "auto"),
            requested_min_floors=data.get("minFloors"),
            requested_max_floors=data.get("maxFloors"),
            requested_unit_mix=data.get("unitMix"),
        )

        fmap_dict = _feasibility_to_dict(fmap)

        user_context = {
            "requested_towers": data.get("towerCount"),
            "unit_mix": data.get("unitMix"),
        }
        try:
            suggestions = generate_feasibility_suggestions(fmap_dict, user_context)
            fmap_dict["suggestions"] = suggestions
        except Exception:
            pass

        return Response({
            "isValid": validation["is_valid"],
            "warnings": validation["warnings"],
            "errors": validation["errors"],
            "suggestions": validation["suggestions"],
            "feasibility": fmap_dict,
        }, status=status.HTTP_200_OK)
