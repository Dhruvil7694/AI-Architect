"""
Roads API endpoints for GIS-grade cartographic rendering.
"""

from __future__ import annotations

import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from tp_ingestion.models import Road
from api.serializers.roads import RoadSerializer
from services.plot_service import build_tp_scheme_query

logger = logging.getLogger(__name__)


class RoadListAPIView(APIView):
    """
    List roads for a TP scheme.
    
    Query params:
      - tp_scheme: Filter by TP scheme (e.g. "TP14")
      - city: Filter by city (optional)
    
    Returns roads with centerlines and widths for line-based rendering.
    """
    
    permission_classes = [AllowAny]
    
    def get(self, request):
        tp_scheme = request.query_params.get("tp_scheme")
        city = request.query_params.get("city")
        
        if not tp_scheme:
            return Response(
                {"error": "tp_scheme query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        queryset = Road.objects.filter(build_tp_scheme_query(tp_scheme))
        
        if city:
            queryset = queryset.filter(city__iexact=city.strip())
        
        queryset = queryset.order_by("id")
        
        serializer = RoadSerializer(queryset, many=True)
        
        return Response({
            "roads": serializer.data,
            "count": len(serializer.data),
        })
