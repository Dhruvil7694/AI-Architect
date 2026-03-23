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
from api.serializers.development_inputs import DevelopmentInputSerializer
from api.mappers.development_mapper import map_development_result_to_dict
from services.site_metrics_service import compute_site_metrics

from architecture.models.building_types import get_building_type
from architecture.models.core_config import compute_required_footprint_for_core
from architecture.regulatory_accessors import get_max_permissible_height_by_road_width


logger = logging.getLogger(__name__)


from rest_framework.permissions import AllowAny

class SiteMetricsAPIView(APIView):
    permission_classes = [AllowAny]
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

    Supports both the legacy OptimalDevelopmentRequestSerializer and the new
    DevelopmentInputSerializer.  The new serializer is tried first; if the
    request lacks new-format fields (building_type, units_per_core) the legacy
    path is used as a fallback.
    """

    def _is_new_format(self, request_data: dict) -> bool:
        """Detect whether the request uses the new input contract."""
        return "building_type" in request_data or "units_per_core" in request_data

    def post(self, request, *args, **kwargs):
        if self._is_new_format(request.data):
            return self._handle_new_format(request)
        return self._handle_legacy_format(request)

    # ------------------------------------------------------------------ #
    #  New-format handler (DevelopmentInputSerializer)
    # ------------------------------------------------------------------ #
    def _handle_new_format(self, request):
        serializer = DevelopmentInputSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            logger.warning("Development input validation failed: %s", exc)
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        tp = data["tp"]
        fp = data["fp"]
        geometry_format = data.get("geometry_format", "geojson")

        try:
            plot = Plot.objects.get(tp_scheme=f"TP{tp}", fp_number=str(fp))
        except Plot.DoesNotExist:
            logger.info("Plot not found: TP%s FP%s", tp, fp)
            return Response(
                {"detail": "Plot not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # --- Resolve building-type constraints ---
        road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
        bt = get_building_type(data["building_type"])

        # Effective height cap: min of road-based cap and building-type cap
        road_height_cap = get_max_permissible_height_by_road_width(road_width)
        effective_height_cap = min(road_height_cap, bt.max_height_m)

        storey_height_m = data.get("storey_height_m", 3.0)
        max_permissible_floors = int(effective_height_cap / storey_height_m)

        # Resolve floor count: user-selected or GDCR max
        user_floors = data.get("floors")
        if user_floors is not None:
            resolved_floors = min(user_floors, max_permissible_floors)
        else:
            resolved_floors = max_permissible_floors if max_permissible_floors > 0 else None

        # Compute min dimensions from core config using dominant unit type
        units_per_core = int(data["units_per_core"])
        unit_mix = data.get("unit_mix") or []
        dominant_unit = unit_mix[0] if unit_mix else "2BHK"

        fp_req = compute_required_footprint_for_core(
            units_per_core=units_per_core,
            unit_type=dominant_unit,
            building_height_m=effective_height_cap,
        )
        min_width_m = max(5.0, fp_req.min_footprint_width_m)
        min_depth_m = max(3.5, fp_req.min_footprint_depth_m)

        # Override tower count if user specified n_buildings
        forced_towers = data.get("n_buildings")

        try:
            result = generate_optimal_development_floor_plans(
                plot=plot,
                storey_height_m=storey_height_m,
                min_width_m=min_width_m,
                min_depth_m=min_depth_m,
                include_building_layout=data.get("include_building_layout", False),
                strict=True,
                building_type=data["building_type"],
                units_per_core=units_per_core,
                segment=data.get("segment", "mid"),
                user_floors=resolved_floors,
                n_buildings=forced_towers,
                unit_mix=unit_mix or None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unexpected error in OptimalDevelopmentFloorPlanAPIView (new) for TP%s FP%s: %s",
                tp, fp, exc,
            )
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        payload = map_development_result_to_dict(result, geometry_format=geometry_format)

        self._log_outcome(tp, fp, result)
        return Response(payload, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------ #
    #  Legacy handler (OptimalDevelopmentRequestSerializer)
    # ------------------------------------------------------------------ #
    def _handle_legacy_format(self, request):
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
            logger.exception(
                "Unexpected error in OptimalDevelopmentFloorPlanAPIView for TP%s FP%s: %s",
                tp, fp, exc,
            )
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        payload = map_development_result_to_dict(result, geometry_format=geometry_format)

        self._log_outcome(tp, fp, result)
        return Response(payload, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------ #
    #  Shared helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _log_outcome(tp, fp, result):
        if result.status == "OK":
            logger.info(
                "Optimal development OK for TP%s FP%s — n_towers=%s, floors=%s, constraint=%s",
                tp, fp, result.n_towers, result.floors, result.controlling_constraint,
            )
        else:
            logger.info(
                "Optimal development domain failure for TP%s FP%s — status=%s, reason=%s",
                tp, fp, result.status, result.failure_reason,
            )
