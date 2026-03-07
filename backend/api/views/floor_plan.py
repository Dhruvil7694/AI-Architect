"""
api/views/floor_plan.py
------------------------
POST /api/development/floor-plan/

Accepts a tower footprint and tower parameters, runs the floor plan generator,
and returns a GeoJSON layout + metrics.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.floor_plan_service import generate_floor_plan

logger = logging.getLogger(__name__)


class FloorPlanAPIView(APIView):
    """
    Generate a GDCR-compliant typical floor plan for a single residential tower.

    Request body (JSON):
    {
        "footprint": { GeoJSON Polygon in DXF coordinate space },
        "n_floors": 16,
        "building_height_m": 48.0,
        "unit_mix": ["2BHK", "3BHK"],
        "storey_height_m": 3.0,
        "plot_area_sqm": 2500.0
    }
    """

    def post(self, request, *args, **kwargs):
        data = request.data

        # ── Validate required fields ──────────────────────────────────────────
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

        unit_mix = data.get("unit_mix", ["2BHK", "3BHK"])
        if not isinstance(unit_mix, list) or not unit_mix:
            unit_mix = ["2BHK", "3BHK"]

        storey_height_m = float(data.get("storey_height_m", 3.0))
        plot_area_sqm   = float(data.get("plot_area_sqm", 0.0))

        # ── Run floor plan engine ─────────────────────────────────────────────
        try:
            result = generate_floor_plan(
                footprint_geojson=footprint,
                n_floors=n_floors,
                building_height_m=building_height_m,
                unit_mix=unit_mix,
                storey_height_m=storey_height_m,
                plot_area_sqm=plot_area_sqm,
            )
        except Exception as exc:
            logger.exception("FloorPlanAPIView: generation error: %s", exc)
            return Response(
                {"detail": "Internal error generating floor plan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if result.get("status") == "error":
            return Response(
                {"detail": result.get("error", "Layout error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(result, status=status.HTTP_200_OK)
