"""
architecture/management/commands/validate_feasibility_metrics.py
-----------------------------------------------------------------
Part 7 validation: run feasibility pipeline for selected TP plots and
optionally compare engine output to expected values (manual GDCR checks).

Produces a validation matrix for:
  - FSI (achieved vs permissible)
  - Ground coverage %
  - COP % (provided / required)
  - Frontage length (m)
  - Height band classification

Usage:
  python manage.py validate_feasibility_metrics --tp 14 --height 16.5 --limit 10
  python manage.py validate_feasibility_metrics --tp 14 --height 16.5 --limit 10 --expected expected_tp14.csv
  python manage.py validate_feasibility_metrics --tp 14 --height 16.5 --limit 10 --output validation_output.csv
"""

from __future__ import annotations

import csv
import traceback
from dataclasses import dataclass
from io import StringIO

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot


def _parse_road_edges(raw: str) -> list[int]:
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [0]


def _bbox_ratio(plot: Plot) -> float:
    try:
        ext = plot.geom.extent
        w = ext[2] - ext[0]
        h = ext[3] - ext[1]
        if w <= 0 or h <= 0:
            return 0.0
        return min(w, h) / max(w, h)
    except Exception:
        return 0.0


def _select_plots(tp: int, limit: int) -> list:
    base = list(Plot.objects.filter(tp_scheme=f"TP{tp}").order_by("fp_number"))
    if not base:
        return []
    by_area_asc = sorted(base, key=lambda p: (p.area_geometry, p.fp_number))
    smallest = by_area_asc[:2]
    largest = by_area_asc[-2:] if len(by_area_asc) >= 2 else by_area_asc[-1:]
    by_ratio_desc = sorted(base, key=lambda p: (-_bbox_ratio(p), p.fp_number))
    near_square = by_ratio_desc[:2]
    by_ratio_asc = sorted(base, key=lambda p: (_bbox_ratio(p), p.fp_number))
    long_narrow = by_ratio_asc[:2]
    irregular = [p for p in base if p.geom.geom_type != "Polygon"][:2]
    seen = set()
    result = []
    for group in [smallest, largest, near_square, long_narrow, irregular]:
        for p in group:
            if p.fp_number not in seen:
                seen.add(p.fp_number)
                result.append(p)
    return sorted(result, key=lambda p: p.fp_number)[:limit]


@dataclass
class ValidationRow:
    fp_number: str
    plot_area_sqft: float
    achieved_fsi: float
    max_fsi: float
    achieved_gc_pct: float
    permissible_gc_pct: float
    cop_provided_sqft: float
    cop_required_sqft: float
    cop_pct: float
    frontage_m: float
    height_band: str
    error: str = ""
    aggregate: object = None  # FeasibilityAggregate when success


def _run_pipeline_for_plot(plot, height: float, road_width: float, road_edges: list, tp: int) -> ValidationRow:
    """Run envelope → placement → skeleton → feasibility for one plot. Return ValidationRow."""
    fp_number = plot.fp_number
    plot_area_sqft = plot.plot_area_sqft
    row = ValidationRow(
        fp_number=fp_number,
        plot_area_sqft=plot_area_sqft,
        achieved_fsi=0.0,
        max_fsi=0.0,
        achieved_gc_pct=0.0,
        permissible_gc_pct=0.0,
        cop_provided_sqft=0.0,
        cop_required_sqft=0.0,
        cop_pct=0.0,
        frontage_m=0.0,
        height_band="",
    )
    try:
        from envelope_engine.services.envelope_service import compute_envelope
        from placement_engine.services.placement_service import compute_placement
        from floor_skeleton.services import generate_floor_skeleton
        from placement_engine.geometry.core_fit import NO_CORE_FIT
        from floor_skeleton.models import NO_SKELETON_PATTERN
        from architecture.feasibility.service import build_feasibility_from_pipeline

        result = compute_envelope(
            plot_wkt=plot.geom.wkt,
            building_height=height,
            road_width=road_width,
            road_facing_edges=road_edges,
        )
        if result.status != "VALID":
            row.error = f"envelope {result.status}"
            return row

        pr = compute_placement(
            envelope_wkt=result.envelope_polygon.wkt,
            building_height_m=height,
            n_towers=1,
            min_width_m=5.0,
            min_depth_m=3.5,
        )
        if not pr.footprints or not pr.per_tower_core_validation:
            row.error = "placement failed"
            return row
        cv = pr.per_tower_core_validation[0]
        if cv.core_fit_status == NO_CORE_FIT:
            row.error = "NO_CORE_FIT"
            return row

        skeleton = generate_floor_skeleton(
            footprint=pr.footprints[0],
            core_validation=cv,
        )
        if skeleton.pattern_used == NO_SKELETON_PATTERN:
            row.error = "NO_SKELETON"
            return row

        agg = build_feasibility_from_pipeline(
            plot_geom_wkt=plot.geom.wkt,
            plot_area_sqft=plot.plot_area_sqft,
            plot_area_sqm=plot.plot_area_sqm,
            envelope_result=result,
            placement_result=pr,
            building_height_m=height,
            road_width_m=road_width,
            tp_scheme=f"TP{tp}",
            fp_number=fp_number,
            skeleton=skeleton,
            rule_results=None,
        )
        rm = agg.regulatory_metrics
        pm = agg.plot_metrics
        row.achieved_fsi = rm.achieved_fsi
        row.max_fsi = rm.max_fsi
        row.achieved_gc_pct = rm.achieved_gc_pct
        row.permissible_gc_pct = rm.permissible_gc_pct
        row.cop_provided_sqft = rm.cop_provided_sqft
        row.cop_required_sqft = rm.cop_required_sqft
        row.cop_pct = (100.0 * rm.cop_provided_sqft / rm.cop_required_sqft) if rm.cop_required_sqft > 0 else 0.0
        row.frontage_m = pm.frontage_length_m
        row.height_band = pm.height_band_label
        row.aggregate = agg
        return row
    except Exception as e:
        row.error = str(e)
        traceback.print_exc()
        return row


class Command(BaseCommand):
    help = "Run feasibility pipeline for selected plots and optionally validate against expected values (Part 7)."

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, required=True, help="TP scheme number (e.g. 14)")
        parser.add_argument("--height", type=float, required=True, help="Building height in metres")
        parser.add_argument("--limit", type=int, default=10, help="Max number of plots to validate")
        parser.add_argument("--road-width", type=float, default=9.0)
        parser.add_argument("--road-edges", type=str, default="0")
        parser.add_argument(
            "--expected",
            type=str,
            default="",
            help="Path to CSV with expected_fsi, expected_gc_pct, expected_cop_pct, expected_frontage_m, expected_height_band per fp_number",
        )
        parser.add_argument("--output", type=str, default="", help="Write engine output matrix to this CSV path")

    def handle(self, *args, **options):
        tp = options["tp"]
        height = options["height"]
        limit = options["limit"]
        road_width = options["road_width"]
        road_edges = _parse_road_edges(options["road_edges"])
        expected_path = (options["expected"] or "").strip()
        output_path = (options["output"] or "").strip()

        plots = _select_plots(tp, limit)
        if not plots:
            self.stdout.write(self.style.ERROR(f"No plots found for TP{tp}."))
            return

        expected_by_fp = {}
        if expected_path:
            try:
                from architecture.feasibility.validation import load_expected_csv
                expected_by_fp = load_expected_csv(expected_path)
                self.stdout.write(f"Loaded expected values for {len(expected_by_fp)} FPs from {expected_path}")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not load --expected CSV: {e}"))

        rows: list[ValidationRow] = []
        for plot in plots:
            row = _run_pipeline_for_plot(plot, height, road_width, road_edges, tp)
            rows.append(row)

        # Print validation matrix
        self.stdout.write("")
        self.stdout.write("=" * 100)
        self.stdout.write(f"Feasibility validation matrix — TP{tp}  Height: {height}m")
        self.stdout.write("=" * 100)
        self.stdout.write(
            f"{'FP':>6}  {'Plot_sqft':>10}  {'FSI':>6}  {'GC%':>6}  {'COP%':>6}  {'Front_m':>8}  {'Band':<10}  {'Valid':<6}"
        )
        self.stdout.write("-" * 100)

        for r in rows:
            if r.error:
                self.stdout.write(
                    f"{r.fp_number:>6}  {r.plot_area_sqft:>10.0f}  —      —      —       —        —           {r.error[:20]}"
                )
                continue
            valid_str = "OK"
            checks = []
            if r.fp_number in expected_by_fp:
                from architecture.feasibility.validation import validate_aggregate_against_expected
                checks = validate_aggregate_against_expected(r.aggregate, **expected_by_fp[r.fp_number])
                valid_str = "PASS" if all(c.passed for c in checks) else "FAIL"
            self.stdout.write(
                f"{r.fp_number:>6}  {r.plot_area_sqft:>10.0f}  {r.achieved_fsi:>6.2f}  {r.achieved_gc_pct:>6.1f}  "
                f"{r.cop_pct:>6.1f}  {r.frontage_m:>8.2f}  {r.height_band:<10}  {valid_str:<6}"
            )
            for c in checks:
                if not c.passed:
                    self.stdout.write(self.style.WARNING(f"       -> {c.metric}: {c.message}"))

        self.stdout.write("-" * 100)
        n_ok = sum(1 for r in rows if not r.error)
        n_fail = sum(1 for r in rows if r.error)
        self.stdout.write(f"Summary: {len(rows)} plots, {n_ok} pipeline OK, {n_fail} pipeline failed.")
        if expected_by_fp:
            validated = [r for r in rows if not r.error and r.fp_number in expected_by_fp]
            from architecture.feasibility.validation import validate_aggregate_against_expected
            pass_n = sum(
                1 for r in validated
                if all(c.passed for c in validate_aggregate_against_expected(r.aggregate, **expected_by_fp[r.fp_number]))
            )
            self.stdout.write(f"Expected comparison: {len(validated)} with expected values, {pass_n} PASS.")
        self.stdout.write("")

        if output_path:
            self._write_output_csv(rows, output_path)
            self.stdout.write(f"Engine output written to {output_path}")

    def _write_output_csv(self, rows: list[ValidationRow], path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "fp_number", "plot_area_sqft", "achieved_fsi", "max_fsi",
                "achieved_gc_pct", "permissible_gc_pct",
                "cop_provided_sqft", "cop_required_sqft", "cop_pct",
                "frontage_m", "height_band", "error",
            ])
            for r in rows:
                w.writerow([
                    r.fp_number, r.plot_area_sqft, r.achieved_fsi, r.max_fsi,
                    r.achieved_gc_pct, r.permissible_gc_pct,
                    r.cop_provided_sqft, r.cop_required_sqft, r.cop_pct,
                    r.frontage_m, r.height_band, r.error,
                ])
