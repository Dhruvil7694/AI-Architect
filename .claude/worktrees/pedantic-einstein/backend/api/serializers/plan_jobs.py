from __future__ import annotations

from rest_framework import serializers

from architecture.models import PlanJob


class PlanJobCreateSerializer(serializers.Serializer):
    plotId = serializers.CharField()
    inputs = serializers.JSONField()


class PlanJobStatusSerializer(serializers.Serializer):
    jobId = serializers.CharField()
    status = serializers.CharField()
    progress = serializers.IntegerField()
    errorMessage = serializers.CharField(allow_null=True, required=False)


class PlanJobResultSerializer(serializers.Serializer):
    planId = serializers.CharField()
    plotId = serializers.CharField()
    metrics = serializers.DictField()
    geometry = serializers.DictField()


