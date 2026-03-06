"""
architecture/management/commands/test_presentation_engine.py
--------------------------------------------------------------
Stress-tests the Presentation Engine across multiple TP plots.

Validates: wall offset stability, room split validity, door placement,
geometry integrity, DXF output consistency, and fallback behavior.

Usage:
    python manage.py test_presentation_engine --tp 14 --height 16.5 --export-dir ./test_outputs
    python manage.py test_presentation_engine --tp 14 --height 16.5 --limit 5 --export-dir ./test_outputs
"""

from __future__ import annotations

import os
import traceback
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot
from common.units import sqft_to_sqm


def _parse_road_edges(raw: str) -> list[int]:
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [0]


def _fmt_height(height: float) -> str:
    s = f"{height:.10f}".rstrip("0").rstrip(".")
    return s


@dataclass
class Row:
    fp: str
    area: float
    env_area: float
    pattern: str
    presentation: str  # "OK" | "FALLBACK"
    dxf_kb: float
    status: str  # "PASS" | "FAIL"
    error: str = ""


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


def _select_plots(tp: int, limit: int) -> list[Plot]:
    base = list(
        Plot.objects.filter(tp_scheme=f"TP{tp}").order_by("fp_number")
    )
    if not base:
        return []

    by_area_asc = sorted(base, key=lambda p: (p.area_geometry, p.fp_number))
    smallest = by_area_asc[:2]
    largest = by_area_asc[-2:] if len(by_area_asc) >= 2 else by_area_asc[-1:]

    by_ratio_desc = sorted(
        base,
        key=lambda p: (-_bbox_ratio(p), p.fp_number),
    )
    near_square = by_ratio_desc[:2]

    by_ratio_asc = sorted(
        base,
        key=lambda p: (_bbox_ratio(p), p.fp_number),
    )
    long_narrow = by_ratio_asc[:2]

    irregular = [p for p in base if p.geom.geom_type != "Polygon"][:2]

    seen = set()
    result = []
    for group in [smallest, largest, near_square, long_narrow, irregular]:
        for p in group:
            if p.fp_number not in seen:
                seen.add(p.fp_number)
                result.append(p)
    result = sorted(result, key=lambda p: p.fp_number)[:limit]
    return result


def _validate_presentation_model(pm) -> tuple[bool, str]:
    try:
        from shapely.geometry import Polygon as ShapelyPolygon
        for w in pm.external_walls + pm.core_walls:
            if not w.outer_coords or len(w.outer_coords) < 3:
                return False, "wall empty or degenerate"
            try:
                poly = ShapelyPolygon(w.outer_coords)
                if not poly.is_valid:
                    return False, "wall self-intersection or invalid"
            except Exception:
                return False, "wall polygon invalid"
            if w.is_double_line and w.inner_coords and len(w.inner_coords) < 3:
                return False, "inner wall degenerate"
        for r in pm.rooms:
            try:
                poly = r.polygon
                if poly is None or not getattr(poly, "is_valid", True) or getattr(poly, "area", 0) <= 0:
                    return False, "invalid room polygon"
            except Exception:
                return False, "room polygon check failed"
        for d in pm.doors:
            if d.width_m <= 0:
                return False, "door arc radius <= 0"
        if not pm.title_block.lines:
            return False, "annotation text empty"
        return True, ""
    except Exception as e:
        return False, str(e)


class Command(BaseCommand):
    help = "Stress-test the Presentation Engine across multiple TP plots."

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, required=True, help="TP scheme number (e.g. 14)")
        parser.add_argument("--height", type=float, required=True, help="Building height in metres")
        parser.add_argument("--limit", type=int, default=10, help="Max number of plots to test")
        parser.add_argument("--export-dir", type=str, required=True, help="Directory for test DXF files")
        parser.add_argument("--presentation", action="store_true", default=True, help="Use presentation layer (default True)")

    def handle(self, *args, **options):
        tp = options["tp"]
        height = options["height"]
        limit = options["limit"]
        export_dir = os.path.abspath(options["export_dir"])
        use_presentation = options["presentation"]
        road_width = 12.0
        road_edges = [0]
        min_width = 5.0
        min_depth = 3.5

        plots = _select_plots(tp, limit)
        if not plots:
            self.stdout.write(self.style.ERROR(f"No plots found for TP{tp}."))
            return

        os.makedirs(export_dir, exist_ok=True)

        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Presentation Engine Stress Test — TP{tp}")
        self.stdout.write(f"Height: {height}m")
        self.stdout.write("=" * 60)
        self.stdout.write("")

        rows: list[Row] = []
        presentation_ok = 0
        fallback_used = 0
        failures = 0

        for plot in plots:
            fp = plot.fp_number
            area_sqft = plot.plot_area_sqft
            row = Row(
                fp=fp,
                area=area_sqft,
                env_area=0.0,
                pattern="",
                presentation="",
                dxf_kb=0.0,
                status="PASS",
            )
            try:
                plot_wkt = plot.geom.wkt
            except Exception as e:
                row.status = "FAIL"
                row.error = f"geom.wkt: {e}"
                rows.append(row)
                failures += 1
                traceback.print_exc()
                continue

            try:
                from envelope_engine.services.envelope_service import compute_envelope
                result = compute_envelope(
                    plot_wkt=plot_wkt,
                    building_height=height,
                    road_width=road_width,
                    road_facing_edges=road_edges,
                )
                if result.status != "VALID":
                    row.status = "FAIL"
                    row.error = f"envelope {result.status}"
                    rows.append(row)
                    failures += 1
                    continue
                envelope_wkt = result.envelope_polygon.wkt
                row.env_area = result.envelope_area_sqft or 0.0
            except Exception as e:
                row.status = "FAIL"
                row.error = f"envelope: {e}"
                rows.append(row)
                failures += 1
                traceback.print_exc()
                continue

            try:
                from placement_engine.services.placement_service import compute_placement
                pr = compute_placement(
                    envelope_wkt=envelope_wkt,
                    building_height_m=height,
                    n_towers=1,
                    min_width_m=min_width,
                    min_depth_m=min_depth,
                )
                if pr.status not in ("VALID", "TOO_TIGHT") or pr.n_towers_placed == 0:
                    row.status = "FAIL"
                    row.error = f"placement {pr.status}"
                    rows.append(row)
                    failures += 1
                    continue
                if not pr.per_tower_core_validation:
                    row.status = "FAIL"
                    row.error = "no core validation"
                    rows.append(row)
                    failures += 1
                    continue
                cv = pr.per_tower_core_validation[0]
                if cv.core_fit_status == "NO_CORE_FIT":
                    row.status = "FAIL"
                    row.error = "NO_CORE_FIT"
                    rows.append(row)
                    failures += 1
                    continue
                row.pattern = cv.selected_pattern or ""
            except Exception as e:
                row.status = "FAIL"
                row.error = f"placement: {e}"
                rows.append(row)
                failures += 1
                traceback.print_exc()
                continue

            try:
                from floor_skeleton.services import generate_floor_skeleton
                from floor_skeleton.models import NO_SKELETON_PATTERN
                skeleton = generate_floor_skeleton(
                    footprint=pr.footprints[0],
                    core_validation=cv,
                )
                if skeleton.pattern_used == NO_SKELETON_PATTERN:
                    row.status = "FAIL"
                    row.error = "NO_SKELETON"
                    rows.append(row)
                    failures += 1
                    continue
            except Exception as e:
                row.status = "FAIL"
                row.error = f"skeleton: {e}"
                rows.append(row)
                failures += 1
                traceback.print_exc()
                continue

            filename = f"TP{tp}_FP{fp}_H{_fmt_height(height)}_test.dxf"
            output_path = os.path.join(export_dir, filename)

            if use_presentation:
                try:
                    from presentation_engine.drawing_composer import compose
                    from dxf_export.presentation_exporter import export_presentation_to_dxf
                    pm = compose(skeleton, tp_num=tp, fp_num=int(fp) if fp.isdigit() else None, height_m=height)
                    valid, msg = _validate_presentation_model(pm)
                    if not valid:
                        row.status = "FAIL"
                        row.error = f"validation: {msg}"
                        rows.append(row)
                        failures += 1
                        continue
                    export_presentation_to_dxf(pm, output_path)
                    if pm.used_fallback_walls or pm.used_fallback_rooms or pm.used_fallback_doors:
                        row.presentation = "FALLBACK"
                    else:
                        row.presentation = "OK"
                except Exception as e:
                    try:
                        from dxf_export.exporter import export_floor_skeleton_to_dxf
                        export_floor_skeleton_to_dxf(skeleton, output_path)
                        row.presentation = "FALLBACK"
                        used_fallback = True
                    except Exception as e2:
                        row.status = "FAIL"
                        row.error = f"dxf: {e2}"
                        rows.append(row)
                        failures += 1
                        traceback.print_exc()
                        continue
            else:
                try:
                    from dxf_export.exporter import export_floor_skeleton_to_dxf
                    export_floor_skeleton_to_dxf(skeleton, output_path)
                    row.presentation = "OK"
                except Exception as e:
                    row.status = "FAIL"
                    row.error = f"dxf: {e}"
                    rows.append(row)
                    failures += 1
                    traceback.print_exc()
                    continue

            try:
                size = os.path.getsize(output_path)
                row.dxf_kb = round(size / 1024.0, 1)
            except Exception:
                row.dxf_kb = 0.0

            if use_presentation:
                if row.presentation == "OK":
                    presentation_ok += 1
                else:
                    fallback_used += 1
            rows.append(row)

        self.stdout.write(
            f"{'FP':>6}  {'Area':>8}  {'EnvArea':>8}  {'Pattern':<12}  "
            f"{'Presentation':<10}  {'DXF KB':>7}  {'Status':<6}"
        )
        self.stdout.write("-" * 60)
        for r in rows:
            self.stdout.write(
                f"{r.fp:>6}  {r.area:>8.0f}  {r.env_area:>8.0f}  {r.pattern:<12}  "
                f"{r.presentation:<10}  {r.dxf_kb:>7.1f}  {r.status:<6}"
            )
            if r.error:
                self.stdout.write(self.style.WARNING(f"       -> {r.error}"))
        self.stdout.write("-" * 60)
        self.stdout.write("Summary:")
        self.stdout.write(f"  Total tested:     {len(rows)}")
        self.stdout.write(f"  Presentation OK:  {presentation_ok}")
        self.stdout.write(f"  Fallback used:    {fallback_used}")
        self.stdout.write(f"  Failures:         {failures}")
        self.stdout.write("")
