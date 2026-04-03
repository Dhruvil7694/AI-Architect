from __future__ import annotations

from typing import Any

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tp_ingestion.models import BlockLabel
from api.serializers.block_labels import BlockLabelSerializer
from services.plot_service import build_tp_scheme_query


class BlockLabelListAPIView(APIView):
    permission_classes = [AllowAny]

    """
    Return CAD overlay block labels (layer BLOCK_NO) as GeoJSON points.

    Optional query params:
      - tp_scheme (e.g. "TP14")
      - city (e.g. "Surat")
    """

    def get(self, request, *args: Any, **kwargs: Any) -> Response:
        tp_scheme = request.query_params.get("tp_scheme")
        city = request.query_params.get("city")

        qs = BlockLabel.objects.select_related("plot").all()
        if tp_scheme:
            qs = qs.filter(build_tp_scheme_query(tp_scheme, "plot__tp_scheme"))
        if city:
            qs = qs.filter(plot__city__iexact=city.strip())

        serializer = BlockLabelSerializer(qs, many=True)
        return Response(serializer.data)

