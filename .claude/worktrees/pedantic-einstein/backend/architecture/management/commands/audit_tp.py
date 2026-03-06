"""
architecture/management/commands/audit_tp.py
---------------------------------------------
Read-only data-integrity audit for a TP scheme stored in PostGIS.

Performs six checks and prints a structured validation report.
No data is written or modified.

Usage
-----
    python manage.py audit_tp --tp 14
    python manage.py audit_tp --tp 14 --excel-path "path/to/scheme.xls"
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot

_LINE = "=" * 60
_SEP  = "-" * 10


class Command(BaseCommand):
    help = "Read-only data-integrity audit for a TP scheme."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tp",
            type=int,
            required=True,
            help="TP number (e.g. 14 for TP14)",
        )
        parser.add_argument(
            "--excel-path",
            type=str,
            default=None,
            help="Path to the Excel scheme file (optional).",
        )

    def handle(self, *args, **options):
        tp_num    = options["tp"]
        excel_path = options["excel_path"]
        tp_scheme = f"TP{tp_num}"

        # ── Collect summary lines for the final status block ──────────────────
        summary: list[str] = []

        self._print_header(tp_scheme, excel_path)

        # ── Section 1 — Database Presence ─────────────────────────────────────
        self._section(1, "DATABASE PRESENCE")
        plots = self._section1(tp_scheme, summary)
        if plots is None:
            sys.exit(1)

        # ── Section 2 — Geometry Type Audit ───────────────────────────────────
        self._section(2, "GEOMETRY TYPE AUDIT")
        try:
            self._section2(plots, summary)
        except Exception as exc:
            self._section_error(2, exc, summary)

        # ── Section 3 — SRID Audit ─────────────────────────────────────────────
        self._section(3, "SRID AUDIT")
        try:
            self._section3(plots, summary)
        except Exception as exc:
            self._section_error(3, exc, summary)

        # ── Section 4 — Area Statistics ────────────────────────────────────────
        self._section(4, "AREA STATISTICS")
        try:
            self._section4(plots, summary)
        except Exception as exc:
            self._section_error(4, exc, summary)

        # ── Section 5 — Excel vs DB Comparison ────────────────────────────────
        self._section(5, "EXCEL vs DB COMPARISON")
        if excel_path:
            try:
                self._section5(plots, excel_path, summary)
            except Exception as exc:
                self._section_error(5, exc, summary)
        else:
            self.stdout.write("[SKIP] --excel-path not provided.")
            summary.append("[SKIP] Excel comparison not run")

        # ── Section 6 — Bounding Box Sanity ────────────────────────────────────
        self._section(6, "BOUNDING BOX SANITY")
        try:
            self._section6(plots, summary)
        except Exception as exc:
            self._section_error(6, exc, summary)

        # ── Final summary ──────────────────────────────────────────────────────
        self._print_summary(summary)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _print_header(self, tp_scheme: str, excel_path: str | None) -> None:
        xl = excel_path if excel_path else "(not provided)"
        self.stdout.write(_LINE)
        self.stdout.write("Architecture AI -- TP Audit Tool")
        self.stdout.write(f"TP Scheme  : {tp_scheme}")
        self.stdout.write(f"Excel file : {xl}")
        self.stdout.write(_LINE)
        self.stdout.write("")

    def _section(self, n: int, title: str) -> None:
        self.stdout.write(f"\n{_SEP} [{n}] {title} {_SEP}")

    def _section_error(self, n: int, exc: Exception, summary: list[str]) -> None:
        msg = f"[ERROR] Section {n} failed: {exc}"
        self.stdout.write(msg)
        self.stdout.write("        Skipping to next section.")
        summary.append(f"[ERROR] Section {n} failed: {exc}")

    def _print_summary(self, summary: list[str]) -> None:
        self.stdout.write("\n" + "=" * 30)
        self.stdout.write("DATASET STATUS")
        self.stdout.write("=" * 30)
        for line in summary:
            self.stdout.write(f"  {line}")
        self.stdout.write("=" * 30)

    # ── Section implementations ───────────────────────────────────────────────

    def _section1(
        self, tp_scheme: str, summary: list[str]
    ) -> list[Plot] | None:
        """DB presence check. Returns queryset list or None (hard stop)."""
        plots = list(Plot.objects.filter(tp_scheme=tp_scheme).order_by("fp_number"))
        count = len(plots)
        if count == 0:
            self.stdout.write(
                f"ERROR: No plots for {tp_scheme} in DB. Run ingest_tp first."
            )
            return None
        self.stdout.write(f"{tp_scheme} -- {count} plots found in DB.")
        summary.append(f"[OK]   DB count: {count} plots")
        return plots

    def _section2(self, plots: list[Plot], summary: list[str]) -> None:
        """Geometry type distribution."""
        type_counter: Counter = Counter()
        multi_fps: list[str] = []

        for p in plots:
            gtype = p.geom.geom_type
            type_counter[gtype] += 1
            if gtype == "MultiPolygon":
                multi_fps.append(p.fp_number)

        polygon_count = type_counter.get("Polygon", 0)
        multi_count   = type_counter.get("MultiPolygon", 0)
        other_count   = sum(
            v for k, v in type_counter.items()
            if k not in ("Polygon", "MultiPolygon")
        )

        self.stdout.write("Geometry Types:")
        self.stdout.write(f"  Polygon      : {polygon_count:>4}")
        self.stdout.write(f"  MultiPolygon : {multi_count:>4}")
        self.stdout.write(f"  Other        : {other_count:>4}")

        if multi_count > 0:
            fp_list = ", ".join(multi_fps[:10])
            if len(multi_fps) > 10:
                fp_list += f" ... (+{len(multi_fps) - 10} more)"
            self.stdout.write(
                f"  [WARN] {multi_count} MultiPolygon geometries detected. FPs: {fp_list}"
            )
            self.stdout.write(
                "         These may cause issues in the placement engine."
            )
            summary.append(f"[WARN] {multi_count} MultiPolygon geometries (FPs: {fp_list})")
        else:
            summary.append("[OK]   All geometries are Polygon type")

    def _section3(self, plots: list[Plot], summary: list[str]) -> None:
        """SRID distribution."""
        srid_counter: Counter = Counter()
        for p in plots:
            srid_counter[p.geom.srid] += 1

        self.stdout.write("SRID Distribution:")
        for srid, cnt in sorted(srid_counter.items(), key=lambda x: (x[0] is None, x[0])):
            label = str(srid) if srid is not None else "None"
            self.stdout.write(f"  {label:>6} : {cnt}")

        none_count = srid_counter.get(None, 0)
        if none_count > 0:
            self.stdout.write(f"  [WARN] {none_count} plots have no SRID assigned.")
            summary.append(f"[WARN] {none_count} plots have SRID=None")
        elif list(srid_counter.keys()) == [0]:
            self.stdout.write(
                "[INFO] All records use SRID=0 (local DXF frame -- expected for TP14)."
            )
            summary.append("[INFO] SRID=0 on all records (expected)")
        else:
            summary.append(f"[OK]   SRID distribution: {dict(srid_counter)}")

    def _section4(self, plots: list[Plot], summary: list[str]) -> None:
        """Area statistics and outlier detection."""
        areas = [(p.fp_number, p.area_geometry) for p in plots]
        values = [a for _, a in areas]

        count   = len(values)
        min_val = min(values)
        max_val = max(values)
        mean    = statistics.mean(values)
        std     = statistics.stdev(values) if count > 1 else 0.0

        min_fp = next(fp for fp, a in areas if a == min_val)
        max_fp = next(fp for fp, a in areas if a == max_val)

        self.stdout.write("Area Stats (DB Geometry):")
        self.stdout.write(f"  Count : {count:>6}")
        self.stdout.write(f"  Min   : {min_val:>10,.1f}   (FP {min_fp})")
        self.stdout.write(f"  Max   : {max_val:>10,.1f}   (FP {max_fp})")
        self.stdout.write(f"  Mean  : {mean:>10,.1f}")
        self.stdout.write(f"  Std   : {std:>10,.1f}")

        LOW_THRESHOLD  = 50.0
        HIGH_THRESHOLD = 50_000.0

        low_outliers  = [(fp, a) for fp, a in areas if a < LOW_THRESHOLD]
        high_outliers = [(fp, a) for fp, a in areas if a > HIGH_THRESHOLD]

        self.stdout.write("\nArea Outliers:")
        if low_outliers:
            for fp, a in low_outliers:
                self.stdout.write(f"  Below {LOW_THRESHOLD:.0f}    : FP {fp} ({a:.1f})")
            self.stdout.write(
                f"  [WARN] {len(low_outliers)} plot(s) below minimum buildable threshold."
            )
            summary.append(f"[WARN] {len(low_outliers)} area outliers below {LOW_THRESHOLD}")
        else:
            self.stdout.write(f"  Below {LOW_THRESHOLD:.0f}        : none")

        if high_outliers:
            for fp, a in high_outliers:
                self.stdout.write(f"  Above {HIGH_THRESHOLD:,.0f} : FP {fp} ({a:,.1f})")
            self.stdout.write(
                f"  [WARN] {len(high_outliers)} plot(s) above upper threshold."
            )
            summary.append(f"[WARN] {len(high_outliers)} area outliers above {HIGH_THRESHOLD:,.0f}")
        else:
            self.stdout.write(f"  Above {HIGH_THRESHOLD:,.0f} : none")

        if not low_outliers and not high_outliers:
            summary.append("[OK]   No area outliers")

    def _section5(
        self, plots: list[Plot], excel_path: str, summary: list[str]
    ) -> None:
        """Excel vs DB area comparison."""
        from tp_ingestion.services.excel_reader import read_excel

        # ── Load Excel via shared reader (handles Gujarati + standard formats) ─
        try:
            excel_dict: dict[str, float] = read_excel(excel_path)
        except Exception as exc:
            self.stdout.write(f"[ERROR] Cannot read Excel file: {exc}")
            summary.append("[ERROR] Excel file could not be read")
            return

        if not excel_dict:
            self.stdout.write("[ERROR] Excel loaded but returned 0 parseable rows.")
            summary.append("[ERROR] Excel parsed 0 rows")
            return

        self.stdout.write(f"Excel loaded via tp_ingestion reader -- {len(excel_dict)} FP records.")

        # ── Build DB dict ─────────────────────────────────────────────────────
        db_dict = {p.fp_number: p.area_geometry for p in plots}

        excel_fps = set(excel_dict.keys())
        db_fps    = set(db_dict.keys())
        matched   = excel_fps & db_fps
        xl_only   = sorted(excel_fps - db_fps)
        db_only   = sorted(db_fps - excel_fps)

        self.stdout.write(f"\nExcel vs DB Area Comparison:")
        self.stdout.write(f"  Excel rows loaded    : {len(excel_dict):>5}")
        self.stdout.write(f"  DB rows              : {len(db_dict):>5}")
        self.stdout.write(f"  Matched              : {len(matched):>5}")
        self.stdout.write(
            f"  Excel-only (no DB)   : {len(xl_only):>5}"
            + (f"  (FPs: {', '.join(xl_only[:8])}{'...' if len(xl_only) > 8 else ''})" if xl_only else "")
        )
        self.stdout.write(
            f"  DB-only (no Excel)   : {len(db_only):>5}"
            + (f"  (FPs: {', '.join(db_only[:8])}{'...' if len(db_only) > 8 else ''})" if db_only else "")
        )

        if not matched:
            self.stdout.write("[WARN] No matching FP numbers between Excel and DB.")
            summary.append("[WARN] Excel loaded but no FP numbers matched DB")
            return

        # ── Compute percent differences ───────────────────────────────────────
        diffs = []
        for fp in matched:
            db_a  = db_dict[fp]
            xl_a  = excel_dict[fp]
            if xl_a != 0:
                pct = (db_a - xl_a) / xl_a * 100.0
            else:
                pct = 0.0
            diffs.append((fp, db_a, xl_a, pct))

        abs_diffs = [abs(d[3]) for d in diffs]
        mean_diff = statistics.mean(abs_diffs)
        max_row   = max(diffs, key=lambda x: abs(x[3]))
        min_diff  = min(abs_diffs)

        self.stdout.write(f"\nArea Difference Stats (matched rows):")
        self.stdout.write(f"  Mean  |%diff| : {mean_diff:>6.1f}%")
        self.stdout.write(f"  Max   |%diff| : {abs(max_row[3]):>6.1f}%  (FP {max_row[0]})")
        self.stdout.write(f"  Min   |%diff| : {min_diff:>6.1f}%")

        top5 = sorted(diffs, key=lambda x: abs(x[3]), reverse=True)[:5]
        self.stdout.write("\nTop 5 worst matches:")
        for fp, db_a, xl_a, pct in top5:
            self.stdout.write(
                f"  FP {fp:>5} : {pct:>+7.1f}%  "
                f"(DB: {db_a:>10,.1f},  Excel: {xl_a:>10,.1f})"
            )

        bad = [(fp, pct) for fp, _, _, pct in diffs if abs(pct) > 10.0]
        if bad:
            self.stdout.write(
                f"\n  [WARN] {len(bad)} plot(s) exceed 10% area difference."
            )
            summary.append(
                f"[WARN] {len(bad)} plots exceed 10% area difference (see Section 5)"
            )
        else:
            summary.append(
                f"[OK]   Excel loaded -- {len(matched)} rows matched, all within 10%"
            )

    def _section6(self, plots: list[Plot], summary: list[str]) -> None:
        """Bounding box dimensions for the first 5 plots."""
        sample = plots[:5]

        self.stdout.write(
            f"Sample Bounding Box Dimensions (first {len(sample)} plots, DXF units):"
        )
        widths = []
        for p in sample:
            xmin, ymin, xmax, ymax = p.geom.extent
            w = xmax - xmin
            h = ymax - ymin
            widths.append(w)
            self.stdout.write(
                f"  FP {p.fp_number:>5} : width= {w:>7.1f}  height= {h:>7.1f}"
            )

        if widths:
            avg_w = statistics.mean(widths)
            if 20 <= avg_w <= 500:
                self.stdout.write(
                    "[INFO] Values consistent with DXF feet scale (expected)."
                )
                summary.append("[OK]   Bounding boxes consistent with DXF feet scale")
            elif 5 <= avg_w <= 100:
                self.stdout.write(
                    "[WARN] Values suggest metres scale -- verify SRID and unit frame."
                )
                summary.append("[WARN] Bounding box values suggest metres, not feet")
            else:
                self.stdout.write(
                    f"[INFO] Average width = {avg_w:.1f}. Verify unit frame manually."
                )
                summary.append(
                    f"[INFO] Bounding box average width = {avg_w:.1f} -- verify scale"
                )
