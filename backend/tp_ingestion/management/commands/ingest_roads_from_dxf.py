"""
Management command: ingest_roads_from_dxf
------------------------------------------
Extract road polygons from a TP scheme DXF file and create Road records.

Road polygons are identified by:
  1. Reading all polygons from the DXF (same polygonize pipeline as ingest_tp).
  2. Matching each polygon against road width TEXT labels (e.g. "18.00 MT.").
  3. Polygons that contain (or are closest to) a road width label become Road records.

Existing FP plot polygons are excluded automatically (they overlap existing Plot.geom).

Usage:
    python manage.py ingest_roads_from_dxf <dxf_path> --tp-scheme TP14 --city Surat
    python manage.py ingest_roads_from_dxf <dxf_path> --tp-scheme TP14 --city Surat --dry-run
"""

from __future__ import annotations

import math
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.contrib.gis.geos import Polygon as GEOSPolygon
from django.contrib.gis.geos import LineString as GEOSLineString

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon as ShapelyPolygon

from tp_ingestion.models import Plot, Road
from tp_ingestion.services.dxf_reader import read_dxf, read_dxf_road_widths
from tp_ingestion.geometry_utils import extract_road_centerline


class Command(BaseCommand):
    help = "Ingest road polygons from a TP DXF into Road records."

    def add_arguments(self, parser):
        parser.add_argument("dxf_path", type=str, help="Path to the TP scheme .dxf file.")
        parser.add_argument("--tp-scheme", type=str, dest="tp_scheme", required=True)
        parser.add_argument("--city", type=str, default="Surat")
        parser.add_argument(
            "--min-area",
            type=float,
            default=500.0,
            dest="min_area",
            help="Minimum polygon area (DXF units²) to be considered a road (default 500).",
        )
        parser.add_argument(
            "--label-radius",
            type=float,
            default=300.0,
            dest="label_radius",
            help="Max distance from road width label to polygon centroid (DXF units, default 300).",
        )
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    def handle(self, *args, **options):
        dxf_path = Path(options["dxf_path"])
        if not dxf_path.exists():
            raise CommandError(f"DXF not found: {dxf_path}")

        tp_scheme = options["tp_scheme"]
        city = options["city"]
        dry_run = options["dry_run"]
        min_area = options["min_area"]
        label_radius = options["label_radius"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode — no data written."))

        # 1. Read all polygons from DXF (no layer filter → all geometry).
        self.stdout.write(f"Reading polygons from {dxf_path.name}...")
        dxf_result = read_dxf(str(dxf_path), min_polygon_area=min_area)
        self.stdout.write(f"  {len(dxf_result.polygons)} polygons extracted (area >= {min_area})")

        # 2. Read road width labels (all layers).
        road_labels = read_dxf_road_widths(str(dxf_path), road_text_layers=None)
        self.stdout.write(f"  {len(road_labels)} road width labels found")
        if not road_labels:
            self.stdout.write(self.style.WARNING("No road width labels found — aborting."))
            return

        # 3. Load existing FP plot polygons for exclusion.
        fp_plots = list(Plot.objects.filter(city=city, tp_scheme=tp_scheme))
        self.stdout.write(f"  {len(fp_plots)} existing FP plots loaded for exclusion")

        # Build Shapely polys from FP plot geoms for overlap check.
        fp_shapely: list[ShapelyPolygon] = []
        for p in fp_plots:
            try:
                coords = [(c[0], c[1]) for c in p.geom.coords[0]]
                fp_shapely.append(ShapelyPolygon(coords))
            except Exception:
                continue

        def is_fp_plot(poly: ShapelyPolygon) -> bool:
            """Return True if poly overlaps substantially with any existing FP plot."""
            for fp in fp_shapely:
                try:
                    if poly.intersects(fp):
                        overlap = poly.intersection(fp).area
                        if overlap / max(poly.area, 1e-9) > 0.3:
                            return True
                except Exception:
                    continue
            return False

        # 4. For each road width label, find the polygon it falls inside (or is closest to).
        label_to_poly: dict[int, tuple[float, ShapelyPolygon]] = {}  # poly_idx -> (width_m, poly)

        for width_m, pt in road_labels:
            best_idx = None
            best_dist = float("inf")
            for i, poly in enumerate(dxf_result.polygons):
                if poly.area < min_area:
                    continue
                try:
                    shapely_pt = ShapelyPoint(pt.x, pt.y)
                    if poly.contains(shapely_pt):
                        dist = 0.0
                    else:
                        dist = poly.centroid.distance(shapely_pt)
                    if dist < best_dist and dist <= label_radius:
                        best_dist = dist
                        best_idx = i
                except Exception:
                    continue

            if best_idx is not None:
                # Keep the wider road for a polygon if multiple labels match.
                existing = label_to_poly.get(best_idx)
                if existing is None or width_m > existing[0]:
                    label_to_poly[best_idx] = (width_m, dxf_result.polygons[best_idx])

        self.stdout.write(f"  {len(label_to_poly)} road polygons matched to width labels")

        # 5. Filter out FP plot overlaps.
        road_candidates: list[tuple[float, ShapelyPolygon]] = []
        for _idx, (width_m, poly) in label_to_poly.items():
            if is_fp_plot(poly):
                continue
            road_candidates.append((width_m, poly))

        self.stdout.write(f"  {len(road_candidates)} road polygons after FP exclusion")

        if not road_candidates:
            self.stdout.write(self.style.WARNING("No road polygons to create."))
            return

        # 6. Clear existing Road records and create new ones.
        if not dry_run:
            deleted, _ = Road.objects.filter(city=city, tp_scheme=tp_scheme).delete()
            self.stdout.write(f"  Deleted {deleted} existing Road records")

        roads_created = 0
        for width_m, poly in road_candidates:
            # Convert Shapely polygon → GEOS.
            try:
                exterior = [(x, y) for x, y in poly.exterior.coords]
                geos_poly = GEOSPolygon(exterior, srid=0)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Skipping invalid polygon: {exc}"))
                continue

            # Extract centerline for line-following road labels.
            geos_centerline = None
            try:
                cl = extract_road_centerline(poly)
                if cl and len(list(cl.coords)) >= 2:
                    geos_centerline = GEOSLineString(list(cl.coords), srid=0)
            except Exception:
                pass

            name = f"{int(width_m) if width_m == int(width_m) else width_m:.1f} m Road"

            if not dry_run:
                Road.objects.create(
                    city=city,
                    tp_scheme=tp_scheme,
                    geom=geos_poly,
                    centerline=geos_centerline,
                    width_m=width_m,
                    name=name,
                )
            else:
                self.stdout.write(f"  [dry-run] Road: {name}, area={poly.area:.0f}, centerline={'OK' if geos_centerline else 'X'}")
            roads_created += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nDry-run complete — {roads_created} roads would be created."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nOK Created {roads_created} Road records for {city} / {tp_scheme}."))
