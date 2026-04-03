"""
Debug and validation endpoints for GIS data export.

Provides GeoJSON exports for validation in QGIS or other GIS tools.
"""

from __future__ import annotations

import json
import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.http import JsonResponse

from tp_ingestion.models import Plot, Road, BlockLabel

logger = logging.getLogger(__name__)


class GeoJSONExportAPIView(APIView):
    """
    Export GeoJSON for debugging and validation.
    
    Query params:
      - tp_scheme: TP scheme to export (required)
      - city: City filter (optional)
      - layer: Specific layer to export (optional)
               Options: plots, roads, block_labels, label_points, all
               Default: all
    
    Returns GeoJSON FeatureCollection(s) for use in QGIS or other GIS tools.
    """
    
    permission_classes = [AllowAny]
    
    def get(self, request):
        tp_scheme = request.query_params.get("tp_scheme")
        city = request.query_params.get("city")
        layer = request.query_params.get("layer", "all")
        
        if not tp_scheme:
            return Response(
                {"error": "tp_scheme query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = {}
        
        # Export plots
        if layer in ["plots", "all"]:
            plots_qs = Plot.objects.filter(tp_scheme=tp_scheme)
            if city:
                plots_qs = plots_qs.filter(city=city)
            
            plot_features = []
            for plot in plots_qs:
                feature = {
                    "type": "Feature",
                    "id": f"{plot.tp_scheme}-{plot.fp_number}",
                    "geometry": json.loads(plot.geom.geojson),
                    "properties": {
                        "fp_number": plot.fp_number,
                        "city": plot.city,
                        "tp_scheme": plot.tp_scheme,
                        "area_sqm": float(plot.plot_area_sqm),
                        "area_sqft": float(plot.plot_area_sqft),
                        "designation": plot.designation or "",
                        "road_width_m": plot.road_width_m,
                        "validation_status": plot.validation_status,
                    },
                }
                plot_features.append(feature)
            
            result["plots"] = {
                "type": "FeatureCollection",
                "features": plot_features,
                "count": len(plot_features),
            }
        
        # Export label points
        if layer in ["label_points", "all"]:
            plots_qs = Plot.objects.filter(
                tp_scheme=tp_scheme,
                label_point__isnull=False
            )
            if city:
                plots_qs = plots_qs.filter(city=city)
            
            label_features = []
            for plot in plots_qs:
                feature = {
                    "type": "Feature",
                    "id": f"{plot.tp_scheme}-{plot.fp_number}-label",
                    "geometry": json.loads(plot.label_point.geojson),
                    "properties": {
                        "fp_number": plot.fp_number,
                        "label": f"FP {plot.fp_number}",
                        "city": plot.city,
                        "tp_scheme": plot.tp_scheme,
                    },
                }
                label_features.append(feature)
            
            result["label_points"] = {
                "type": "FeatureCollection",
                "features": label_features,
                "count": len(label_features),
            }
        
        # Export roads
        if layer in ["roads", "all"]:
            roads_qs = Road.objects.filter(tp_scheme=tp_scheme)
            if city:
                roads_qs = roads_qs.filter(city=city)
            
            road_features = []
            road_centerline_features = []
            
            for road in roads_qs:
                # Road polygon
                feature = {
                    "type": "Feature",
                    "id": f"road-{road.id}",
                    "geometry": json.loads(road.geom.geojson),
                    "properties": {
                        "id": road.id,
                        "name": road.name,
                        "width_m": road.width_m,
                        "city": road.city,
                        "tp_scheme": road.tp_scheme,
                    },
                }
                road_features.append(feature)
                
                # Road centerline
                if road.centerline:
                    centerline_feature = {
                        "type": "Feature",
                        "id": f"road-centerline-{road.id}",
                        "geometry": json.loads(road.centerline.geojson),
                        "properties": {
                            "id": road.id,
                            "name": road.name,
                            "width_m": road.width_m,
                            "city": road.city,
                            "tp_scheme": road.tp_scheme,
                        },
                    }
                    road_centerline_features.append(centerline_feature)
            
            result["roads"] = {
                "type": "FeatureCollection",
                "features": road_features,
                "count": len(road_features),
            }
            
            result["road_centerlines"] = {
                "type": "FeatureCollection",
                "features": road_centerline_features,
                "count": len(road_centerline_features),
            }
        
        # Export block labels
        if layer in ["block_labels", "all"]:
            # Get block labels via related plots
            plots_qs = Plot.objects.filter(tp_scheme=tp_scheme)
            if city:
                plots_qs = plots_qs.filter(city=city)
            
            block_labels_qs = BlockLabel.objects.filter(
                plot__in=plots_qs
            ).select_related("plot")
            
            block_label_features = []
            for bl in block_labels_qs:
                feature = {
                    "type": "Feature",
                    "id": f"block-label-{bl.id}",
                    "geometry": json.loads(bl.geom.geojson),
                    "properties": {
                        "text": bl.text,
                        "plot_id": f"{bl.plot.tp_scheme}-{bl.plot.fp_number}" if bl.plot else None,
                    },
                }
                block_label_features.append(feature)
            
            result["block_labels"] = {
                "type": "FeatureCollection",
                "features": block_label_features,
                "count": len(block_label_features),
            }
        
        # Add metadata
        result["metadata"] = {
            "tp_scheme": tp_scheme,
            "city": city,
            "layer": layer,
            "crs": "EPSG:0",  # Local coordinate system
            "note": "SRID=0 (unitless/local DXF coordinates). Convert to UTM Zone 43N (EPSG:32643) for Gujarat.",
        }
        
        return Response(result)


class ValidationStatsAPIView(APIView):
    """
    Get validation statistics for a TP scheme.
    
    Query params:
      - tp_scheme: TP scheme (required)
      - city: City filter (optional)
    
    Returns statistics about label points, roads, and data quality.
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
        
        plots_qs = Plot.objects.filter(tp_scheme=tp_scheme)
        if city:
            plots_qs = plots_qs.filter(city=city)
        
        total_plots = plots_qs.count()
        plots_with_label_points = plots_qs.filter(label_point__isnull=False).count()
        plots_with_road_width = plots_qs.filter(road_width_m__isnull=False).count()
        plots_with_designation = plots_qs.exclude(designation="").count()
        validated_plots = plots_qs.filter(validation_status=True).count()
        
        roads_qs = Road.objects.filter(tp_scheme=tp_scheme)
        if city:
            roads_qs = roads_qs.filter(city=city)
        
        total_roads = roads_qs.count()
        roads_with_centerline = roads_qs.filter(centerline__isnull=False).count()
        roads_with_width = roads_qs.filter(width_m__isnull=False).count()
        
        block_labels_qs = BlockLabel.objects.filter(
            plot__tp_scheme=tp_scheme
        )
        if city:
            block_labels_qs = block_labels_qs.filter(plot__city=city)
        
        total_block_labels = block_labels_qs.count()
        block_labels_mapped = block_labels_qs.filter(plot__isnull=False).count()
        
        stats = {
            "tp_scheme": tp_scheme,
            "city": city,
            "plots": {
                "total": total_plots,
                "with_label_points": plots_with_label_points,
                "label_point_coverage": f"{plots_with_label_points / max(1, total_plots) * 100:.1f}%",
                "with_road_width": plots_with_road_width,
                "with_designation": plots_with_designation,
                "validated": validated_plots,
                "validation_rate": f"{validated_plots / max(1, total_plots) * 100:.1f}%",
            },
            "roads": {
                "total": total_roads,
                "with_centerline": roads_with_centerline,
                "centerline_coverage": f"{roads_with_centerline / max(1, total_roads) * 100:.1f}%" if total_roads > 0 else "N/A",
                "with_width": roads_with_width,
            },
            "block_labels": {
                "total": total_block_labels,
                "mapped_to_plots": block_labels_mapped,
                "mapping_rate": f"{block_labels_mapped / max(1, total_block_labels) * 100:.1f}%" if total_block_labels > 0 else "N/A",
            },
            "recommendations": [],
        }
        
        # Add recommendations
        if plots_with_label_points < total_plots:
            stats["recommendations"].append(
                f"Run 'python manage.py compute_label_points --tp-scheme {tp_scheme}' to compute missing label points"
            )
        
        if total_roads == 0:
            city_param = city or "<city>"
            stats["recommendations"].append(
                f"Run 'python manage.py extract_roads --tp-scheme {tp_scheme} --city {city_param}' to extract roads"
            )
        
        if roads_with_centerline < total_roads:
            stats["recommendations"].append(
                f"{total_roads - roads_with_centerline} roads are missing centerlines"
            )
        
        return Response(stats)
