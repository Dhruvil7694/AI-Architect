"""
api/views/floor_core.py
-----------------------
POST /api/development/floor-core/

Accepts a tower footprint and parameters, runs the circulation core
generator, and returns a GeoJSON layout + metrics + compliance.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from floorplan_engine.engine import generate_floor_core_layout

logger = logging.getLogger(__name__)


class FloorCoreLayoutAPIView(APIView):
    """
    Generate a circulation core layout for a single residential tower.

    Request body (JSON)::

        {
            "footprint": { GeoJSON Polygon in DXF coordinate space },
            "n_floors": 12,
            "building_height_m": 36.0,
            "target_units_per_floor": 6,
            "orientation_deg": null,
            "tower_type": "MID_RISE"
        }
    """

    def post(self, request, *args, **kwargs):
        data = request.data

        # ── Validate required fields ─────────────────────────────────────
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

        # ── Optional fields ──────────────────────────────────────────────
        target_units = data.get("target_units_per_floor", 6)
        orientation_deg = data.get("orientation_deg")
        tower_type = data.get("tower_type")

        tower_data = {
            "footprint": footprint,
            "n_floors": n_floors,
            "building_height_m": building_height_m,
            "target_units_per_floor": int(target_units),
            "tower_type": tower_type,
        }
        if orientation_deg is not None:
            tower_data["orientation_deg"] = float(orientation_deg)

        # ── Run engine ───────────────────────────────────────────────────
        try:
            result = generate_floor_core_layout(tower_data)
        except Exception as exc:
            logger.exception("FloorCoreLayoutAPIView: generation error: %s", exc)
            return Response(
                {"detail": "Internal error generating floor core layout."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if result.get("status") == "error":
            return Response(
                {"detail": result.get("error", "Layout error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(result, status=status.HTTP_200_OK)
