from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from services.plot_exploration_service import explore_plot

logger = logging.getLogger(__name__)


class PlotExplorationAPIView(APIView):
    """
    GET /api/development/explore/{plot_id}/

    Returns GDCR constraints, 3 AI-generated development scenarios,
    and plot annotations for the exploration step.
    """

    permission_classes = [AllowAny]

    def get(self, request, plot_id: str, *args, **kwargs):
        try:
            result = explore_plot(plot_id)
        except Exception as exc:
            if "not found" in str(exc).lower() or "does not exist" in str(exc).lower():
                return Response(
                    {"detail": "Plot not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.exception("Plot exploration failed for %s: %s", plot_id, exc)
            return Response(
                {"detail": "Plot exploration failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK)
