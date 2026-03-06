from __future__ import annotations

"""
simulate_optimal_development
----------------------------

Management command to run the deterministic multi-tower development optimiser
for a single TP/FP plot under GDCR constraints.

This command is additive and does not modify existing CLI behaviour.
"""

import json
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot

from architecture.regulatory.development_optimizer import (
    evaluate_development_configuration,
)


class Command(BaseCommand):
    help = (
        "Simulate the optimal multi-tower development configuration for a TP/FP plot "
        "using the deterministic development optimiser (uniform height, fixed storey "
        "height across towers). Outputs a JSON summary of the "
        "OptimalDevelopmentSolution."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, required=True, help="TP scheme number (e.g. 14)")
        parser.add_argument("--fp", type=int, required=True, help="FP number (e.g. 127)")
        parser.add_argument(
            "--storey-height",
            type=float,
            default=3.0,
            help="Storey height in metres (default: 3.0)",
        )
        parser.add_argument(
            "--min-width",
            type=float,
            default=5.0,
            help="Minimum footprint width in metres (default: 5.0)",
        )
        parser.add_argument(
            "--min-depth",
            type=float,
            default=3.5,
            help="Minimum footprint depth in metres (default: 3.5)",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable verbose per-candidate optimiser diagnostics (FSI, envelope, placement, rules, layout).",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        fp = options["fp"]
        storey_height = options.get("storey_height") or 3.0
        min_width = options.get("min_width") or 5.0
        min_depth = options.get("min_depth") or 3.5
        debug = bool(options.get("debug"))

        try:
            plot = Plot.objects.get(tp_scheme=f"TP{tp}", fp_number=str(fp))
        except Plot.DoesNotExist:
            raise CommandError(f"Plot not found: TP{tp} FP{fp}")

        solution = evaluate_development_configuration(
            plot=plot,
            storey_height_m=storey_height,
            min_width_m=min_width,
            min_depth_m=min_depth,
            mode="development",
            debug=debug,
        )

        payload = asdict(solution)
        self.stdout.write(json.dumps(payload, indent=2))

