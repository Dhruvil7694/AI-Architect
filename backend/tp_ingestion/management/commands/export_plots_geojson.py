"""
Export Plot polygons from PostGIS to a GeoJSON file for viewing in QGIS or geojson.io.
"""

from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot


class Command(BaseCommand):
    help = "Export tp_ingestion Plot geometries to a GeoJSON file (QGIS, geojson.io)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", "-o",
            type=str,
            required=True,
            help="Output file path (e.g. outputs/plots.geojson)",
        )
        parser.add_argument(
            "--tp",
            type=int,
            default=None,
            help="Filter by TP scheme number (e.g. 14 for TP14)",
        )
        parser.add_argument(
            "--fp",
            type=int,
            default=None,
            help="Filter by FP number (e.g. 126). Use with --tp.",
        )

    def handle(self, *args, **options):
        output_path = options["output"]
        tp = options["tp"]
        fp = options["fp"]

        qs = Plot.objects.all().order_by("tp_scheme", "fp_number")
        if tp is not None:
            qs = qs.filter(tp_scheme=f"TP{tp}")
        if fp is not None:
            qs = qs.filter(fp_number=str(fp))

        features = []
        for plot in qs:
            if not plot.geom:
                continue
            geom_json = json.loads(plot.geom.geojson)
            features.append({
                "type": "Feature",
                "geometry": geom_json,
                "properties": {
                    "id": plot.id,
                    "tp_scheme": plot.tp_scheme,
                    "fp_number": plot.fp_number,
                    "city": plot.city,
                    "area_sqft": plot.area_geometry,
                    "road_width_m": plot.road_width_m,
                    "road_edges": plot.road_edges or "",
                },
            })
        fc = {"type": "FeatureCollection", "features": features}

        parent = os.path.dirname(os.path.abspath(output_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, indent=2, ensure_ascii=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(features)} plot(s) to {output_path}"
            )
        )
