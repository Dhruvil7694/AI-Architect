"""
placement_engine management command: compute_placement
-------------------------------------------------------
Run the building placement engine for a given PlotEnvelope and print a
structured report.  Optionally save to the database and export intermediate
geometries to GeoJSON for visual inspection in QGIS.

Usage examples:
    python manage.py compute_placement --envelope-id 1 --building-height 16.5 --n-towers 1
    python manage.py compute_placement --envelope-id 1 --building-height 16.5 --n-towers 2 --save
    python manage.py compute_placement --envelope-id 1 --building-height 16.5 --n-towers 1 --export-geojson --export-dir output/
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from envelope_engine.models import PlotEnvelope
from placement_engine.geometry import (
    MIN_FOOTPRINT_WIDTH_M,
    MIN_FOOTPRINT_DEPTH_M,
    DXF_TO_METRES,
)
from placement_engine.services.placement_service import (
    PlacementResult,
    compute_placement,
    save_placement,
)


class Command(BaseCommand):
    help = "Compute building placement for a PlotEnvelope and print a report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--envelope-id",
            type=int,
            required=True,
            help="PK of the PlotEnvelope to use as input.",
        )
        parser.add_argument(
            "--building-height",
            type=float,
            required=True,
            dest="building_height_m",
            help="Proposed building height in metres.",
        )
        parser.add_argument(
            "--n-towers",
            type=int,
            default=1,
            dest="n_towers",
            help="Number of towers to place (default: 1).",
        )
        parser.add_argument(
            "--min-width",
            type=float,
            default=MIN_FOOTPRINT_WIDTH_M,
            dest="min_width_m",
            help=f"Minimum footprint width in metres (default: {MIN_FOOTPRINT_WIDTH_M}).",
        )
        parser.add_argument(
            "--min-depth",
            type=float,
            default=MIN_FOOTPRINT_DEPTH_M,
            dest="min_depth_m",
            help=f"Minimum footprint depth in metres (default: {MIN_FOOTPRINT_DEPTH_M}).",
        )
        parser.add_argument(
            "--save",
            action="store_true",
            default=False,
            help="Persist the result to the database.",
        )
        parser.add_argument(
            "--export-geojson",
            action="store_true",
            default=False,
            help="Export envelope, footprints, and exclusion zones to GeoJSON files.",
        )
        parser.add_argument(
            "--export-dir",
            type=str,
            default="output",
            dest="export_dir",
            help="Directory for GeoJSON export (default: output/).",
        )

    # ──────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        envelope_id       = options["envelope_id"]
        building_height_m = options["building_height_m"]
        n_towers          = options["n_towers"]
        min_width_m       = options["min_width_m"]
        min_depth_m       = options["min_depth_m"]
        do_save           = options["save"]
        do_export         = options["export_geojson"]
        export_dir        = options["export_dir"]

        # ── Load envelope ──────────────────────────────────────────────────────
        try:
            envelope_db = PlotEnvelope.objects.get(pk=envelope_id)
        except PlotEnvelope.DoesNotExist:
            raise CommandError(f"PlotEnvelope with id={envelope_id} not found.")

        if envelope_db.status != "VALID" or not envelope_db.envelope_geom:
            raise CommandError(
                f"PlotEnvelope #{envelope_id} has status={envelope_db.status} "
                "and/or missing envelope_geom. Run compute_envelope first."
            )

        envelope_wkt = envelope_db.envelope_geom.wkt

        self.stdout.write(
            self.style.HTTP_INFO(
                f"\nBuilding Placement Engine"
                f"\n  Envelope #{envelope_id}  "
                f"(Proposal #{envelope_db.proposal_id})"
                f"\n  Envelope area     : {envelope_db.envelope_area_sqft:.1f} sq.ft"
                f"\n  Building height   : {building_height_m} m"
                f"\n  Towers requested  : {n_towers}"
                f"\n  Min footprint     : {min_width_m} m x {min_depth_m} m"
            )
        )
        self.stdout.write("-" * 60)

        # ── Run placement ──────────────────────────────────────────────────────
        result: PlacementResult = compute_placement(
            envelope_wkt=envelope_wkt,
            building_height_m=building_height_m,
            n_towers=n_towers,
            min_width_m=min_width_m,
            min_depth_m=min_depth_m,
        )

        # ── Print report ───────────────────────────────────────────────────────
        self._print_report(result)

        # ── Save to DB ─────────────────────────────────────────────────────────
        if do_save:
            bp = save_placement(result, envelope_db)
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSaved: BuildingPlacement #{bp.pk} "
                    f"with {bp.footprints.count()} FootprintRecord(s)"
                )
            )

        # ── Export GeoJSON ─────────────────────────────────────────────────────
        if do_export:
            self._export_geojson(result, envelope_wkt, export_dir, envelope_id)

    # ──────────────────────────────────────────────────────────────────────────

    def _print_report(self, result: PlacementResult):
        status_style = self.style.SUCCESS if result.status == "VALID" else self.style.WARNING
        if result.status in ("ERROR", "INVALID_INPUT", "NO_FIT", "NO_FIT_CORE"):
            status_style = self.style.ERROR

        self.stdout.write(status_style(f"\nStatus            : {result.status}"))

        if result.error_message:
            self.stdout.write(self.style.ERROR(f"Error             : {result.error_message}"))

        self.stdout.write(
            f"Towers requested  : {result.n_towers_requested}\n"
            f"Towers placed     : {result.n_towers_placed}\n"
            f"Spacing required  : {result.spacing_required_m:.3f} m  "
            f"({result.spacing_required_dxf:.3f} ft)\n"
        )

        if result.orientation_primary_deg is not None:
            self.stdout.write(
                f"Orientation       : primary={result.orientation_primary_deg:.2f}deg  "
                f"secondary={result.orientation_secondary_deg:.2f}deg\n"
                f"Packing mode      : {result.packing_mode}\n"
            )
        if result.grid_resolution_dxf is not None:
            self.stdout.write(f"Grid resolution   : {result.grid_resolution_dxf:.4f} ft\n")

        for i, fp in enumerate(result.footprints):
            self.stdout.write(
                f"\n  Tower {i}:\n"
                f"    Area            : {fp.area_sqft:.2f} sq.ft\n"
                f"    Width x Depth   : {fp.width_m:.2f} m x {fp.depth_m:.2f} m  "
                f"({fp.width_dxf:.2f} ft x {fp.depth_dxf:.2f} ft)\n"
                f"    Orientation     : {fp.orientation_label} "
                f"@ {fp.orientation_angle_deg:.2f} deg\n"
                f"    Aspect ratio    : {fp.aspect_ratio:.2f}:1\n"
                f"    Grid resolution : {fp.grid_resolution_dxf:.4f} ft\n"
                f"    Component index : {fp.source_component_index}\n"
            )

            # ── Core validation section per tower ──────────────────────────────
            if i < len(result.per_tower_core_validation):
                cv = result.per_tower_core_validation[i]
                core_style = self.style.SUCCESS if cv.core_fit_status == "VALID" else self.style.ERROR
                self.stdout.write(
                    f"    --- Core Validation ---\n"
                    f"    Core fit status : "
                )
                self.stdout.write(core_style(cv.core_fit_status))
                self.stdout.write(
                    f"    Layout pattern  : {cv.selected_pattern}\n"
                    f"    Staircases req  : {cv.n_staircases_required}  "
                    f"(lift required: {cv.lift_required})\n"
                    f"    Core package    : {cv.core_pkg_width_m:.2f} m wide x "
                    f"{cv.core_pkg_depth_m:.2f} m deep\n"
                    f"    Core area est.  : {cv.core_area_estimate_sqm:.2f} sq.m\n"
                    f"    Remaining usable: {cv.remaining_usable_sqm:.2f} sq.m\n"
                )
                self.stdout.write("    Core audit:\n")
                for entry in cv.audit_log:
                    pat = entry.get("pattern", "?")
                    outcome = entry.get("outcome", "?")
                    dc = entry.get("depth_check", {})
                    wc = entry.get("width_check", {})
                    outcome_style = (self.style.SUCCESS if outcome == "SELECTED"
                                     else self.style.WARNING)
                    line = (
                        f"      {pat:15s}: "
                        f"depth {dc.get('actual_m','?'):.2f}>={dc.get('required_m','?'):.2f}m "
                        f"[{'OK' if dc.get('pass') else 'FAIL':{4}}]  "
                        f"width {wc.get('actual_m','?'):.2f}>={wc.get('required_m','?'):.2f}m "
                        f"[{'OK' if wc.get('pass') else 'FAIL':{4}}]  "
                        f"=> {outcome}"
                    )
                    self.stdout.write(outcome_style(line))

        if result.placement_audit:
            self.stdout.write("\nSpacing audit:")
            for entry in result.placement_audit:
                line = (
                    f"  Pair {entry['pair']}: "
                    f"gap={entry['gap_m']:.3f} m  "
                    f"required={entry['required_m']:.3f} m  "
                    f"[{entry['status']}]  "
                    f"{entry['gdcr_clause']}"
                )
                if entry["status"] == "PASS":
                    self.stdout.write(self.style.SUCCESS(line))
                else:
                    self.stdout.write(self.style.ERROR(line))

        self.stdout.write("-" * 60)

    def _export_geojson(
        self,
        result:       PlacementResult,
        envelope_wkt: str,
        export_dir:   str,
        envelope_id:  int,
    ):
        from shapely.wkt import loads as shapely_loads
        from placement_engine.geometry.spacing_enforcer import (
            compute_exclusion_zone,
        )

        Path(export_dir).mkdir(parents=True, exist_ok=True)
        prefix = f"placement_env{envelope_id}_H{result.building_height_m:.0f}m"

        # Layer: envelope
        env_poly = shapely_loads(envelope_wkt)
        self._write_geojson(
            os.path.join(export_dir, f"{prefix}_envelope.geojson"),
            [{"type": "Feature",
              "geometry": self._shapely_to_geojson_geom(env_poly),
              "properties": {"layer": "envelope", "area_sqft": round(env_poly.area, 2)}}]
        )

        features: list[dict] = []

        # Layer: footprints + exclusion zones
        for i, fp in enumerate(result.footprints):
            # footprint
            features.append({
                "type": "Feature",
                "geometry": self._shapely_to_geojson_geom(fp.footprint_polygon),
                "properties": {
                    "layer":              f"footprint_{i}",
                    "tower_index":        i,
                    "area_sqft":          round(fp.area_sqft, 2),
                    "width_m":            round(fp.width_m, 3),
                    "depth_m":            round(fp.depth_m, 3),
                    "orientation_label":  fp.orientation_label,
                    "orientation_deg":    round(fp.orientation_angle_deg, 4),
                    "grid_res_dxf":       round(fp.grid_resolution_dxf, 4),
                    "component_index":    fp.source_component_index,
                },
            })

            # exclusion zone
            excl = compute_exclusion_zone(fp.footprint_polygon, result.building_height_m)
            features.append({
                "type": "Feature",
                "geometry": self._shapely_to_geojson_geom(excl),
                "properties": {
                    "layer":          f"exclusion_zone_{i}",
                    "tower_index":    i,
                    "spacing_req_m":  round(result.spacing_required_m, 3),
                    "spacing_req_dxf": round(result.spacing_required_dxf, 3),
                },
            })

        out_path = os.path.join(export_dir, f"{prefix}_footprints.geojson")
        self._write_geojson(out_path, features)
        self.stdout.write(self.style.SUCCESS(f"\nGeoJSON exported to: {export_dir}/"))

    def _shapely_to_geojson_geom(self, geom) -> dict:
        """Convert a Shapely geometry to a GeoJSON geometry dict."""
        import json
        return json.loads(_shapely_geom_to_geojson(geom))

    def _write_geojson(self, path: str, features: list[dict]):
        fc = {"type": "FeatureCollection", "features": features}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(fc, fh, indent=2)
        self.stdout.write(f"  Written: {path}")


# ── Standalone GeoJSON geometry converter ─────────────────────────────────────

def _shapely_geom_to_geojson(geom) -> str:
    """Convert a Shapely geometry to a GeoJSON geometry JSON string."""
    import json
    from shapely.geometry import mapping
    return json.dumps(mapping(geom))
