"""
architecture/management/commands/site_planning_real_plot.py
-----------------------------------------------------------
Run the full development pipeline for a real Plot from the
live PostGIS database and validate site-level planning metrics
without using Django's TestCase/test database isolation.

Usage:
  python manage.py site_planning_real_plot
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot
from architecture.services.development_pipeline import (
    generate_optimal_development_floor_plans,
)
from compliance.gdcr_config import load_gdcr_config


class Command(BaseCommand):
    help = (
        "Run the development pipeline for the first real Plot in the live DB "
        "and validate site-level planning metrics (BUA, FSI, GC, footprint)."
    )

    def handle(self, *args, **options):
        # 1) Fetch a real Plot from the live database.
        plot = Plot.objects.first()
        if plot is None:
            raise CommandError(
                "No Plot instances available in the live DB. "
                "Ingest at least one FP (Plot) before running this command."
            )

        plot_area_sqm = float(plot.plot_area_sqm)

        # 2) Run full development pipeline (no mocks).
        result = generate_optimal_development_floor_plans(
            plot=plot,
            include_building_layout=True,
            strict=True,
        )

        if result.status != "OK":
            raise CommandError(
                "Development pipeline did not complete successfully for Plot "
                f"id={getattr(plot, 'id', None)}. "
                f"Status={result.status}, "
                f"reason={result.failure_reason}, "
                f"details={result.failure_details}"
            )

        # 3) Extract site-level parameters.
        n_towers = int(result.n_towers)
        floors = int(result.floors)
        height_m = float(result.height_m)
        achieved_fsi = float(result.achieved_fsi)
        total_bua_sqft = float(result.total_bua_sqft)
        gc_utilization_pct = float(result.gc_utilization_pct)

        placement = result.placement_summary
        if placement is None:
            raise CommandError("Placement summary is missing for successful pipeline run.")

        per_tower_footprints_sqft = list(placement.per_tower_footprint_sqft or [])

        total_footprint_sqft = sum(per_tower_footprints_sqft)
        total_footprint_sqm = total_footprint_sqft * 0.092903
        total_bua_sqm = total_bua_sqft * 0.092903

        # 4) Compute allowed BUA from FSI (load from GDCR.yaml via existing loader).
        yaml_path: Path = settings.BASE_DIR.parent / "GDCR.yaml"
        gdcr = load_gdcr_config(yaml_path)

        max_fsi = float(gdcr.fsi_rules.maximum_fsi)
        allowed_bua_sqm = max_fsi * plot_area_sqm if plot_area_sqm > 0 else 0.0
        fsi_utilization_ratio = (
            total_bua_sqm / allowed_bua_sqm if allowed_bua_sqm > 0 else 0.0
        )

        # 5) Assert mathematical consistency (raise CommandError on any violation).

        # A) Footprint aggregation.
        if not (total_footprint_sqm > 0.0):
            raise CommandError("Total footprint must be positive.")
        if len(per_tower_footprints_sqft) != n_towers:
            raise CommandError(
                "Number of footprint entries must match n_towers "
                f"(have {len(per_tower_footprints_sqft)}, expected {n_towers})."
            )

        # B) BUA consistency: geometry-based BUA vs reported total.
        expected_bua_sqm = total_footprint_sqm * floors
        if round(total_bua_sqm, 2) != round(expected_bua_sqm, 2):
            raise CommandError(
                "Total BUA must equal footprint × floors. "
                f"got={total_bua_sqm:.2f} sqm, expected={expected_bua_sqm:.2f} sqm."
            )

        # C) FSI constraint.
        if allowed_bua_sqm > 0 and total_bua_sqm > allowed_bua_sqm + 1e-6:
            raise CommandError(
                "BUA exceeds allowed FSI. "
                f"total_bua_sqm={total_bua_sqm:.2f}, allowed_bua_sqm={allowed_bua_sqm:.2f}."
            )

        # D) Ground coverage (GC) constraint, if configured.
        max_gc_pct = gdcr.parking_rules.max_ground_coverage_pct_dw3
        if max_gc_pct is not None and plot_area_sqm > 0:
            gc_ratio = total_footprint_sqm / plot_area_sqm
            if gc_ratio > (max_gc_pct / 100.0) + 1e-6:
                raise CommandError(
                    "Ground coverage exceeds permitted limit. "
                    f"gc_ratio={gc_ratio:.4f}, max_gc={max_gc_pct:.2f}%."
                )

        # E) Spacing check (if spacing values are available).
        spacing_required = getattr(placement, "spacing_required_m", None)
        spacing_provided = getattr(placement, "spacing_provided_m", None)
        if spacing_required is not None and spacing_provided is not None:
            if (spacing_provided or 0.0) < (spacing_required or 0.0) - 1e-6:
                raise CommandError(
                    "Tower spacing insufficient. "
                    f"required={spacing_required}, provided={spacing_provided}."
                )

        # 6) Print debug summary for audit.
        self.stdout.write("----- SITE PLANNING DEBUG -----")
        self.stdout.write(f"Plot Area (sqm): {plot_area_sqm}")
        self.stdout.write(f"Towers: {n_towers}")
        self.stdout.write(f"Floors: {floors}")
        self.stdout.write(f"Height (m): {height_m}")
        self.stdout.write(f"Achieved FSI: {achieved_fsi}")
        self.stdout.write(f"Total Footprint (sqm): {total_footprint_sqm}")
        self.stdout.write(f"Total BUA (sqm): {total_bua_sqm}")
        self.stdout.write(f"Allowed BUA (sqm): {allowed_bua_sqm}")
        self.stdout.write(f"FSI Utilization: {fsi_utilization_ratio:.4f}")
        self.stdout.write(f"GC Utilization %: {gc_utilization_pct}")
        self.stdout.write("--------------------------------")
        self.stdout.write(self.style.SUCCESS("Site planning metrics validation passed."))

