from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from django.contrib.gis.db.models import Extent
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers.block_labels import BlockLabelSerializer
from api.serializers.plots import PlotSerializer
from api.serializers.roads import RoadSerializer
from services.plot_service import build_tp_scheme_query, get_plot_by_public_id, list_plots
from tp_ingestion.models import BlockLabel, Plot, Road

class PlotListAPIView(APIView):
    permission_classes = [AllowAny]
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
        search: Optional[str] = request.query_params.get("search") or None
        tp_scheme: Optional[str] = request.query_params.get("tp_scheme") or None
        city: Optional[str] = request.query_params.get("city") or None
        try:
            limit = int(request.query_params.get("limit")) if request.query_params.get("limit") else None
        except (TypeError, ValueError):
            limit = None
        try:
            offset = int(request.query_params.get("offset")) if request.query_params.get("offset") else None
        except (TypeError, ValueError):
            offset = None

        plots_qs, total = list_plots(
            tp_scheme=tp_scheme,
            city=city,
            search=search,
            limit=limit,
            offset=offset,
        )

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


def _infer_kind(designation: str | None) -> str:
    d = (designation or "").upper()
    if "ROAD" in d:
        return "road"
    if "RESIDENTIAL" in d or "SALE FOR RES" in d:
        return "residential"
    if "COMMERCIAL" in d or "SALE FOR COM" in d:
        return "commercial"
    if "PUBLIC" in d:
        return "public"
    if "OPEN SPACE" in d or "GARDEN" in d:
        return "open_space"
    if "S.E.W" in d or "SEWAGE" in d or "E.W.S" in d:
        return "sewage"
    return "other"


def _fp_label_from_name(name: str) -> str:
    upper = name.upper().strip()
    if upper.startswith("FP "):
        return name[3:].strip()
    return name.strip()


def _road_label(name: str | None, width_m: float | None) -> str:
    if isinstance(width_m, (int, float)):
        width = float(width_m)
        return f"{width:.0f} m Road" if width.is_integer() else f"{width:.1f} m Road"
    if name:
        return name
    return "Road"


def _merge_extents(extents: list[Any]) -> list[float]:
    valid = [e for e in extents if e and len(e) == 4]
    if not valid:
        return [0.0, 0.0, 1.0, 1.0]
    min_x = min(float(e[0]) for e in valid)
    min_y = min(float(e[1]) for e in valid)
    max_x = max(float(e[2]) for e in valid)
    max_y = max(float(e[3]) for e in valid)
    if min_x == max_x:
        max_x += 1.0
    if min_y == max_y:
        max_y += 1.0
    return [min_x, min_y, max_x, max_y]


def _normalize_file_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _tp_scheme_number(tp_scheme: str) -> str:
    return "".join(ch for ch in tp_scheme if ch.isdigit())


@lru_cache(maxsize=64)
def _resolve_tp_source_files(tp_scheme: str) -> dict[str, str | None]:
    """
    Best-effort source file discovery under repository tp_data/.
    """
    backend_root = Path(__file__).resolve().parents[2]
    repo_root = backend_root.parent
    tp_data_root = repo_root / "tp_data"
    if not tp_data_root.exists():
        return {"dxfFile": None, "excelFile": None}

    scheme_norm = _normalize_file_name(tp_scheme)
    scheme_num = _tp_scheme_number(tp_scheme)
    candidates = list(tp_data_root.rglob("*"))

    dxf_files = [p for p in candidates if p.is_file() and p.suffix.lower() == ".dxf"]
    excel_files = [
        p
        for p in candidates
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xls", ".csv"}
    ]

    def score(path: Path) -> tuple[int, int]:
        normalized = _normalize_file_name(path.name)
        s = 0
        if scheme_norm and scheme_norm in normalized:
            s += 4
        if scheme_num and scheme_num in normalized:
            s += 2
        if "TP" in normalized:
            s += 1
        return (s, len(path.name))

    chosen_dxf = max(dxf_files, key=score, default=None)
    chosen_excel = max(excel_files, key=score, default=None)

    return {
        "dxfFile": chosen_dxf.name if chosen_dxf else None,
        "excelFile": chosen_excel.name if chosen_excel else None,
    }


class PlotDetailAPIView(APIView):
    """
    Get a single plot by id. Id format: "{tp_scheme}-{fp}", e.g. "TP14-1".
    """

    def get(self, request: Request, id: str, *args: Any, **kwargs: Any) -> Response:
        try:
            plot = get_plot_by_public_id(id)
        except (Plot.DoesNotExist, ValueError):
            return Response(
                {"detail": "Plot not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PlotSerializer(plot)
        return Response(serializer.data)


class TpBundleAPIView(APIView):
    permission_classes = [AllowAny]

    """
    Return a TP-scoped map bundle for planner rendering.

    Query params:
      - tp_scheme: required TP identifier (e.g. TP14)
      - city: optional city filter
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        tp_scheme = request.query_params.get("tp_scheme")
        city = request.query_params.get("city")
        if not tp_scheme:
            return Response(
                {"error": "tp_scheme query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        source_files = _resolve_tp_source_files(tp_scheme)

        plots_qs, _ = list_plots(tp_scheme=tp_scheme, city=city)
        plot_items = list(PlotSerializer(plots_qs, many=True).data)

        fp_polygon_features: list[dict[str, Any]] = []
        fp_label_point_features: list[dict[str, Any]] = []
        for item in plot_items:
            geometry = item.get("geometry")
            if not geometry:
                continue
            plot_id = str(item.get("id", ""))
            plot_name = str(item.get("name", ""))
            designation = str(item.get("designation") or "")
            area_sqm = float(item.get("areaSqm") or 0.0)
            fp_label = _fp_label_from_name(plot_name)

            fp_polygon_features.append(
                {
                    "type": "Feature",
                    "id": plot_id,
                    "geometry": geometry,
                    "properties": {
                        "plotId": plot_id,
                        "name": plot_name,
                        "fpLabel": fp_label,
                        "areaSqm": area_sqm,
                        "designation": designation,
                        "roadWidthM": item.get("roadWidthM"),
                        "kind": _infer_kind(designation),
                    },
                }
            )

            label_point = item.get("labelPoint")
            if (
                isinstance(label_point, list)
                and len(label_point) >= 2
                and isinstance(label_point[0], (int, float))
                and isinstance(label_point[1], (int, float))
            ):
                fp_label_point_features.append(
                    {
                        "type": "Feature",
                        "id": f"{plot_id}-label",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(label_point[0]), float(label_point[1])],
                        },
                        "properties": {
                            "plotId": plot_id,
                            "fpLabel": fp_label,
                            "areaSqm": area_sqm,
                        },
                    }
                )

        roads_qs = Road.objects.filter(build_tp_scheme_query(tp_scheme))
        if city:
            roads_qs = roads_qs.filter(city__iexact=city.strip())
        road_items = list(RoadSerializer(roads_qs, many=True).data)
        road_features: list[dict[str, Any]] = []
        road_centerline_features: list[dict[str, Any]] = []
        for item in road_items:
            road_id = int(item.get("id"))
            width_m = item.get("widthM")
            label = _road_label(item.get("name"), width_m)
            if item.get("geometry"):
                road_features.append(
                    {
                        "type": "Feature",
                        "id": f"road-{road_id}",
                        "geometry": item["geometry"],
                        "properties": {
                            "roadId": road_id,
                            "name": item.get("name") or "",
                            "label": label,
                            "widthM": width_m,
                        },
                    }
                )
            if item.get("centerline"):
                road_centerline_features.append(
                    {
                        "type": "Feature",
                        "id": f"road-centerline-{road_id}",
                        "geometry": item["centerline"],
                        "properties": {
                            "roadId": road_id,
                            "name": item.get("name") or "",
                            "label": label,
                            "widthM": width_m,
                        },
                    }
                )

        block_labels_qs = BlockLabel.objects.select_related("plot").filter(
            build_tp_scheme_query(tp_scheme, "plot__tp_scheme")
        )
        if city:
            block_labels_qs = block_labels_qs.filter(plot__city__iexact=city.strip())
        block_label_items = list(BlockLabelSerializer(block_labels_qs, many=True).data)
        block_label_features: list[dict[str, Any]] = []
        for item in block_label_items:
            geometry = item.get("geometry")
            if not geometry:
                continue
            block_label_features.append(
                {
                    "type": "Feature",
                    "id": f"block-label-{item.get('id')}",
                    "geometry": geometry,
                    "properties": {
                        "labelId": str(item.get("id")),
                        "text": item.get("text") or "",
                        "plotId": item.get("plotId"),
                    },
                }
            )

        plots_extent_qs = Plot.objects.filter(build_tp_scheme_query(tp_scheme))
        if city:
            plots_extent_qs = plots_extent_qs.filter(city__iexact=city.strip())
        plot_extent = plots_extent_qs.aggregate(extent=Extent("geom")).get("extent")
        road_extent = roads_qs.aggregate(extent=Extent("geom")).get("extent")
        bbox = _merge_extents([plot_extent, road_extent])

        payload = {
            "meta": {
                "tpScheme": tp_scheme,
                "city": city,
                "coordSpace": "LOCAL_DXF",
                "srid": 0,
                "unitLinear": "foot",
                "unitArea": "sqft",
                "bbox": bbox,
                "ingestionVersion": "v1",
                "source": {
                    "dxfFile": source_files.get("dxfFile"),
                    "excelFile": source_files.get("excelFile"),
                },
            },
            "layers": {
                "fpPolygons": {
                    "type": "FeatureCollection",
                    "features": fp_polygon_features,
                },
                "fpLabelPoints": {
                    "type": "FeatureCollection",
                    "features": fp_label_point_features,
                },
                "roads": {
                    "type": "FeatureCollection",
                    "features": road_features,
                },
                "roadCenterlines": {
                    "type": "FeatureCollection",
                    "features": road_centerline_features,
                },
                "blockLabels": {
                    "type": "FeatureCollection",
                    "features": block_label_features,
                },
            },
            "stats": {
                "fpCount": len(fp_polygon_features),
                "roadCount": len(road_features),
                "blockLabelCount": len(block_label_features),
            },
        }
        return Response(payload)
