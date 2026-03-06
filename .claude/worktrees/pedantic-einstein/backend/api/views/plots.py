from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.contrib.gis.geos import GEOSGeometry
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from tp_ingestion.models import Plot
from utils.geometry_geojson import wkt_to_geojson
from api.serializers.plots import PlotSerializer
from services.plot_service import list_plots, get_plot_by_public_id


class PlotListAPIView(APIView):
    """
    List available plots for site planning.

    Response schema (per plot):
      - tp: numeric TP code when parseable (e.g. 14 for "TP14"), else None
      - tp_scheme: raw TP scheme string (e.g. "TP14")
      - fp: FP number as string
      - area_sqft: plot area in sq.ft (from area_geometry)
      - area_sqm: plot area in sq.m
      - road_width_m: road width in metres (may be null)
      - geometry: envelope of the plot polygon, as GeoJSON by default or WKT
                  when geometry_format=wkt is provided as a query parameter.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        geometry_format = (
            request.query_params.get("geometry_format") or "geojson"
        ).lower()
        # Currently only GeoJSON is supported by the frontend contract.
        use_geojson = geometry_format == "geojson"

        search: Optional[str] = request.query_params.get("search") or None
        try:
            limit = int(request.query_params.get("limit")) if request.query_params.get("limit") else None
        except (TypeError, ValueError):
            limit = None
        try:
            offset = int(request.query_params.get("offset")) if request.query_params.get("offset") else None
        except (TypeError, ValueError):
            offset = None

        plots_qs, total = list_plots(search=search, limit=limit, offset=offset)

        # Use serializer for stable DTO contract.
        serializer = PlotSerializer(plots_qs, many=True)
        results = serializer.data

        # Backwards compatible: if client expects a plain list, they can use
        # the "results" array; the envelope adds pagination metadata.
        payload = {
            "results": results,
            "count": total,
            "limit": limit,
            "offset": offset,
        }
        return Response(payload)


def _plot_to_item(p: Plot, use_geojson: bool) -> Dict[str, Any]:
    tp_raw = p.tp_scheme
    tp_numeric = None
    if isinstance(tp_raw, str):
        try:
            tp_numeric = int(tp_raw.replace("TP", "").strip())
        except (TypeError, ValueError):
            tp_numeric = None
    geom = p.geom
    geom_wkt = geom.wkt if isinstance(geom, GEOSGeometry) else None
    geometry = wkt_to_geojson(geom_wkt) if use_geojson else geom_wkt
    return {
        "tp": tp_numeric,
        "tp_scheme": tp_raw,
        "fp": p.fp_number,
        "area_sqft": float(p.plot_area_sqft),
        "area_sqm": float(p.plot_area_sqm),
        "road_width_m": float(p.road_width_m) if p.road_width_m is not None else None,
        "designation": p.designation or None,
        "geometry": geometry,
    }


class PlotDetailAPIView(APIView):
    """
    Get a single plot by id. Id format: "{tp_scheme}-{fp}", e.g. "TP14-1".
    """

    def get(self, request: Request, id: str, *args: Any, **kwargs: Any) -> Response:
        from rest_framework import status

        geometry_format = (
            request.query_params.get("geometry_format") or "geojson"
        ).lower()
        use_geojson = geometry_format == "geojson"

        try:
            plot = get_plot_by_public_id(id)
        except (Plot.DoesNotExist, ValueError):
            return Response(
                {"detail": "Plot not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PlotSerializer(plot)
        return Response(serializer.data)

