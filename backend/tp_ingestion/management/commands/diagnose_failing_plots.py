"""
Management command: diagnose_failing_plots
-------------------------------------------
Explain why certain plots failed area validation (Excel vs geometry).

Reports:
  - FP 152-type: Same FP has multiple Excel rows; first row had wrong area.
    (Ingestion now picks area closest to geometry, so re-ingest to fix.)
  - Others: Geometry is 2–3x Excel → likely DXF label matched to wrong polygon.
    Verify in DXF/QGIS which polygon the FP label is inside.

Usage:
    python manage.py diagnose_failing_plots [--city CITY] [--tp-scheme TP14]
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot
from tp_ingestion.services.excel_reader import read_excel_all_areas


class Command(BaseCommand):
    help = "Diagnose why plots failed area validation."

    def add_arguments(self, parser):
        parser.add_argument("--city", type=str, default=None)
        parser.add_argument("--tp-scheme", type=str, dest="tp_scheme", default=None)
        parser.add_argument(
            "--excel",
            type=str,
            default=None,
            help="Path to TP scheme Excel (to show duplicate-row info).",
        )

    def handle(self, *args, **options):
        qs = Plot.objects.filter(validation_status=False).order_by("tp_scheme", "fp_number")
        if options.get("city"):
            qs = qs.filter(city=options["city"])
        if options.get("tp_scheme"):
            qs = qs.filter(tp_scheme=options["tp_scheme"])

        failing = list(qs)
        if not failing:
            self.stdout.write(self.style.SUCCESS("No failing plots in DB for the given filters."))
            return

        # Load Excel areas per FP if path given (to show duplicate rows)
        fp_areas_map = {}
        excel_path = options.get("excel")
        if excel_path and Path(excel_path).exists():
            try:
                fp_areas_map = read_excel_all_areas(excel_path)
            except Exception as e:
                self.stdout.write(self.style.WARNING("Could not read Excel: %s" % e))

        self.stdout.write("")
        self.stdout.write("=" * 72)
        self.stdout.write("  Failing plots (area_excel vs area_geometry)")
        self.stdout.write("=" * 72)

        for p in failing:
            diff_pct = (p.area_geometry - p.area_excel) / p.area_excel * 100 if p.area_excel else 0
            areas = fp_areas_map.get(p.fp_number, [])

            if len(areas) > 1:
                best = min(areas, key=lambda a: abs(a - p.area_geometry))
                diagnosis = (
                    "Duplicate Excel rows: first area used was %.0f; geometry %.0f sq.ft. "
                    "Another row has area %.0f (closest to geometry). Re-run ingest_tp to fix."
                ) % (p.area_excel, p.area_geometry, best)
            else:
                ratio = p.area_geometry / p.area_excel if p.area_excel else 0
                diagnosis = (
                    "Geometry ~%.1fx Excel. Likely DXF label matched to wrong polygon — "
                    "check in QGIS/DXF which polygon contains the FP %s label."
                ) % (ratio, p.fp_number)

            self.stdout.write("")
            self.stdout.write("  %s FP %s" % (p.tp_scheme, p.fp_number))
            self.stdout.write("    Excel: %s sq.ft  |  Geometry: %s sq.ft  |  Diff: %+.1f%%" % (
                p.area_excel, round(p.area_geometry, 2), diff_pct))
            self.stdout.write("    -> %s" % diagnosis)

        self.stdout.write("")
        self.stdout.write("=" * 72)
        if not excel_path and failing:
            self.stdout.write("Tip: pass --excel <path_to_scheme.xls> to see duplicate-row diagnosis.")
        self.stdout.write("To fix duplicate-row cases (e.g. FP 152): run fix_plot_areas_from_excel.")
        self.stdout.write("")
