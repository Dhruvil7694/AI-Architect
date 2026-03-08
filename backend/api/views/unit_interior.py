"""
api/views/unit_interior.py
---------------------------
POST /api/development/unit-interior/

Given unit type and clear dimensions, generate a GDCR-compliant room layout
for Stage 3 (unit interior design) of the planner.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from services.unit_interior_service import generate_unit_interior

logger = logging.getLogger(__name__)


class UnitInteriorAPIView(APIView):
    """
    Generate a room-level layout for a single residential unit.

    Request body:
    {
        "unit_type":    "2BHK",
        "unit_width_m": 6.0,
        "unit_depth_m": 7.5
    }
    """

    def post(self, request, *args, **kwargs):
        data = request.data

        unit_type = data.get("unit_type", "2BHK")
        if not isinstance(unit_type, str):
            return Response(
                {"detail": "'unit_type' must be a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            unit_width_m = float(data.get("unit_width_m", 6.0))
            unit_depth_m = float(data.get("unit_depth_m", 7.5))
        except (TypeError, ValueError):
            return Response(
                {"detail": "'unit_width_m' and 'unit_depth_m' must be numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if unit_width_m <= 0 or unit_depth_m <= 0:
            return Response(
                {"detail": "Unit dimensions must be positive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        design_brief = str(data.get("design_brief", "")).strip()

        try:
            result = generate_unit_interior(
                unit_type=unit_type,
                unit_width_m=unit_width_m,
                unit_depth_m=unit_depth_m,
                design_brief=design_brief,
            )
        except Exception as exc:
            logger.exception("UnitInteriorAPIView: %s", exc)
            return Response(
                {"detail": "Internal error generating unit interior."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if result.get("status") == "error":
            return Response(
                {"detail": result.get("error", "Layout error")},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(result, status=status.HTTP_200_OK)
