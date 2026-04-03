from __future__ import annotations

from rest_framework import serializers


class AIPlannerScenarioRequestSerializer(serializers.Serializer):
    brief = serializers.CharField()
    site_id = serializers.CharField()
    # Optional PlannerInputs payload from frontend
    inputs = serializers.JSONField(required=False)


class AIPlannerScenarioResponseSerializer(serializers.Serializer):
    class ScenarioLayoutSerializer(serializers.Serializer):
        label = serializers.CharField()
        tower_count = serializers.IntegerField()
        fsi_target = serializers.FloatField()
        plan = serializers.DictField()
        design_insights = serializers.ListField(
            child=serializers.CharField(),
            allow_empty=False,
        )

    program_spec = serializers.DictField()
    scenarios = ScenarioLayoutSerializer(many=True)


__all__ = [
    "AIPlannerScenarioRequestSerializer",
    "AIPlannerScenarioResponseSerializer",
]


