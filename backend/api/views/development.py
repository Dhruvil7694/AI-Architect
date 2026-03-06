from __future__ import annotations

import logging

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tp_ingestion.models import Plot

from architecture.services.development_pipeline import (
    generate_optimal_development_floor_plans,
)
from api.serializers.development import (
    OptimalDevelopmentRequestSerializer,
    SiteMetricsSerializer,
)
from api.mappers.development_mapper import map_development_result_to_dict
from services.site_metrics_service import compute_site_metrics


logger = logging.getLogger(__name__)


class SiteMetricsAPIView(APIView):
    """
    Compute baseline site metrics for a given plot.
    """

    def get(self, request, plot_id: str, *args, **kwargs):
        metrics = compute_site_metrics(plot_id)
        serializer = SiteMetricsSerializer(metrics)
        return Response(serializer.data)


class OptimalDevelopmentFloorPlanAPIView(APIView):
    """
    HTTP API wrapper around generate_optimal_development_floor_plans().

    This layer is intentionally thin:
      - Validates and normalises request data.
      - Resolves the Plot instance.
      - Delegates to the development pipeline service.
      - Maps the result DTO to a JSON-safe dict.
      - Handles HTTP vs domain failures distinctly.
    """

    def post(self, request, *args, **kwargs):
        serializer = OptimalDevelopmentRequestSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            logger.warning("Optimal development request validation failed: %s", exc)
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        tp = data["tp"]
        fp = data["fp"]
        geometry_format = data.get("geometry_format", "geojson")

        try:
            plot = Plot.objects.get(tp_scheme=f"TP{tp}", fp_number=str(fp))
        except Plot.DoesNotExist:
            logger.info("Plot not found for optimal development: TP%s FP%s", tp, fp)
            return Response(
                {"detail": "Plot not found"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            result = generate_optimal_development_floor_plans(
                plot=plot,
                storey_height_m=data.get("storey_height_m", 3.0),
                min_width_m=data.get("min_width_m", 5.0),
                min_depth_m=data.get("min_depth_m", 3.5),
                include_building_layout=data.get("include_building_layout", False),
                strict=data.get("strict", True),
            )
        except Exception as exc:  # noqa: BLE001
            # Internal error: log full stack trace, return generic 500 to caller.
            logger.exception(
                "Unexpected error in OptimalDevelopmentFloorPlanAPIView for TP%s FP%s: %s",
                tp,
                fp,
                exc,
            )
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Map domain result to JSON payload. Domain failures still use HTTP 200.
        payload = map_development_result_to_dict(result, geometry_format=geometry_format)

        # Minimal logging of outcome.
        if result.status == "OK":
            logger.info(
                "Optimal development OK for TP%s FP%s — n_towers=%s, floors=%s, constraint=%s",
                tp,
                fp,
                result.n_towers,
                result.floors,
                result.controlling_constraint,
            )
        else:
            logger.info(
                "Optimal development domain failure for TP%s FP%s — status=%s, reason=%s",
                tp,
                fp,
                result.status,
                result.failure_reason,
            )

        return Response(payload, status=status.HTTP_200_OK)

