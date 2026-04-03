"""
Management command: report_ingestion_gaps
-----------------------------------------
Pre-ingest QA: compare DXF + Excel without writing to the database.

Reports:
  - Excel FPs with no matched polygon (likely "holes" in QGIS after ingest)
  - Matched FPs that fail area validation at the given tolerance
  - Matched FPs absent from Excel (label in CAD, no scheme row)
  - Unmatched labels (including numeric FPs that never linked to geometry)

Optional CSV export for tracking in spreadsheets.

Usage:
    python manage.py report_ingestion_gaps <dxf_path> <excel_path> \\
        --polygon-layers F.P. "new f.p." --label-layers "FINAL F.P." \\
        --snap-tolerance 35

    python manage.py report_ingestion_gaps plan.dxf scheme.xls --csv gaps.csv
"""

from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.services.area_validator import validate_area
from tp_ingestion.services.dxf_reader import read_dxf
from tp_ingestion.services.excel_reader import read_excel_all_areas
from tp_ingestion.services.geometry_matcher import match_fp_to_polygons


class Command(BaseCommand):
    help = "Pre-ingest gap report: Excel vs DXF matching (no DB writes)."

    def add_arguments(self, parser):
        parser.add_argument("dxf_path", type=str, help="Path to the TP scheme .dxf file.")
        parser.add_argument("excel_path", type=str, help="Path to the scheme .xls / .xlsx / .csv.")
        parser.add_argument(
            "--area-tolerance",
            type=float,
            default=0.10,
            dest="area_tolerance",
            help="Same as ingest_tp (default: 0.10 = 10%%).",
        )
        parser.add_argument(
            "--snap-tolerance",
            type=float,
            default=1.0,
            dest="snap_tolerance",
            help="Label–polygon snap distance in DXF units (default: 1.0).",
        )
        parser.add_argument(
            "--polygon-layers",
            nargs="+",
            dest="polygon_layers",
            default=None,
            metavar="LAYER",
            help="DXF layer(s) for plot polygons. Default: all layers.",
        )
        parser.add_argument(
            "--label-layers",
            nargs="+",
            dest="label_layers",
            default=None,
            metavar="LAYER",
            help="DXF layer(s) for FP labels. Default: all layers.",
        )
        parser.add_argument(
            "--snap-decimals",
            type=int,
            default=2,
            dest="snap_decimals",
            help="Coordinate snap decimals (default: 2).",
        )
        parser.add_argument(
            "--csv",
            type=str,
            default=None,
            dest="csv_path",
            help="Write one row per gap / outcome to this CSV path.",
        )

    def handle(self, *args, **options):
        dxf_path = options["dxf_path"]
        excel_path = options["excel_path"]
        area_tolerance = options["area_tolerance"]
        snap_tolerance = options["snap_tolerance"]
        polygon_layers = options["polygon_layers"]
        label_layers = options["label_layers"]
        snap_decimals = options["snap_decimals"]
        csv_path = options["csv_path"]

        if not Path(dxf_path).exists():
            raise CommandError(f"DXF not found: {dxf_path}")
        if not Path(excel_path).exists():
            raise CommandError(f"Excel/CSV not found: {excel_path}")

        dxf_result = read_dxf(
            dxf_path,
            polygon_layers=polygon_layers,
            label_layers=label_layers,
            snap_decimals=snap_decimals,
        )
        fp_map = read_excel_all_areas(excel_path)
        excel_fps = set(fp_map.keys())

        matched, unmatched = match_fp_to_polygons(
            dxf_result.polygons,
            dxf_result.labels,
            snap_tolerance=snap_tolerance,
        )

        seen: set[str] = set()
        deduped = []
        for m in matched:
            if m.fp_number in seen:
                continue
            seen.add(m.fp_number)
            deduped.append(m)

        matched_fp = {m.fp_number for m in deduped}
        in_excel_no_match = sorted(
            excel_fps - matched_fp,
            key=lambda x: (int(x) if x.isdigit() else 9999, x),
        )
        matched_not_in_excel = sorted(
            matched_fp - excel_fps,
            key=lambda x: (len(x), x),
        )

        would_save: list[str] = []
        area_fail: list[tuple[str, float, float, float]] = []

        for m in deduped:
            fp = m.fp_number
            if fp not in fp_map:
                continue
            areas = fp_map[fp]
            area_excel = min(areas, key=lambda a: abs(a - m.polygon.area))
            vr = validate_area(fp, m.polygon, area_excel, tolerance=area_tolerance)
            if vr.is_valid:
                would_save.append(fp)
            else:
                err_pct = vr.relative_error * 100
                area_fail.append((fp, area_excel, vr.area_geometry, err_pct))

        # ── stdout ─────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Ingestion gap report (pre-DB) ==="))
        self.stdout.write(f"  DXF polygons        : {len(dxf_result.polygons)}")
        self.stdout.write(f"  Labels              : {len(dxf_result.labels)}")
        self.stdout.write(f"  Matches (raw)       : {len(matched)}")
        self.stdout.write(f"  Unique matched FP   : {len(matched_fp)}")
        self.stdout.write(f"  Excel FP rows       : {len(excel_fps)}")
        self.stdout.write(f"  Would save (area OK): {len(would_save)}")
        self.stdout.write(f"  Area FAIL            : {len(area_fail)}")
        self.stdout.write(f"  Matched, not in Excel: {len(matched_not_in_excel)}")
        self.stdout.write("")

        if in_excel_no_match:
            self.stdout.write(
                self.style.WARNING(
                    f"In Excel but no polygon match ({len(in_excel_no_match)}):"
                )
            )
            self.stdout.write("  " + ", ".join(in_excel_no_match))
            self.stdout.write("")

        if area_fail:
            self.stdout.write(self.style.WARNING(f"Area validation fail @ {area_tolerance:.0%}:"))
            for fp, ae, ag, pct in sorted(
                area_fail, key=lambda t: int(t[0]) if t[0].isdigit() else 0
            ):
                self.stdout.write(
                    f"  FP {fp}  Excel {ae:.0f}  Geom {ag:.2f}  ({pct:.1f}%)"
                )
            self.stdout.write("")

        if matched_not_in_excel:
            self.stdout.write(
                self.style.WARNING(
                    "Matched in DXF but no Excel row (skipped on ingest): "
                    + ", ".join(matched_not_in_excel)
                )
            )
            self.stdout.write("")

        if unmatched:
            show = unmatched if len(unmatched) <= 80 else unmatched[:80] + ["..."]
            self.stdout.write(
                f"Unmatched labels ({len(unmatched)}): {show}"
            )
            self.stdout.write("")

        # ── optional CSV ────────────────────────────────────────────────
        if csv_path:
            out = Path(csv_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "category",
                        "fp_or_label",
                        "excel_area",
                        "geom_area",
                        "error_pct",
                        "note",
                    ]
                )
                for fp in in_excel_no_match:
                    w.writerow(
                        [
                            "in_excel_no_polygon",
                            fp,
                            fp_map[fp][0],
                            "",
                            "",
                            "No label–polygon match for this FP",
                        ]
                    )
                for fp, ae, ag, pct in area_fail:
                    w.writerow(
                        [
                            "area_validation_fail",
                            fp,
                            ae,
                            f"{ag:.4f}",
                            f"{pct:.2f}",
                            f"tolerance {area_tolerance:.0%}",
                        ]
                    )
                for fp in matched_not_in_excel:
                    w.writerow(
                        [
                            "matched_no_excel_row",
                            fp,
                            "",
                            "",
                            "",
                            "Label matched polygon; add FP to Excel or remove label",
                        ]
                    )
                for lab in unmatched:
                    w.writerow(["unmatched_label", lab, "", "", "", ""])

            self.stdout.write(self.style.SUCCESS(f"Wrote {out.resolve()}"))

        self.stdout.write(self.style.SUCCESS("Done.\n"))
