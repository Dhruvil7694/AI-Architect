from __future__ import annotations

from rest_framework import serializers

from tp_ingestion.models import Plot
from tp_ingestion.geometry_utils import get_label_point


class PlotSerializer(serializers.ModelSerializer):
    """
    Minimal plot DTO used by both list and detail endpoints.
    """

    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    areaSqm = serializers.SerializerMethodField()
    roadWidthM = serializers.FloatField(source="road_width_m", allow_null=True)
    designation = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    geometry = serializers.SerializerMethodField()
    labelPoint = serializers.SerializerMethodField()

    class Meta:
        model = Plot
        fields = [
            "id",
            "name",
            "areaSqm",
            "roadWidthM",
            "designation",
            "geometry",
            "labelPoint",
        ]

    def get_id(self, obj: Plot) -> str:
        return f"{obj.tp_scheme}-{obj.fp_number}"

    def get_name(self, obj: Plot) -> str:
        """Display name matching Excel 'FP No' column: FP 1, FP 2, ..."""
        return f"FP {obj.fp_number}"

    def get_areaSqm(self, obj: Plot) -> float:
        return float(obj.plot_area_sqm)

    def get_geometry(self, obj: Plot):
        """
        Return GeoJSON for the plot polygon.

        GeoDjango's .geojson returns a JSON string; convert to a dict.
        """
        import json

        return json.loads(obj.geom.geojson)
    
    def get_labelPoint(self, obj: Plot):
        """
        Return optimal label placement point [x, y].
        
        Uses polylabel-like algorithm (representative_point) for better
        placement on irregular/L-shaped plots.
        """
        if obj.label_point:
            return [obj.label_point.x, obj.label_point.y]

        # If the DB record is missing label_point (older ingestions),
        # compute polylabel on the fly to avoid centroid-based placement.
        from shapely.geometry import Polygon as ShapelyPolygon

        coords = [(pt[0], pt[1]) for pt in obj.geom.coords[0]]
        shapely_poly = ShapelyPolygon(coords)
        label_pt = get_label_point(shapely_poly)
        return [label_pt.x, label_pt.y]


