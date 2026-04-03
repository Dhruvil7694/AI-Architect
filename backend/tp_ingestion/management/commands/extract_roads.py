"""
Management command: extract_roads
----------------------------------
Extract road geometries from existing Plot records and create Road entries.

Identifies plots with road designations, extracts centerlines, and computes widths.

Usage:
    python manage.py extract_roads --tp-scheme TP14 --city Ahmedabad

Optional flags:
    --dry-run    : Preview roads without saving to database
"""

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import LineString as GEOSLineString

from tp_ingestion.models import Plot, Road
from tp_ingestion.geometry_utils import (
    extract_road_centerline,
    compute_road_width_from_polygon,
    get_label_point,
)
from shapely.geometry import Polygon as ShapelyPolygon


class Command(BaseCommand):
    help = "Extract road geometries from plots and create Road records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--city",
            type=str,
            required=True,
            help="City name (e.g. Ahmedabad)",
        )
        parser.add_argument(
            "--tp-scheme",
            type=str,
            required=True,
            dest="tp_scheme",
            help="TP scheme identifier (e.g. TP14)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Preview roads without saving to database",
        )

    def handle(self, *args, **options):
        city = options["city"]
        tp_scheme = options["tp_scheme"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode — no data will be written."))

        # Find all plots with road designations
        road_plots = Plot.objects.filter(
            city=city,
            tp_scheme=tp_scheme,
        ).exclude(designation="")

        # Filter for road-like designations
        road_keywords = ["ROAD", "SCHEME ROAD"]
        roads_found = []

        for plot in road_plots:
            designation = (plot.designation or "").upper()
            if not any(kw in designation for kw in road_keywords):
                continue

            # Convert GEOS polygon to Shapely
            coords = [(pt[0], pt[1]) for pt in plot.geom.coords[0]]
            shapely_poly = ShapelyPolygon(coords)

            # Extract centerline
            centerline = extract_road_centerline(shapely_poly)

            # Compute width (or extract from designation/road_width_m)
            width_m = plot.road_width_m
            if not width_m:
                # Try to extract from designation text
                import re
                match = re.search(r"(\d+(?:\.\d+)?)\s*(?:M|MT)\b", designation)
                if match:
                    width_m = float(match.group(1))
                else:
                    # Compute from geometry (in DXF units, typically feet)
                    width_dxf = compute_road_width_from_polygon(shapely_poly)
                    # Convert feet to meters (approximate)
                    width_m = width_dxf * 0.3048

            # Extract road name
            name = designation.strip()

            roads_found.append({
                "plot": plot,
                "centerline": centerline,
                "width_m": width_m,
                "name": name,
            })

        self.stdout.write(f"\nFound {len(roads_found)} road plots in {city} / {tp_scheme}")

        if not roads_found:
            self.stdout.write(self.style.WARNING("No roads found."))
            return

        # Preview
        for i, road_data in enumerate(roads_found, 1):
            self.stdout.write(
                f"  [{i}] {road_data['name'][:50]} — "
                f"Width: {road_data['width_m']:.1f}m — "
                f"Centerline: {'✓' if road_data['centerline'] else '✗'}"
            )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nDry-run complete. {len(roads_found)} roads identified."))
            return

        # Save to database
        # Clear existing roads for this scheme
        Road.objects.filter(city=city, tp_scheme=tp_scheme).delete()

        roads_to_create = []
        for road_data in roads_found:
            plot = road_data["plot"]
            centerline = road_data["centerline"]
            width_m = road_data["width_m"]
            name = road_data["name"]

            # Convert centerline to GEOS
            geos_centerline = None
            if centerline:
                coords = list(centerline.coords)
                geos_centerline = GEOSLineString(coords, srid=0)

            roads_to_create.append(
                Road(
                    city=city,
                    tp_scheme=tp_scheme,
                    geom=plot.geom,
                    centerline=geos_centerline,
                    width_m=width_m,
                    name=name,
                )
            )

        if roads_to_create:
            Road.objects.bulk_create(roads_to_create, batch_size=100)

        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Saved {len(roads_to_create)} roads to database.")
        )
