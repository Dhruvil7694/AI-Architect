from __future__ import annotations

from rest_framework import serializers

from tp_ingestion.models import Plot


class PlotSerializer(serializers.ModelSerializer):
    """
    Minimal plot DTO used by both list and detail endpoints.
    """

    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    areaSqm = serializers.SerializerMethodField()
    roadWidthM = serializers.FloatField(source="road_width_m", allow_null=True)
    geometry = serializers.SerializerMethodField()

    class Meta:
        model = Plot
        fields = [
            "id",
            "name",
            "areaSqm",
            "roadWidthM",
            "geometry",
        ]

    def get_id(self, obj: Plot) -> str:
        return f"{obj.tp_scheme}-{obj.fp_number}"

    def get_name(self, obj: Plot) -> str:
        return f"{obj.tp_scheme} {obj.fp_number}"

    def get_areaSqm(self, obj: Plot) -> float:
        return float(obj.plot_area_sqm)

    def get_geometry(self, obj: Plot):
        """
        Return GeoJSON for the plot polygon.

        GeoDjango's .geojson returns a JSON string; convert to a dict.
        """
        import json

        return json.loads(obj.geom.geojson)


