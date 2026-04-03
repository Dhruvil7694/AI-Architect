"""
POST /api/development/floor-plan-preview-image/

Text-to-image preview from tower + optional AI floor plan context.
Does not call or modify the AI floor plan layout pipeline.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_layer.config import get_ai_config
from services.floor_plan_preview_image_service import (
    build_floor_plan_image_prompt,
    footprint_dimensions_m,
    generate_image_via_huggingface,
    image_bytes_to_base64_png,
)

logger = logging.getLogger(__name__)


class FloorPlanPreviewImageAPIView(APIView):
    """
    Request body (JSON), same base fields as AI floor plan plus optional context:

    {
      "footprint": { GeoJSON Polygon },
      "n_floors": 12,
      "building_height_m": 36.0,
      "units_per_core": 4,
      "segment": "mid",
      "unit_mix": ["2BHK", "3BHK"],
      "storey_height_m": 3.0,
      "plot_area_sqm": 0.0,
      "design_brief": "",
      "design_notes": "",
      "ai_metrics": { ... optional subset of AI floor plan metrics }
    }
    """

    def post(self, request, *args, **kwargs):
        data = request.data
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

        try:
            building_height_m = float(data.get("building_height_m"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "'building_height_m' must be a number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        w_m, d_m = footprint_dimensions_m(footprint)
        if w_m <= 0 or d_m <= 0:
            return Response(
                {"detail": "Could not derive footprint dimensions from polygon."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cfg = get_ai_config()
        token = cfg.huggingface_api_token
        if not token:
            return Response(
                {
                    "detail": (
                        "Image generation is not configured. Set HUGGINGFACE_API_TOKEN "
                        "in the server environment (see AI layer docs)."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        payload = {
            "footprint": footprint,
            "n_floors": n_floors,
            "building_height_m": building_height_m,
            "units_per_core": int(data.get("units_per_core", 4)),
            "building_type": int(data.get("building_type", 2)),
            "segment": str(data.get("segment", "mid")),
            "unit_mix": data.get("unit_mix") or [],
            "storey_height_m": float(data.get("storey_height_m", 3.0)),
            "plot_area_sqm": float(data.get("plot_area_sqm", 0.0)),
            "design_brief": str(data.get("design_brief", "")),
            "design_notes": str(data.get("design_notes", "")),
            "ai_metrics": data.get("ai_metrics"),
        }

        prompt = build_floor_plan_image_prompt(payload)

        try:
            raw = generate_image_via_huggingface(
                prompt,
                api_token=token,
                model_id=cfg.hf_image_model,
                timeout_s=cfg.hf_image_timeout_s,
            )
        except ValueError as exc:
            logger.warning("Floor plan preview image failed: %s", exc)
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            logger.exception("Floor plan preview image unexpected error: %s", exc)
            return Response(
                {"detail": "Image generation failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        b64, mime = image_bytes_to_base64_png(raw)
        return Response(
            {
                "status": "ok",
                "mime_type": mime,
                "image_base64": b64,
                "prompt_used": prompt,
            },
            status=status.HTTP_200_OK,
        )
