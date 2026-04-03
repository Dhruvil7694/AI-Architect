"""
Road serializer for GIS-grade cartographic rendering.
"""

from __future__ import annotations

from rest_framework import serializers

from tp_ingestion.models import Road


class RoadSerializer(serializers.ModelSerializer):
    """
    Road DTO for map rendering.
    
    Returns centerline geometry and width for line-based rendering.
    """

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(allow_blank=True)
    widthM = serializers.FloatField(source="width_m", allow_null=True)
    centerline = serializers.SerializerMethodField()
    geometry = serializers.SerializerMethodField()

    class Meta:
        model = Road
        fields = [
            "id",
            "name",
            "widthM",
            "centerline",
            "geometry",
        ]

    def get_centerline(self, obj: Road):
        """
        Return GeoJSON LineString for the road centerline.
        """
        if not obj.centerline:
            return None
        
        import json
        return json.loads(obj.centerline.geojson)
    
    def get_geometry(self, obj: Road):
        """
        Return GeoJSON Polygon for the original road geometry.
        """
        import json
        return json.loads(obj.geom.geojson)
