"""
Management command: verify_plot_data
------------------------------------
Verify plot foundation data: Excel area vs geometry area and current road fields.

Use this first to ensure the source data (Excel) matches what we stored from the DXF.
If area validation fails for many plots, fix ingestion or source data before running
envelope/floorplan engines.

Usage:
    python manage.py verify_plot_data [--city CITY] [--tp-scheme TP14] [--export report.csv]

Example:
    python manage.py verify_plot_data --tp-scheme TP14 --export tp14_verification.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot


class Command(BaseCommand):
    help = "Verify plot data: area_excel vs area_geometry, validation status, road fields."

    def add_arguments(self, parser):
        parser.add_argument(
            "--city",
            type=str,
            default=None,
            help="Filter by city (e.g. Ahmedabad). Omit to include all cities.",
        )
        parser.add_argument(
            "--tp-scheme",
            type=str,
            default=None,
            dest="tp_scheme",
            help="Filter by TP scheme (e.g. TP14). Omit to include all schemes.",
        )
        parser.add_argument(
            "--export",
            type=str,
            default=None,
            dest="export_path",
            help="Optional path to export a CSV of all plotted rows for review.",
        )

    def handle(self, *args, **options):
        qs = Plot.objects.all().order_by("tp_scheme", "fp_number")
        if options.get("city"):
            qs = qs.filter(city=options["city"])
        if options.get("tp_scheme"):
            qs = qs.filter(tp_scheme=options["tp_scheme"])

        plots = list(qs)
        if not plots:
            self.stdout.write(self.style.WARNING("No plots found for the given filters."))
            return

        # Build rows for display and optional CSV
        rows = []
        for p in plots:
            diff = p.area_geometry - p.area_excel if p.area_excel else 0
            diff_pct = (diff / p.area_excel * 100) if p.area_excel else 0
            rows.append({
                "city": p.city,
                "tp_scheme": p.tp_scheme,
                "fp_number": p.fp_number,
                "area_excel": round(p.area_excel, 2),
                "area_geometry": round(p.area_geometry, 2),
                "diff_pct": round(diff_pct, 2),
                "validation_status": "OK" if p.validation_status else "FAIL",
                "road_width_m": p.road_width_m if p.road_width_m is not None else "",
                "road_edges": (p.road_edges or "").strip(),
            })

        # Console summary
        ok = sum(1 for r in rows if r["validation_status"] == "OK")
        fail = len(rows) - ok
        with_road = sum(1 for r in rows if r["road_width_m"] != "" and (r["road_edges"] or r["road_width_m"] != ""))
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("  Plot data verification (Excel vs geometry)")
        self.stdout.write("=" * 70)
        self.stdout.write(f"  Total plots   : {len(rows)}")
        self.stdout.write(f"  Area OK       : {ok}")
        self.stdout.write(f"  Area FAIL     : {fail}")
        self.stdout.write(f"  With road set : {with_road} (road_width_m and/or road_edges)")
        self.stdout.write("=" * 70)

        # Sample table (first 20)
        self.stdout.write("")
        self.stdout.write(f"{'TP':<6} {'FP':<8} {'Area Excel':<12} {'Area Geom':<12} {'Diff %':<8} {'Status':<6} {'Road':<12}")
        self.stdout.write("-" * 70)
        for r in rows[:20]:
            road = f"{r['road_width_m']}m, E{r['road_edges']}" if r["road_width_m"] or r["road_edges"] else "—"
            self.stdout.write(
                f"{r['tp_scheme']:<6} {r['fp_number']:<8} {r['area_excel']:<12} {r['area_geometry']:<12} "
                f"{r['diff_pct']:<8.2f} {r['validation_status']:<6} {road:<12}"
            )
        if len(rows) > 20:
            self.stdout.write(f"  ... and {len(rows) - 20} more (use --export for full list).")

        # Export full CSV
        export_path = options.get("export_path")
        if export_path:
            path = Path(export_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            self.stdout.write(self.style.SUCCESS(f"\nExported full report to: {path}"))
        self.stdout.write("")
