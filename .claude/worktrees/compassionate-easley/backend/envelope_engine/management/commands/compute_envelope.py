"""
management/commands/compute_envelope.py
----------------------------------------
Django management command: compute the legal buildable envelope for a plot.

Usage — minimal
---------------
python manage.py compute_envelope \
    --fp-number 101 \
    --tp-scheme TP14 \
    --city Surat \
    --road-width 12 \
    --building-height 16.5 \
    --road-edges 0

Usage — full
------------
python manage.py compute_envelope \
    --fp-number 101 \
    --tp-scheme TP14 \
    --city Surat \
    --road-width 12 \
    --building-height 16.5 \
    --road-edges 0 \
    --proposal-id 1            link to an existing BuildingProposal (optional)
    --no-gc-enforcement        skip ground coverage clipping
    --save                     persist PlotEnvelope to DB
    --export-geojson           write .geojson file to current directory
    --export-dir output/       directory for GeoJSON files (default: cwd)

Output
------
Prints an ASCII summary table with all margin values and computed areas.
With --export-geojson, writes <fp_number>_<tp_scheme>_envelope.geojson to
the export directory containing all geometry layers as named features.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot


class Command(BaseCommand):
    help = "Compute the GDCR-compliant buildable envelope for a TP/FP plot."

    def add_arguments(self, parser):
        # ── Plot identification ────────────────────────────────────────────────
        g_id = parser.add_argument_group("Plot identification (required)")
        g_id.add_argument("--fp-number",  required=True)
        g_id.add_argument("--tp-scheme",  required=True)
        g_id.add_argument("--city",       required=True)

        # ── Envelope parameters ────────────────────────────────────────────────
        g_env = parser.add_argument_group("Envelope parameters (required)")
        g_env.add_argument(
            "--road-width", type=float, required=True,
            help="Adjacent road width in metres.",
        )
        g_env.add_argument(
            "--building-height", type=float, required=True,
            help="Proposed building height in metres.",
        )
        g_env.add_argument(
            "--road-edges", required=True,
            help=(
                "Comma-separated 0-based edge indices that face a road. "
                "Use `python manage.py inspect_dxf` to identify edge indices. "
                "Example: --road-edges 0  or  --road-edges 0,2 (corner plot)."
            ),
        )

        g_env.add_argument(
            "--cop-strategy",
            type=str,
            default="edge",
            help=(
                "Common open plot placement strategy: 'edge' (rear strip, default) "
                "or 'center' (axis-aligned central rectangle)."
            ),
        )

        # ── Optional linkage ───────────────────────────────────────────────────
        g_opt = parser.add_argument_group("Optional")
        g_opt.add_argument(
            "--proposal-id", type=int,
            help=(
                "ID of an existing BuildingProposal to link the envelope to. "
                "If omitted, the most recent proposal for this plot is used."
            ),
        )
        g_opt.add_argument(
            "--no-gc-enforcement", action="store_true", default=False,
            help="Measure but do not clip to ground coverage limit.",
        )

        # ── Output control ─────────────────────────────────────────────────────
        g_out = parser.add_argument_group("Output")
        g_out.add_argument(
            "--save", action="store_true", default=False,
            help="Persist PlotEnvelope record to DB.",
        )
        g_out.add_argument(
            "--export-geojson", action="store_true", default=False,
            help="Write a GeoJSON file with all geometry layers.",
        )
        g_out.add_argument(
            "--export-dir", type=str, default=".",
            help="Directory for GeoJSON output (default: current directory).",
        )

    def handle(self, *args, **options):
        from envelope_engine.services.envelope_service import (
            compute_envelope,
            save_envelope,
        )

        # ── Parse road edges ───────────────────────────────────────────────────
        try:
            road_facing_edges = [
                int(x.strip())
                for x in options["road_edges"].split(",")
                if x.strip()
            ]
        except ValueError:
            raise CommandError(
                "--road-edges must be a comma-separated list of integers. "
                f"Got: '{options['road_edges']}'"
            )

        # ── Resolve plot ───────────────────────────────────────────────────────
        try:
            plot = Plot.objects.get(
                fp_number=options["fp_number"],
                tp_scheme__iexact=options["tp_scheme"],
                city__iexact=options["city"],
            )
        except Plot.DoesNotExist:
            raise CommandError(
                f"No Plot found for FP {options['fp_number']} / "
                f"{options['tp_scheme']} / {options['city']}. "
                "Run `python manage.py ingest_tp` first."
            )

        self.stdout.write(
            f"  Plot: {plot}  (area_geometry={plot.area_geometry:.1f} sq.ft, "
            f"{len(list(plot.geom.coords[0])) - 1} edges)"
        )

        # ── Validate edge indices ──────────────────────────────────────────────
        num_edges = len(list(plot.geom.coords[0])) - 1
        for idx in road_facing_edges:
            if idx < 0 or idx >= num_edges:
                raise CommandError(
                    f"Edge index {idx} is out of range. "
                    f"Plot has {num_edges} edges (0–{num_edges - 1})."
                )

        # ── Resolve proposal (for --save) ──────────────────────────────────────
        proposal = None
        if options["save"]:
            proposal = self._resolve_proposal(plot, options.get("proposal_id"))
            if proposal is None:
                raise CommandError(
                    "Cannot save without a BuildingProposal. "
                    "Run `python manage.py check_compliance ... --save` first "
                    "or pass --proposal-id."
                )

        # ── Run the pipeline ───────────────────────────────────────────────────
        result = compute_envelope(
            plot_wkt=plot.geom.wkt,
            building_height=options["building_height"],
            road_width=options["road_width"],
            road_facing_edges=road_facing_edges,
            enforce_gc=not options["no_gc_enforcement"],
            cop_strategy=options.get("cop_strategy") or "edge",
        )

        # ── Print report ───────────────────────────────────────────────────────
        self._print_report(result, plot, options)

        # ── Save ───────────────────────────────────────────────────────────────
        if options["save"] and proposal is not None:
            pe = save_envelope(result, proposal)
            self.stdout.write(
                f"\n[saved] PlotEnvelope #{pe.pk} — status={pe.status}"
            )

        # ── Export GeoJSON ─────────────────────────────────────────────────────
        if options["export_geojson"]:
            self._export_geojson(result, plot, options)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_proposal(self, plot, proposal_id):
        from rules_engine.models import BuildingProposal
        if proposal_id:
            try:
                return BuildingProposal.objects.get(pk=proposal_id, plot=plot)
            except BuildingProposal.DoesNotExist:
                return None
        return (
            BuildingProposal.objects.filter(plot=plot)
            .order_by("-created_at")
            .first()
        )

    def _print_report(self, result, plot, options):
        W = 120
        self.stdout.write("\n" + "=" * W)
        self.stdout.write(
            f"  ENVELOPE REPORT — FP {plot.fp_number} | {plot.tp_scheme} | {plot.city}"
        )
        self.stdout.write(
            f"  H={options['building_height']} m  |  Road={options['road_width']} m  "
            f"|  Road-facing edges: {options['road_edges']}"
        )
        self.stdout.write("=" * W)

        # ── Edge margin table ──────────────────────────────────────────────────
        if result.edge_margin_audit:
            self.stdout.write(
                f"\n{'Edge':>5}  {'Type':<5}  {'Road W (m)':>10}  "
                f"{'Margin (m)':>10}  {'Margin (ft)':>11}  {'GDCR Clause':<20}"
            )
            self.stdout.write("-" * 70)
            for e in result.edge_margin_audit:
                rw = f"{e['road_width_m']:.1f}" if e["road_width_m"] else "—"
                self.stdout.write(
                    f"  {e['edge_index']:>3}  {e['edge_type']:<5}  {rw:>10}  "
                    f"  {e['margin_m']:>8.2f}  {e['margin_dxf']:>11.4f}  "
                    f"{e['gdcr_clause']:<20}"
                )

        # ── Result summary ─────────────────────────────────────────────────────
        self.stdout.write("\n" + "-" * W)
        self.stdout.write(f"  Status            : {result.status}")

        if result.status == "VALID":
            self.stdout.write(
                f"  Plot area         : {plot.area_geometry:.1f} sq.ft"
            )
            self.stdout.write(
                f"  Envelope area     : {result.envelope_area_sqft:.1f} sq.ft"
                f"  ({result.envelope_area_sqft / plot.area_geometry * 100:.1f}% of plot)"
            )
            self.stdout.write(
                f"  Ground coverage   : {result.ground_coverage_pct:.1f}%"
                f"  [{result.gc_status}]"
            )
            common_a = result.common_plot_area_sqft or 0.0
            self.stdout.write(
                f"  Common plot       : {common_a:.1f} sq.ft"
                f"  [{result.common_plot_status}]"
            )
        else:
            self.stdout.write(f"  Error             : {result.error_message}")

        self.stdout.write("=" * W + "\n")

    def _export_geojson(self, result, plot, options):
        """Write a GeoJSON FeatureCollection with all geometry layers."""
        export_dir = Path(options["export_dir"])
        export_dir.mkdir(parents=True, exist_ok=True)

        filename = (
            f"{plot.fp_number}_{plot.tp_scheme}_"
            f"H{options['building_height']}_envelope.geojson"
        ).replace(" ", "_")
        filepath = export_dir / filename

        features = []

        # Original plot
        features.append(_geojson_feature(
            plot.geom.wkt, "plot",
            {"fp_number": plot.fp_number, "area_sqft": plot.area_geometry}
        ))

        layer_map = {
            "margin_envelope":  result.margin_polygon,
            "gc_envelope":      result.gc_polygon,
            "final_envelope":   result.envelope_polygon,
            "common_plot":      result.common_plot_polygon,
        }
        for name, poly in layer_map.items():
            if poly is not None and not poly.is_empty:
                features.append(_geojson_feature(
                    poly.wkt, name, {"area_sqft": round(poly.area, 2)}
                ))

        geojson = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::0"}},
            "features": features,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(geojson, f, indent=2)

        self.stdout.write(f"[geojson] Written: {filepath}")


def _geojson_feature(wkt: str, layer_name: str, props: dict) -> dict:
    """Convert a WKT polygon string to a GeoJSON Feature dict."""
    from shapely import wkt as shapely_wkt
    from shapely.geometry import mapping

    poly = shapely_wkt.loads(wkt)
    return {
        "type": "Feature",
        "properties": {"layer": layer_name, **props},
        "geometry": mapping(poly),
    }
