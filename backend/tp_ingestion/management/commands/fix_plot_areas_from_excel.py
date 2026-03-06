"""
Management command: fix_plot_areas_from_excel
---------------------------------------------
Re-apply Excel areas to existing plots using the \"closest area\" rule:
when an FP has multiple rows in the Excel, set area_excel to the value
closest to the plot's geometry area and recompute validation_status.

Use after upgrading to read_excel_all_areas ingestion to fix plots like FP 152
that had wrong area due to \"first row\" being an outlier.

Usage:
    python manage.py fix_plot_areas_from_excel <excel_path> --city <city> --tp-scheme TP14 [--tolerance 0.10]
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tp_ingestion.models import Plot
from tp_ingestion.services.area_validator import validate_area
from tp_ingestion.services.excel_reader import read_excel_all_areas


def _polygon_area_geos(geom):
    """Area of GEOS polygon (same units as DXF)."""
    return geom.area


class Command(BaseCommand):
    help = "Update area_excel and validation_status from Excel (closest-area rule)."

    def add_arguments(self, parser):
        parser.add_argument("excel_path", type=str)
        parser.add_argument("--city", type=str, required=True)
        parser.add_argument("--tp-scheme", type=str, dest="tp_scheme", required=True)
        parser.add_argument("--tolerance", type=float, default=0.10)

    def handle(self, *args, **options):
        excel_path = Path(options["excel_path"])
        if not excel_path.exists():
            raise CommandError("Excel not found: %s" % excel_path)

        fp_areas = read_excel_all_areas(excel_path)
        qs = Plot.objects.filter(
            city=options["city"],
            tp_scheme=options["tp_scheme"],
        )
        tolerance = options.get("tolerance", 0.10)
        updated = 0
        with transaction.atomic():
            for plot in qs:
                if plot.fp_number not in fp_areas:
                    continue
                areas = fp_areas[plot.fp_number]
                area_geom = _polygon_area_geos(plot.geom)
                area_excel = min(areas, key=lambda a: abs(a - area_geom))
                # Reuse validator for is_valid
                from shapely.geometry import Polygon
                coords = list(plot.geom.coords[0])
                shp = Polygon(coords)
                vr = validate_area(plot.fp_number, shp, area_excel, tolerance=tolerance)
                if plot.area_excel != vr.area_excel or plot.validation_status != vr.is_valid:
                    plot.area_excel = vr.area_excel
                    plot.area_geometry = vr.area_geometry
                    plot.validation_status = vr.is_valid
                    plot.save(update_fields=["area_excel", "area_geometry", "validation_status"])
                    updated += 1
        self.stdout.write(self.style.SUCCESS("Updated %d plot(s)." % updated))