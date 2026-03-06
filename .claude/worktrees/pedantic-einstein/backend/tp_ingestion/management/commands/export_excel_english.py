"""
Management command: export_excel_english
----------------------------------------
Convert a Gujarati font-encoded TP scheme Excel to an English CSV (or Excel)
with decoded FP numbers and areas. Headers become "FP No", "Area (sq.ft)".

Does not translate Gujarati text in other columns — only decodes the numeric
columns we use (FP and Area) and writes a clean table. Use for verification
and as a source for road data or other tools.

Usage:
    python manage.py export_excel_english <excel_path> [--output out.csv] [--format csv|xlsx]
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

import pandas as pd

from tp_ingestion.services.excel_reader import _is_gujarati_encoded, read_excel_all_areas


class Command(BaseCommand):
    help = "Convert Gujarati TP scheme Excel to English CSV/Excel (decoded FP and Area)."

    def add_arguments(self, parser):
        parser.add_argument("excel_path", type=str, help="Path to the .xls / .xlsx file.")
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            default=None,
            dest="output",
            help="Output path (default: same dir as input, name_English.csv).",
        )
        parser.add_argument(
            "--format",
            choices=["csv", "xlsx"],
            default="csv",
            dest="format",
            help="Output format (default: csv).",
        )

    def handle(self, *args, **options):
        excel_path = Path(options["excel_path"])
        if not excel_path.exists():
            raise CommandError("Excel file not found: %s" % excel_path)

        # Detect encoding
        raw_header = pd.read_excel(excel_path, dtype=str, nrows=1)
        first_col = str(raw_header.columns[0])
        if not _is_gujarati_encoded(first_col):
            self.stdout.write(self.style.WARNING(
                "File appears to be standard English already. Exporting decoded FP/Area only."
            ))

        fp_areas = read_excel_all_areas(excel_path)
        # Build rows: one row per (fp, area) so duplicate FPs appear
        rows = []
        def _fp_sort_key(x):
            try:
                return (0, int(x))
            except ValueError:
                return (1, x)

        for fp in sorted(fp_areas.keys(), key=_fp_sort_key):
            for area in fp_areas[fp]:
                rows.append({"FP No": fp, "Area (sq.ft)": round(area, 2)})
        if not rows:
            raise CommandError("No FP/Area data decoded from the Excel file.")

        df = pd.DataFrame(rows)

        out = options.get("output")
        fmt = options.get("format", "csv")
        if not out:
            out = excel_path.parent / (excel_path.stem + "_English." + ("csv" if fmt == "csv" else "xlsx"))
        else:
            out = Path(out)

        out.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "csv":
            df.to_csv(out, index=False, encoding="utf-8")
        else:
            df.to_excel(out, index=False, sheet_name="Scheme")

        self.stdout.write(self.style.SUCCESS("Exported %d rows to: %s" % (len(df), out)))
