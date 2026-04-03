"""
Management command: assign_designation_from_dxf
-----------------------------------------------
Assign plot.designation by spatially matching each FP polygon to land-use
polygons drawn in the TP DXF (e.g. residential/commercial/public/open space).

Usage:
    python manage.py assign_designation_from_dxf <dxf_path> --tp-scheme TP14 [--city Surat] [--dry-run]
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.wkt import loads as load_wkt

from tp_ingestion.models import Plot


LAYER_TO_DESIGNATION: dict[str, str] = {
    "01residential": "SALE FOR RESIDENTIAL",
    "residential": "SALE FOR RESIDENTIAL",
    "02commercial": "SALE FOR COMMERCIAL",
    "03publicpurpose": "PUBLIC PURPOSE",
    "04green": "OPEN SPACE/GARDEN",
}


def _lwpolyline_to_polygon(entity) -> ShapelyPolygon | None:
    if not getattr(entity, "is_closed", False):
        return None
    pts = [(v[0], v[1]) for v in entity.get_points()]
    if len(pts) < 3:
        return None
    poly = ShapelyPolygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if poly.is_valid else None


def _hatch_path_to_polygon(path) -> ShapelyPolygon | None:
    verts = getattr(path, "vertices", None)
    if not verts:
        return None
    pts = []
    for v in verts:
        if isinstance(v, (tuple, list)) and len(v) >= 2:
            pts.append((float(v[0]), float(v[1])))
    if len(pts) < 3:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    poly = ShapelyPolygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if poly.is_valid else None


class Command(BaseCommand):
    help = "Assign plot.designation from DXF land-use layers."

    def add_arguments(self, parser):
        parser.add_argument("dxf_path", type=str, help="Path to the TP scheme .dxf file.")
        parser.add_argument("--tp-scheme", type=str, dest="tp_scheme", required=True)
        parser.add_argument("--city", type=str, default=None)
        parser.add_argument("--dry-run", action="store_true", dest="dry_run")

    def handle(self, *args, **options):
        dxf_path = Path(options["dxf_path"])
        if not dxf_path.exists():
            raise CommandError(f"DXF not found: {dxf_path}")

        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        zone_polygons: list[tuple[str, ShapelyPolygon]] = []
        wanted_layers = {k.lower() for k in LAYER_TO_DESIGNATION}

        for entity in msp:
            layer = entity.dxf.layer.lower()
            if layer not in wanted_layers:
                continue

            if entity.dxftype() == "LWPOLYLINE":
                poly = _lwpolyline_to_polygon(entity)
                if poly is not None:
                    zone_polygons.append((LAYER_TO_DESIGNATION[layer], poly))
                continue

            if entity.dxftype() == "HATCH":
                for path in entity.paths:
                    poly = _hatch_path_to_polygon(path)
                    if poly is not None:
                        zone_polygons.append((LAYER_TO_DESIGNATION[layer], poly))
                continue

        if not zone_polygons:
            raise CommandError(
                "No zoning polygons found in expected layers: "
                + ", ".join(sorted(LAYER_TO_DESIGNATION.keys()))
            )

        qs = Plot.objects.filter(tp_scheme=options["tp_scheme"])
        if options.get("city"):
            qs = qs.filter(city=options["city"])
        plots = list(qs)
        if not plots:
            raise CommandError("No plots found for requested tp-scheme/city.")

        updated = 0
        unmatched = 0

        with transaction.atomic():
            for p in plots:
                shp_plot = load_wkt(p.geom.wkt)

                # Choose designation by max overlap area with zoning polygons
                best_designation = ""
                best_area = 0.0
                for designation, zone in zone_polygons:
                    if not shp_plot.intersects(zone):
                        continue
                    area = shp_plot.intersection(zone).area
                    if area > best_area:
                        best_area = area
                        best_designation = designation

                if not best_designation:
                    unmatched += 1
                    continue

                if p.designation != best_designation:
                    p.designation = best_designation
                    if not options["dry_run"]:
                        p.save(update_fields=["designation"])
                    updated += 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        self.stdout.write(
            f"Designation assigned/updated for {updated} plot(s). "
            f"No zoning match for {unmatched} plot(s)."
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run - no changes saved."))
