from __future__ import annotations

"""
Integration test that runs the full development pipeline for a real Plot
and validates site-level planning metrics (BUA, FSI, GC, footprint).

This test must not mock anything and is intended as a Phase 2 gatekeeper.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase

from tp_ingestion.models import Plot
from architecture.services.development_pipeline import (
    generate_optimal_development_floor_plans,
)
from compliance.gdcr_config import load_gdcr_config


class TestSitePlanningRealPlot(TestCase):
    def test_site_planning_metrics_consistency_for_real_plot(self) -> None:
        """
        Fetch a real Plot from the DB, run the full development pipeline,
        and assert mathematical consistency of site-level planning metrics.
        """
        plot = Plot.objects.first()
        if plot is None:
            self.fail(
                "No Plot instances available in DB for site planning integration test. "
                "Load at least one FP (Plot) before running this test."
            )

        plot_area_sqm = float(plot.plot_area_sqm)

        # Run the full development pipeline (no mocks).
        result = generate_optimal_development_floor_plans(
            plot=plot,
            include_building_layout=True,
            strict=True,
        )

        # Status must be OK; otherwise fail with detailed diagnostics.
        if result.status != "OK":
            self.fail(
                "Development pipeline did not complete successfully for Plot "
                f"id={getattr(plot, 'id', None)}. "
                f"Status={result.status}, "
                f"reason={result.failure_reason}, "
                f"details={result.failure_details}"
            )

        # Site-level parameters from result.
        n_towers = int(result.n_towers)
        floors = int(result.floors)
        height_m = float(result.height_m)
        achieved_fsi = float(result.achieved_fsi)
        total_bua_sqft = float(result.total_bua_sqft)
        gc_utilization_pct = float(result.gc_utilization_pct)

        placement = result.placement_summary
        self.assertIsNotNone(
            placement, "Placement summary must be present for successful pipeline run."
        )

        per_tower_footprints_sqft = list(placement.per_tower_footprint_sqft or [])

        # Aggregate footprint and BUA in sqm.
        total_footprint_sqft = sum(per_tower_footprints_sqft)
        total_footprint_sqm = total_footprint_sqft * 0.092903
        total_bua_sqm = total_bua_sqft * 0.092903

        # Load GDCR configuration from YAML via existing loader.
        yaml_path: Path = settings.BASE_DIR.parent / "GDCR.yaml"
        gdcr = load_gdcr_config(yaml_path)

        max_fsi = float(gdcr.fsi_rules.maximum_fsi)
        allowed_bua_sqm = max_fsi * plot_area_sqm if plot_area_sqm > 0 else 0.0
        fsi_utilization_ratio = (
            total_bua_sqm / allowed_bua_sqm if allowed_bua_sqm > 0 else 0.0
        )

        # A) Footprint aggregation.
        self.assertGreater(total_footprint_sqm, 0.0)
        self.assertEqual(
            len(per_tower_footprints_sqft),
            n_towers,
            msg="Number of footprint entries must match n_towers.",
        )

        # B) BUA consistency (geometry vs. reported total).
        expected_bua_sqm = total_footprint_sqm * floors
        self.assertAlmostEqual(
            total_bua_sqm,
            expected_bua_sqm,
            places=2,
            msg="Total BUA must equal footprint × floors.",
        )

        # C) FSI constraint (BUA must not exceed allowed FSI cap).
        if allowed_bua_sqm > 0:
            self.assertLessEqual(
                total_bua_sqm,
                allowed_bua_sqm + 1e-6,
                msg="BUA exceeds allowed FSI.",
            )

        # D) Ground coverage (GC) constraint, if configured.
        max_gc_pct = gdcr.parking_rules.max_ground_coverage_pct_dw3
        if max_gc_pct is not None and plot_area_sqm > 0:
            gc_ratio = total_footprint_sqm / plot_area_sqm
            self.assertLessEqual(
                gc_ratio,
                (max_gc_pct / 100.0) + 1e-6,
                msg="Ground coverage exceeds permitted limit.",
            )

        # E) Spacing check (only if spacing values are available).
        if (
            getattr(placement, "spacing_required_m", None) is not None
            and getattr(placement, "spacing_provided_m", None) is not None
        ):
            self.assertGreaterEqual(
                placement.spacing_provided_m or 0.0,
                placement.spacing_required_m or 0.0,
                msg="Tower spacing insufficient.",
            )

        # Diagnostic summary for manual audit.
        print("----- SITE PLANNING DEBUG -----")
        print(f"Plot Area (sqm): {plot_area_sqm}")
        print(f"Towers: {n_towers}")
        print(f"Floors: {floors}")
        print(f"Height (m): {height_m}")
        print(f"Total Footprint (sqm): {total_footprint_sqm}")
        print(f"Total BUA (sqm): {total_bua_sqm}")
        print(f"Allowed BUA (sqm): {allowed_bua_sqm}")
        print(f"FSI Utilization: {fsi_utilization_ratio:.4f}")
        print(f"GC Utilization %: {gc_utilization_pct}")
        print("--------------------------------")

