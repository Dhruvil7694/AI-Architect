"""
api/views/ai_floor_plan.py
----------------------------
POST /api/development/ai-floor-plan/

AI-powered floor plan generation using GPT-4o.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.ai_floor_plan_service import generate_ai_floor_plan

logger = logging.getLogger(__name__)


class AIFloorPlanAPIView(APIView):
    """
    Generate an AI-powered typical floor plan for a single residential tower.

    Request body (JSON):
    {
        "footprint": { GeoJSON Polygon in DXF coordinate space },
        "n_floors": 12,
        "building_height_m": 36.0,
        "units_per_core": 4,
        "building_type": 2,
        "segment": "mid",
        "unit_mix": ["2BHK", "3BHK"],
        "storey_height_m": 3.0,
        "plot_area_sqm": 2500.0,
        "design_brief": "",
        "image_model": "dalle3"
    }

    image_model: dalle3 | gemini | recraft | ideogram | flux | svg_only
    Recraft: set RECRAFT_API_KEY in the environment; optional RECRAFT_MODEL (default recraftv4),
    RECRAFT_SIZE (default 16:9), RECRAFT_STYLE (v2/v3 only), RECRAFT_NEGATIVE_PROMPT (v2/v3 only),
    RECRAFT_TIMEOUT_S.
    """

    def post(self, request, *args, **kwargs):
        data = request.data

        # ── Validate required fields ──
        footprint = data.get("footprint")
        if not footprint or footprint.get("type") != "Polygon":
            return Response(
                {"detail": "'footprint' must be a GeoJSON Polygon object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        n_floors = data.get("n_floors")
        if not isinstance(n_floors, int) or n_floors < 1:
            return Response(
                {"detail": "'n_floors' must be a positive integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        building_height_m = data.get("building_height_m")
        try:
            building_height_m = float(building_height_m)
        except (TypeError, ValueError):
            return Response(
                {"detail": "'building_height_m' must be a number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units_per_core = int(data.get("units_per_core", 4))
        building_type = int(data.get("building_type", 2))
        segment = str(data.get("segment", "mid"))
        unit_mix = data.get("unit_mix", [])
        if not isinstance(unit_mix, list):
            unit_mix = []
        storey_height_m = float(data.get("storey_height_m", 3.0))
        plot_area_sqm = float(data.get("plot_area_sqm", 0.0))
        design_brief = str(data.get("design_brief", ""))
        image_model = str(data.get("image_model", "dalle3"))

        # ── Run AI floor plan engine ──
        try:
            result = generate_ai_floor_plan(
                footprint_geojson=footprint,
                n_floors=n_floors,
                building_height_m=building_height_m,
                units_per_core=units_per_core,
                building_type=building_type,
                segment=segment,
                unit_mix=unit_mix,
                storey_height_m=storey_height_m,
                plot_area_sqm=plot_area_sqm,
                design_brief=design_brief,
                image_model=image_model,
            )
        except Exception as exc:
            logger.exception("AIFloorPlanAPIView: generation error: %s", exc)
            return Response(
                {"detail": "Internal error generating AI floor plan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if result.get("status") == "error":
            return Response(
                {"detail": result.get("error", "AI layout error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(result, status=status.HTTP_200_OK)
