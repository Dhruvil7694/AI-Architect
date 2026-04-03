"""
Debug and validation API endpoints.
"""

from __future__ import annotations

from django.urls import path

from api.views.debug import GeoJSONExportAPIView, ValidationStatsAPIView


urlpatterns = [
    path("geojson-export/", GeoJSONExportAPIView.as_view(), name="geojson-export"),
    path("validation-stats/", ValidationStatsAPIView.as_view(), name="validation-stats"),
]
