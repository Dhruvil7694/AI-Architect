from __future__ import annotations

"""
simulate_max_height
-------------------

Management command to run the deterministic maximum legal height solver
for a single TP/FP plot under GDCR constraints.

This command is additive and does not modify existing CLI behaviour.
"""

import json

from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot

from architecture.regulatory.height_solver import solve_max_legal_height


class Command(BaseCommand):
    help = (
        "Simulate the maximum GDCR-compliant building height for a TP/FP plot "
        "using the deterministic height solver (single-tower scenario). "
        "Outputs a JSON summary of the HeightSolution."
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
            "--height-cap",
            type=float,
            default=None,
            help="Optional explicit upper bound on building height (m). "
                 "Solver will respect the lower of this and the GDCR road-width cap.",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        fp = options["fp"]
        storey_height = options.get("storey_height") or 3.0
        min_width = options.get("min_width") or 5.0
        min_depth = options.get("min_depth") or 3.5
        height_cap = options.get("height_cap")

        try:
            plot = Plot.objects.get(tp_scheme=f"TP{tp}", fp_number=str(fp))
        except Plot.DoesNotExist:
            raise CommandError(f"Plot not found: TP{tp} FP{fp}")

        solution = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=height_cap,
            storey_height_m=storey_height,
            min_width_m=min_width,
            min_depth_m=min_depth,
        )

        payload = asdict(solution)
        self.stdout.write(json.dumps(payload, indent=2))

