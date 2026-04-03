from __future__ import annotations

import json
from rest_framework import serializers

from tp_ingestion.models import BlockLabel


class BlockLabelSerializer(serializers.ModelSerializer):
    geometry = serializers.SerializerMethodField()
    plotId = serializers.SerializerMethodField()

    class Meta:
        model = BlockLabel
        fields = [
            "id",
            "text",
            "geometry",
            "plotId",
        ]

    def get_geometry(self, obj: BlockLabel):
        # GeoDjango returns geojson as a JSON string; normalize to a dict.
        return json.loads(obj.geom.geojson)

    def get_plotId(self, obj: BlockLabel) -> str | None:
        if not obj.plot_id:
            return None
        return f"{obj.plot.tp_scheme}-{obj.plot.fp_number}"

