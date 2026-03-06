"""
management/commands/check_compliance.py
----------------------------------------
Django management command that evaluates a building proposal against
all GDCR and NBC rules and prints a formatted compliance report.

Usage (minimal — only mandatory fields)
-----------------------------------------
python manage.py check_compliance \
    --fp-number 101 \
    --tp-scheme TP14 \
    --city Surat \
    --road-width 12 \
    --building-height 16.5 \
    --total-bua 14000 \
    --num-floors 4 \
    --ground-coverage 3500

Full example (with all optional fields)
-----------------------------------------
python manage.py check_compliance \
    --fp-number 101 \
    --tp-scheme TP14 \
    --city Surat \
    --road-width 12 \
    --building-height 16.5 \
    --total-bua 14000 \
    --num-floors 4 \
    --ground-coverage 3500 \
    --has-lift \
    --stair-width 1.2 \
    --tread-mm 275 \
    --riser-mm 175 \
    --stair-headroom 2.4 \
    --side-margin 3.0 \
    --rear-margin 3.0 \
    --num-exits 2 \
    --corridor-width 1.2 \
    --door-width 1.0 \
    --travel-distance 25 \
    --sprinklered \
    --fire-door-rating 120 \
    --has-fire-lift \
    --has-firefighting-shaft \
    --show-na \
    --save

Flags
-----
--dry-run   : evaluate but do NOT save BuildingProposal or ComplianceResult.
--save      : persist BuildingProposal + ComplianceResult to the database.
--show-na   : include NA rows in the printed report.
"""

from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot


class Command(BaseCommand):
    help = "Evaluate GDCR + NBC compliance for a building proposal on a TP/FP plot."

    # ── Argument definitions ──────────────────────────────────────────────────

    def add_arguments(self, parser):
        # Plot identification
        g_plot = parser.add_argument_group("Plot identification (required)")
        g_plot.add_argument("--fp-number",  required=True)
        g_plot.add_argument("--tp-scheme",  required=True)
        g_plot.add_argument("--city",       required=True)

        # Mandatory proposal parameters
        g_mand = parser.add_argument_group("Mandatory proposal parameters")
        g_mand.add_argument("--road-width",       type=float, required=True,
                            help="Adjacent road width in metres.")
        g_mand.add_argument("--building-height",  type=float, required=True,
                            help="Proposed building height in metres.")
        g_mand.add_argument("--total-bua",        type=float, required=True,
                            help="Total built-up area (all floors) in sq.ft.")
        g_mand.add_argument("--num-floors",       type=int, required=True,
                            help="Number of floors above ground.")
        g_mand.add_argument("--ground-coverage",  type=float, required=True,
                            help="Ground floor footprint in sq.ft.")

        # Boolean flags
        g_flag = parser.add_argument_group("Boolean flags")
        g_flag.add_argument("--has-basement",          action="store_true", default=False)
        g_flag.add_argument("--sprinklered",            action="store_true", default=False,
                            help="Building has an automatic sprinkler system.")
        g_flag.add_argument("--has-lift",               action="store_true", default=None)
        g_flag.add_argument("--has-fire-lift",          action="store_true", default=None)
        g_flag.add_argument("--has-firefighting-shaft", action="store_true", default=None)

        # Optional numeric inputs
        g_opt = parser.add_argument_group("Optional numeric inputs")
        g_opt.add_argument("--side-margin",         type=float)
        g_opt.add_argument("--rear-margin",         type=float)
        g_opt.add_argument("--stair-width",         type=float, help="m")
        g_opt.add_argument("--tread-mm",            type=float)
        g_opt.add_argument("--riser-mm",            type=float)
        g_opt.add_argument("--stair-headroom",      type=float, help="m")
        g_opt.add_argument("--window-area",         type=float, help="sq.m")
        g_opt.add_argument("--floor-area",          type=float, help="sq.m of habitable room")
        g_opt.add_argument("--room-height",         type=float, help="m")
        g_opt.add_argument("--bathroom-height",     type=float, help="m")
        g_opt.add_argument("--basement-height",     type=float, help="m")
        g_opt.add_argument("--wall-height-road",    type=float, help="Road-side boundary wall m")
        g_opt.add_argument("--wall-height-other",   type=float, help="Non-road boundary wall m")
        g_opt.add_argument("--num-exits",           type=int)
        g_opt.add_argument("--corridor-width",      type=float, help="m")
        g_opt.add_argument("--door-width",          type=float, help="m")
        g_opt.add_argument("--travel-distance",     type=float, help="m")
        g_opt.add_argument("--fire-separation",     type=float, help="m")
        g_opt.add_argument("--fire-door-rating",    type=float, help="minutes")
        g_opt.add_argument("--refuge-area-pct",     type=float, help="% of floor area")
        g_opt.add_argument("--distance-to-wide-road", type=float,
                           help="Distance in m to nearest 36/45 m road")
        g_opt.add_argument("--notes", type=str, default="")

        # Output / persistence control
        g_out = parser.add_argument_group("Output options")
        g_out.add_argument("--show-na",  action="store_true", default=False,
                           help="Include NA rows in the printed report.")
        g_out.add_argument("--json",     action="store_true", default=False,
                           help="Output results as JSON instead of ASCII table.")
        g_out.add_argument("--save",     action="store_true", default=False,
                           help="Persist BuildingProposal + ComplianceResult to DB.")
        g_out.add_argument("--dry-run",  action="store_true", default=False,
                           help="Evaluate but do not save (overrides --save).")

    # ── Main handler ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        from rules_engine.services.evaluator import build_inputs_from_dict, evaluate_all
        from rules_engine.services.report import as_dict, print_report

        # 1. Resolve the Plot
        try:
            plot = Plot.objects.get(
                fp_number=options["fp_number"],
                tp_scheme__iexact=options["tp_scheme"],
                city__iexact=options["city"],
            )
        except Plot.DoesNotExist:
            raise CommandError(
                f"No validated Plot found for FP {options['fp_number']} "
                f"in scheme {options['tp_scheme']} / city {options['city']}.\n"
                "Run `python manage.py ingest_tp` first to import plot data."
            )

        self.stdout.write(
            f"  Plot found: {plot} (area_geometry={plot.area_geometry:.1f} sq.ft)"
        )

        # 2. Build inputs dict
        params = {
            "road_width":               options["road_width"],
            "building_height":          options["building_height"],
            "total_bua":                options["total_bua"],
            "num_floors":               options["num_floors"],
            "ground_coverage":          options["ground_coverage"],
            "has_basement":             options["has_basement"],
            "is_sprinklered":           options["sprinklered"],
            "has_lift":                 options.get("has_lift"),
            "has_fire_lift":            options.get("has_fire_lift"),
            "has_firefighting_shaft":   options.get("has_firefighting_shaft"),
        }

        # Optional numeric params — only include when provided
        _optional_map = {
            "side_margin":              "side_margin",
            "rear_margin":              "rear_margin",
            "stair_width":              "stair_width",
            "tread_mm":                 "tread_mm",
            "riser_mm":                 "riser_mm",
            "stair_headroom":           "stair_headroom",
            "window_area":              "window_area",
            "floor_area":               "floor_area",
            "room_height":              "room_height",
            "bathroom_height":          "bathroom_height",
            "basement_height":          "basement_height",
            "wall_height_road":         "wall_height_road_side",
            "wall_height_other":        "wall_height_other_side",
            "num_exits":                "num_exits",
            "corridor_width":           "corridor_width",
            "door_width":               "door_width",
            "travel_distance":          "travel_distance",
            "fire_separation":          "fire_separation_distance",
            "fire_door_rating":         "fire_door_rating",
            "refuge_area_pct":          "refuge_area_pct",
            "distance_to_wide_road":    "distance_to_wide_road",
        }
        for cli_key, input_key in _optional_map.items():
            val = options.get(cli_key)
            if val is not None:
                params[input_key] = val

        inputs = build_inputs_from_dict(plot.area_geometry, params)

        # 3. Evaluate
        results = evaluate_all(inputs)

        # 4. Output
        title = (f"FP {plot.fp_number} | {plot.tp_scheme} | {plot.city}  "
                 f"— H={options['building_height']} m, BUA={options['total_bua']} sq.ft")

        if options["json"]:
            print(json.dumps(as_dict(results), indent=2))
        else:
            print_report(results, title=title, show_na=options["show_na"])

        # 5. Persist (if requested and not dry-run)
        if options["save"] and not options["dry_run"]:
            self._persist(plot, options, results)
        elif options["dry_run"]:
            self.stdout.write("\n[dry-run] No records saved.")

    # ── Persistence helper ────────────────────────────────────────────────────

    def _persist(self, plot, options, results):
        from django.db import transaction

        from rules_engine.models import BuildingProposal, ComplianceResult

        with transaction.atomic():
            proposal = BuildingProposal.objects.create(
                plot            = plot,
                road_width      = options["road_width"],
                building_height = options["building_height"],
                total_bua       = options["total_bua"],
                num_floors      = options["num_floors"],
                ground_coverage = options["ground_coverage"],
                has_basement    = options["has_basement"],
                is_sprinklered  = options["sprinklered"],
                has_lift        = options.get("has_lift"),
                side_margin     = options.get("side_margin"),
                rear_margin     = options.get("rear_margin"),
                stair_width     = options.get("stair_width"),
                tread_mm        = options.get("tread_mm"),
                riser_mm        = options.get("riser_mm"),
                stair_headroom  = options.get("stair_headroom"),
                window_area     = options.get("window_area"),
                floor_area      = options.get("floor_area"),
                room_height     = options.get("room_height"),
                bathroom_height = options.get("bathroom_height"),
                basement_height = options.get("basement_height"),
                wall_height_road_side   = options.get("wall_height_road"),
                wall_height_other_side  = options.get("wall_height_other"),
                num_exits               = options.get("num_exits"),
                corridor_width          = options.get("corridor_width"),
                door_width              = options.get("door_width"),
                travel_distance         = options.get("travel_distance"),
                fire_separation_distance = options.get("fire_separation"),
                fire_door_rating         = options.get("fire_door_rating"),
                has_fire_lift            = options.get("has_fire_lift"),
                has_firefighting_shaft   = options.get("has_firefighting_shaft"),
                refuge_area_pct          = options.get("refuge_area_pct"),
                distance_to_wide_road    = options.get("distance_to_wide_road"),
                notes                    = options.get("notes", ""),
            )

            compliance_rows = [
                ComplianceResult(
                    proposal       = proposal,
                    rule_id        = r.rule_id,
                    rule_source    = r.source,
                    category       = r.category,
                    description    = r.description,
                    status         = r.status,
                    required_value = r.required_value,
                    actual_value   = r.actual_value,
                    unit           = r.unit or "",
                    note           = r.note or "",
                )
                for r in results
            ]
            ComplianceResult.objects.bulk_create(compliance_rows, ignore_conflicts=True)

        self.stdout.write(
            f"\n[saved] BuildingProposal #{proposal.pk} + "
            f"{len(compliance_rows)} ComplianceResult rows stored."
        )
