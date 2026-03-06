from __future__ import annotations

"""
Unit tests for architecture.regulatory.development_optimizer.

These tests focus on optimiser behaviour (multi-tower placement iteration,
FSI comparison, and controlling constraint attribution) using mocks.
"""

from unittest import mock

from django.test import TestCase

from architecture.regulatory.development_optimizer import (
    OptimalDevelopmentSolution,
    solve_optimal_development_configuration,
)


class DevelopmentOptimizerTests(TestCase):
    def test_infeasible_when_no_road_width(self):
        """If road width is missing/non-positive, optimiser returns INFEASIBLE."""
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="dev0",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 0.0

        sol = solve_optimal_development_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertEqual(sol.n_towers, 0)
        self.assertEqual(sol.floors, 0)
        self.assertEqual(sol.controlling_constraint, "INFEASIBLE")

    @mock.patch("architecture.regulatory.development_optimizer._is_layout_viable_for_tower", return_value=True)
    @mock.patch("architecture.regulatory.development_optimizer._is_compliant_via_rules_multi", return_value=True)
    @mock.patch("architecture.regulatory.development_optimizer._build_multi_tower_regulatory_ctx")
    @mock.patch("architecture.regulatory.development_optimizer.compute_placement")
    @mock.patch("architecture.regulatory.development_optimizer.compute_envelope")
    @mock.patch("architecture.regulatory.development_optimizer.detect_road_edges_with_meta")
    @mock.patch("architecture.regulatory.development_optimizer.get_max_ground_coverage_pct", return_value=100.0)
    @mock.patch("architecture.regulatory.development_optimizer.get_max_fsi", return_value=10.0)
    @mock.patch("architecture.regulatory.development_optimizer.get_max_permissible_height_by_road_width", return_value=30.0)
    def test_picks_best_fsi_multi_tower(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_detect_edges,
        mock_compute_envelope,
        mock_compute_placement,
        mock_build_ctx,
        mock_rules_ok,
        mock_layout_ok,
    ):
        """
        Optimiser should explore multiple tower counts and pick the configuration
        with the highest achieved FSI.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon

        # Road edges detection: dummy
        mock_detect_edges.return_value = (["EDGE0"], False)

        class DummyEnv:
            status = "VALID"
            envelope_polygon = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
            envelope_area_sqft = 1000.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        mock_compute_envelope.return_value = DummyEnv()

        class DummyFP:
            def __init__(self, area_sqft):
                self.width_m = 10.0
                self.depth_m = 10.0
                self.area_sqft = area_sqft

        class DummyPlacement:
            def __init__(self, n_towers, area_per_tower):
                self.status = "VALID"
                self.footprints = [DummyFP(area_per_tower) for _ in range(n_towers)]
                self.spacing_required_m = 0.0
                self.placement_audit = []
                self.per_tower_core_validation = []

        # For n_towers=1 and 2, placement is VALID; for 3, becomes INVALID.
        def placement_side_effect(envelope_wkt, building_height_m, n_towers, min_width_m, min_depth_m):
            if n_towers == 1:
                return DummyPlacement(1, 300.0)
            if n_towers == 2:
                return DummyPlacement(2, 250.0)
            class InvalidPlacement:
                status = "INVALID"
            return InvalidPlacement()

        mock_compute_placement.side_effect = placement_side_effect

        class DummyReg:
            def __init__(self, fsi, util_pct, gc_pct):
                self.achieved_fsi = fsi
                self.fsi_utilization_pct = util_pct
                self.achieved_gc_pct = gc_pct

        # Build ctx so that 2 towers yields higher FSI than 1 tower at the same floors.
        def build_ctx_side_effect(plot, height_m, floors, env, placement):
            n_towers = len(placement.footprints)
            if n_towers == 1:
                reg = DummyReg(fsi=1.0, util_pct=50.0, gc_pct=30.0)
            else:
                reg = DummyReg(fsi=1.5, util_pct=75.0, gc_pct=35.0)
            ctx = {
                "height_m": height_m,
                "floors": floors,
                "total_footprint_area_sqft": sum(fp.area_sqft for fp in placement.footprints),
                "regulatory": reg,
                "envelope": env,
                "placement": placement,
                "spacing_required_m": 0.0,
                "spacing_provided_m": 0.0,
            }
            return True, ctx

        mock_build_ctx.side_effect = build_ctx_side_effect

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="dev1",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        sol = solve_optimal_development_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        # Should pick the 2-tower configuration with higher achieved FSI.
        self.assertEqual(sol.n_towers, 2)
        self.assertGreater(sol.achieved_fsi, 1.0)

