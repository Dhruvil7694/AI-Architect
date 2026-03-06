"""
Management command: assign_road_data_from_dxf
---------------------------------------------
Get all road sizes and edges for each FP from the DXF by:
  1. Extracting road width TEXT labels (e.g. "18.00 MT.") from the DXF (layer ROADNAME).
  2. For each plot polygon, finding which exterior edge is closest to each label.
  3. Assigning that edge as a road edge with the label's width; then updating the DB.

Usage:
    python manage.py assign_road_data_from_dxf <dxf_path> --tp-scheme TP14 [--city Surat] [--max-distance 80] [--dry-run]
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import Point as ShapelyPoint

from tp_ingestion.models import Plot
from tp_ingestion.services.dxf_reader import read_dxf_road_widths
from architecture.spatial.road_edge_detector import _edge_segments


def _point_to_segment_distance(px: float, py: float, segment) -> float:
    """Distance from point (px, py) to GEOS LineString segment (two points)."""
    coords = list(segment.coords)
    if len(coords) < 2:
        return float("inf")
    line = ShapelyLineString([(coords[0][0], coords[0][1]), (coords[1][0], coords[1][1])])
    return ShapelyPoint(px, py).distance(line)


class Command(BaseCommand):
    help = "Assign road_width_m and road_edges for all plots from DXF road width labels."

    def add_arguments(self, parser):
        parser.add_argument("dxf_path", type=str, help="Path to the TP scheme .dxf file.")
        parser.add_argument("--tp-scheme", type=str, dest="tp_scheme", required=True)
        parser.add_argument("--city", type=str, default=None)
        parser.add_argument(
            "--max-distance",
            type=float,
            default=80.0,
            dest="max_distance",
            help="Max distance from road label to plot edge to assign (DXF units, default 80).",
        )
        parser.add_argument(
            "--road-layer",
            type=str,
            default="ROADNAME",
            dest="road_layer",
            help="DXF layer name for road width text (default ROADNAME).",
        )
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    def handle(self, *args, **options):
        dxf_path = Path(options["dxf_path"])
        if not dxf_path.exists():
            raise CommandError("DXF not found: %s" % dxf_path)

        qs = Plot.objects.filter(tp_scheme=options["tp_scheme"]).order_by("fp_number")
        if options.get("city"):
            qs = qs.filter(city=options["city"])
        plots = list(qs)
        if not plots:
            raise CommandError("No plots found for tp_scheme=%s" % options["tp_scheme"])

        # Load road width labels from DXF
        road_widths = read_dxf_road_widths(dxf_path, road_text_layers=[options.get("road_layer", "ROADNAME")])
        if not road_widths:
            self.stdout.write(self.style.WARNING("No road width labels found in DXF. Check --road-layer."))
            return

        # Build list of (fp_number, edge_idx, segment) for all plot edges
        all_edges: list[tuple[str, int, object]] = []
        for p in plots:
            segments = _edge_segments(p.geom)
            for idx, seg in enumerate(segments):
                all_edges.append((p.fp_number, idx, seg))

        # For each road label, assign to the closest plot edge within max_distance.
        # (fp_number, edge_idx) -> (width_m, dist); keep the closest label per edge.
        assigned: dict[tuple[str, int], tuple[float, float]] = {}
        for width_m, point in road_widths:
            best_fp, best_idx, best_dist = None, None, float("inf")
            px, py = point.x, point.y
            for fp_number, edge_idx, segment in all_edges:
                d = _point_to_segment_distance(px, py, segment)
                if d < best_dist and d <= options["max_distance"]:
                    best_dist = d
                    best_fp, best_idx = fp_number, edge_idx
            if best_fp is not None:
                key = (best_fp, best_idx)
                if key not in assigned or best_dist < assigned[key][1]:
                    assigned[key] = (width_m, best_dist)

        # Group by fp_number: road_edges = sorted set of indices, road_width_m = max width
        by_fp: dict[str, dict] = defaultdict(lambda: {"edges": set(), "widths": []})
        for (fp_number, edge_idx), (width_m, _dist) in assigned.items():
            by_fp[fp_number]["edges"].add(edge_idx)
            by_fp[fp_number]["widths"].append(width_m)

        updated = 0
        with transaction.atomic():
            for p in plots:
                data = by_fp.get(p.fp_number)
                if not data or not data["edges"]:
                    continue
                road_edges_str = ",".join(str(i) for i in sorted(data["edges"]))
                road_width_m = max(data["widths"])
                if (p.road_edges or "") != road_edges_str or p.road_width_m != road_width_m:
                    p.road_edges = road_edges_str
                    p.road_width_m = road_width_m
                    if not options.get("dry_run"):
                        p.save(update_fields=["road_edges", "road_width_m"])
                    updated += 1
                    if options.get("dry_run"):
                        self.stdout.write("  [dry-run] %s FP %s -> edges=%s width=%.1f m" % (
                            p.tp_scheme, p.fp_number, road_edges_str, road_width_m))

            if options.get("dry_run"):
                transaction.set_rollback(True)

        self.stdout.write(
            "Assigned road data to %d plot(s) from %d DXF road width label(s)."
            % (updated, len(road_widths))
        )
        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("Dry run — no changes saved."))
        else:
            self.stdout.write(self.style.SUCCESS("Done."))