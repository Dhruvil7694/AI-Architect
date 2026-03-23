from rest_framework import serializers


class DevelopmentInputSerializer(serializers.Serializer):
    """New user-facing development input contract."""
    # Plot identification
    tp = serializers.IntegerField(help_text="Town Planning scheme number")
    fp = serializers.IntegerField(help_text="Final Plot number")

    # 1. Building type (1=Low-Rise, 2=Mid-Rise, 3=High-Rise)
    building_type = serializers.IntegerField(
        min_value=1, max_value=3, default=3,
        help_text="Building type: 1=Low-Rise(G+3), 2=Mid-Rise(G+5), 3=High-Rise(6+)",
    )

    # 2. Number of floors
    floors = serializers.IntegerField(
        required=False, default=None, allow_null=True,
        help_text="User-selected floor count. null = auto (GDCR max permissible)",
    )

    # 3. Core config (units per core per floor)
    units_per_core = serializers.ChoiceField(
        choices=[2, 4, 6], default=4,
        help_text="Units sharing one lift+staircase core: 2 (premium), 4 (mid), 6 (budget)",
    )

    # 4. Segment (drives RCA efficiency ratio)
    segment = serializers.ChoiceField(
        choices=["budget", "mid", "premium", "luxury"], default="mid",
    )

    # 5. Number of buildings (towers)
    n_buildings = serializers.IntegerField(
        required=False, default=None, allow_null=True,
        help_text="Number of towers. null = auto (optimizer decides).",
    )

    # Unit mix (optional)
    unit_mix = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
    )

    # Storey height
    storey_height_m = serializers.FloatField(default=3.0, min_value=2.5, max_value=4.5)

    # Output options
    include_building_layout = serializers.BooleanField(default=False)
    geometry_format = serializers.ChoiceField(
        choices=["geojson", "wkt"], default="geojson",
    )

    def validate_floors(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Floors must be at least 1.")
        return value

    def validate_n_buildings(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Number of buildings must be at least 1.")
        return value
