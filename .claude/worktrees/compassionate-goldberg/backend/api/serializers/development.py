from __future__ import annotations

from rest_framework import serializers


class SiteMetricsSerializer(serializers.Serializer):
    plotId = serializers.CharField()
    plotAreaSqm = serializers.FloatField()
    baseFSI = serializers.FloatField()
    maxFSI = serializers.FloatField()
    maxBUA = serializers.FloatField()
    copAreaSqm = serializers.FloatField()
    copStrategy = serializers.CharField()


class OptimalDevelopmentRequestSerializer(serializers.Serializer):
    """
    Request contract for the optimal development floor-plan API.

    This serializer performs only basic type/shape validation. All domain /
    regulatory logic is delegated to the service layer.
    """

    tp = serializers.IntegerField(required=True)
    fp = serializers.IntegerField(required=True)

    storey_height_m = serializers.FloatField(
        required=False, default=3.0, min_value=1e-6
    )
    min_width_m = serializers.FloatField(
        required=False, default=5.0, min_value=1e-6
    )
    min_depth_m = serializers.FloatField(
        required=False, default=3.5, min_value=1e-6
    )

    include_building_layout = serializers.BooleanField(required=False, default=False)
    strict = serializers.BooleanField(required=False, default=True)
    geometry_format = serializers.ChoiceField(
        choices=("geojson", "wkt"),
        required=False,
        default="geojson",
    )

    def validate(self, attrs):
        """
        Additional cross-field validation if needed.

        Currently just enforces strictly positive dimensional parameters.
        """
        for field in ("storey_height_m", "min_width_m", "min_depth_m"):
            value = attrs.get(field)
            if value is not None and value <= 0:
                raise serializers.ValidationError(
                    {field: "Must be greater than 0."}
                )
        return attrs

