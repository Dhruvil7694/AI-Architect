from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from services.plot_service import get_plot_by_public_id
from architecture.services.feasibility_advisor import (
    compute_feasibility_map,
    validate_user_request,
)
from architecture.services.feasibility_serializer import (
    FEASIBILITY_CACHE_SCHEMA_VERSION,
    feasibility_to_dict,
)
from ai_planner.feasibility_suggestions import generate_feasibility_suggestions

logger = logging.getLogger(__name__)

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
        use_default_cache = abs(storey_height_m - 3.0) < 1e-9
        has_cached = (
            use_default_cache
            and plot.cached_feasibility_json is not None
            and abs(float(plot.cached_feasibility_storey_height_m or 0.0) - 3.0) < 1e-9
            and int(
                plot.cached_feasibility_json.get("_feasibilityCacheSchemaVersion", 0)
            )
            == FEASIBILITY_CACHE_SCHEMA_VERSION
        )

        if has_cached:
            fmap_dict = dict(plot.cached_feasibility_json)
        else:
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

            fmap_dict = feasibility_to_dict(fmap)
            if use_default_cache:
                plot.cached_feasibility_json = fmap_dict
                plot.cached_feasibility_storey_height_m = 3.0
                plot.cached_metrics_updated_at = timezone.now()
                plot.save(
                    update_fields=[
                        "cached_feasibility_json",
                        "cached_feasibility_storey_height_m",
                        "cached_metrics_updated_at",
                    ]
                )

        # Generate suggestions (rule-based; AI-enhanced when key is set)
        try:
            suggestions = generate_feasibility_suggestions(fmap_dict)
            fmap_dict["suggestions"] = suggestions
        except Exception as exc:
            logger.warning("Suggestions failed: %s", exc)

        fmap_dict.pop("_feasibilityCacheSchemaVersion", None)
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

        fmap_dict = feasibility_to_dict(fmap)

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
