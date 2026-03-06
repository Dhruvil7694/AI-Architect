from __future__ import annotations

"""
Unit tests for architecture.regulatory.height_solver.

These tests focus on the high-level behaviour and invariants of the solver.
They do not attempt to cover every geometric edge case.
"""

from dataclasses import asdict
from math import isclose
from unittest import mock

from django.test import TestCase

from architecture.regulatory.height_solver import (
    HeightSolution,
    solve_max_legal_height,
)


class HeightSolverTests(TestCase):
    def test_height_solution_dataclass_round_trip(self):
        """HeightSolution should be serialisable via asdict without loss."""
        sol = HeightSolution(
            max_height_m=16.5,
            controlling_constraint="ROAD_WIDTH_CAP",
            floors=5,
            footprint_area_sqft=1000.0,
            achieved_fsi=1.5,
            fsi_utilization_pct=55.55,
            gc_utilization_pct=35.0,
            spacing_required_m=5.0,
            spacing_provided_m=None,
        )
        d = asdict(sol)
        self.assertEqual(d["max_height_m"], 16.5)
        self.assertEqual(d["controlling_constraint"], "ROAD_WIDTH_CAP")
        self.assertEqual(d["floors"], 5)

    @mock.patch("architecture.regulatory.height_solver._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.height_solver.evaluate_all")
    @mock.patch("architecture.regulatory.height_solver.compute_placement")
    @mock.patch("architecture.regulatory.height_solver.compute_envelope")
    @mock.patch("architecture.regulatory.height_solver.get_max_ground_coverage_pct")
    @mock.patch("architecture.regulatory.height_solver.get_max_fsi")
    @mock.patch("architecture.regulatory.height_solver.get_max_permissible_height_by_road_width")
    def test_height_never_exceeds_road_cap(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_compute_envelope,
        mock_compute_placement,
        mock_evaluate_all,
        mock_is_layout_viable,
    ):
        """
        Solver must never return a height above the GDCR road-width cap.

        This test uses minimal stubs for envelope/placement and rules to
        exercise the binary search without real geometry.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from rules_engine.rules.base import RuleResult, PASS

        # Road cap at 30.0 m
        mock_get_h_road.return_value = 30.0
        mock_get_max_fsi.return_value = 10.0  # effectively non-limiting FSI
        mock_get_max_gc.return_value = 100.0  # GC never limiting

        # Simple square plot and envelope
        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="1",
            area_excel=100.0,
            area_geometry=100.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        class DummyEnv:
            status = "VALID"
            envelope_polygon = plot_geom
            envelope_area_sqft = 100.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        mock_compute_envelope.return_value = DummyEnv()

        class DummyFP:
            width_m = 10.0
            depth_m = 10.0
            area_sqft = 100.0

        class DummyPlacement:
            status = "VALID"
            footprints = [DummyFP()]
            spacing_required_m = 0.0
            placement_audit = []
            per_tower_core_validation = []

        mock_compute_placement.return_value = DummyPlacement()

        # All rules PASS
        mock_evaluate_all.return_value = [
            RuleResult(
                rule_id="gdcr.fsi.base",
                source="GDCR",
                category="fsi",
                description="",
                status=PASS,
                required_value=None,
                actual_value=None,
            )
        ]

        sol = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertLessEqual(sol.max_height_m, 30.0 + 1e-6)
        # Post-solver reduces to floor multiples; legal max may be e.g. 29.97 → 27 m, so LAYOUT_LIMIT possible
        self.assertIn(sol.controlling_constraint, ("ROAD_WIDTH_CAP", "LAYOUT_LIMIT"))
        self.assertGreater(sol.max_height_m, 0.0)

    @mock.patch("architecture.regulatory.height_solver._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.height_solver.evaluate_all")
    @mock.patch("architecture.regulatory.height_solver.compute_placement")
    @mock.patch("architecture.regulatory.height_solver.compute_envelope")
    @mock.patch("architecture.regulatory.height_solver.get_max_ground_coverage_pct")
    @mock.patch("architecture.regulatory.height_solver.get_max_fsi")
    @mock.patch("architecture.regulatory.height_solver.get_max_permissible_height_by_road_width")
    def test_fsi_can_limit_height(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_compute_envelope,
        mock_compute_placement,
        mock_evaluate_all,
        mock_is_layout_viable,
    ):
        """
        When FSI is restrictive but allows at least one floor, the solver
        should be limited by FSI (height well below road cap).
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from rules_engine.rules.base import RuleResult, PASS

        mock_get_h_road.return_value = 70.0  # high cap from road
        mock_get_max_fsi.return_value = 0.5  # low max FSI
        mock_get_max_gc.return_value = 100.0

        # Plot 1000 sqft → allowed_bua = 500. Footprint 250 → max 2 floors (6 m) so binary search converges with floors >= 1.
        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="2",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        class DummyEnv:
            status = "VALID"
            envelope_polygon = plot_geom
            envelope_area_sqft = 1000.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        mock_compute_envelope.return_value = DummyEnv()

        class DummyFP:
            width_m = 10.0
            depth_m = 10.0
            area_sqft = 250.0  # 500/250 = 2 floors max → FSI caps height at ~6 m

        class DummyPlacement:
            status = "VALID"
            footprints = [DummyFP()]
            spacing_required_m = 0.0
            placement_audit = []
            per_tower_core_validation = []

        mock_compute_placement.return_value = DummyPlacement()

        mock_evaluate_all.return_value = [
            RuleResult(
                rule_id="gdcr.fsi.base",
                source="GDCR",
                category="fsi",
                description="",
                status=PASS,
                required_value=None,
                actual_value=None,
            )
        ]

        sol = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        # Road cap is high; solution should be well below it and attributed to FSI/geometry.
        self.assertLess(sol.max_height_m, 70.0)
        self.assertGreater(sol.max_height_m, 0.0)

    @mock.patch("architecture.regulatory.height_solver.evaluate_all")
    @mock.patch("architecture.regulatory.height_solver.compute_placement")
    @mock.patch("architecture.regulatory.height_solver.compute_envelope")
    @mock.patch("architecture.regulatory.height_solver.get_max_ground_coverage_pct")
    @mock.patch("architecture.regulatory.height_solver.get_max_fsi")
    @mock.patch("architecture.regulatory.height_solver.get_max_permissible_height_by_road_width")
    def test_zero_height_when_allowed_bua_less_than_footprint(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_compute_envelope,
        mock_compute_placement,
        mock_evaluate_all,
    ):
        """
        When allowed_bua < footprint_area, max_floors_fsi = 0 → any positive height
        is FSI-infeasible. Solver must return max_height_m = 0 and INFEASIBLE.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from rules_engine.rules.base import RuleResult, PASS

        mock_get_h_road.return_value = 30.0
        # Plot 1000 sqft, max_fsi 0.2 → allowed_bua = 200. Footprint 500 → 200/500 = 0 floors.
        mock_get_max_fsi.return_value = 0.2
        mock_get_max_gc.return_value = 100.0

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="3",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 12.0

        class DummyEnv:
            status = "VALID"
            envelope_polygon = plot_geom
            envelope_area_sqft = 1000.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        mock_compute_envelope.return_value = DummyEnv()

        class DummyFP:
            width_m = 10.0
            depth_m = 10.0
            area_sqft = 500.0  # allowed_bua = 200 < 500 → max_floors_fsi = 0

        class DummyPlacement:
            status = "VALID"
            footprints = [DummyFP()]
            spacing_required_m = 0.0
            placement_audit = []
            per_tower_core_validation = []

        mock_compute_placement.return_value = DummyPlacement()
        mock_evaluate_all.return_value = [
            RuleResult(
                rule_id="gdcr.fsi.base",
                source="GDCR",
                category="fsi",
                description="",
                status=PASS,
                required_value=None,
                actual_value=None,
            )
        ]

        sol = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertEqual(sol.max_height_m, 0.0)
        self.assertEqual(sol.controlling_constraint, "INFEASIBLE")
        self.assertEqual(sol.floors, 0)

    @mock.patch("architecture.regulatory.height_solver._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.height_solver.evaluate_all")
    @mock.patch("architecture.regulatory.height_solver.compute_placement")
    @mock.patch("architecture.regulatory.height_solver.compute_envelope")
    @mock.patch("architecture.regulatory.height_solver.get_max_ground_coverage_pct")
    @mock.patch("architecture.regulatory.height_solver.get_max_fsi")
    @mock.patch("architecture.regulatory.height_solver.get_max_permissible_height_by_road_width")
    def test_discrete_margin_threshold_caps_height(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_compute_envelope,
        mock_compute_placement,
        mock_evaluate_all,
        mock_is_layout_viable,
    ):
        """
        When envelope validity depends on height (e.g. margin step at 15 m),
        solver must not exceed the height at which envelope first fails.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from rules_engine.rules.base import RuleResult, PASS

        mock_get_h_road.return_value = 30.0
        mock_get_max_fsi.return_value = 3.0
        mock_get_max_gc.return_value = 100.0

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="4",
            area_excel=100.0,
            area_geometry=100.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        class DummyEnv:
            status = "VALID"
            envelope_polygon = plot_geom
            envelope_area_sqft = 100.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        class InvalidEnv:
            status = "COLLAPSED"
            envelope_polygon = None
            envelope_area_sqft = None
            ground_coverage_pct = None
            common_plot_area_sqft = None
            edge_margin_audit = []

        def envelope_side_effect(plot_wkt, building_height, road_width, road_facing_edges, enforce_gc=True):
            # Simulate discrete margin: valid only when height <= 15 m
            if building_height <= 15.0:
                return DummyEnv()
            return InvalidEnv()

        mock_compute_envelope.side_effect = envelope_side_effect

        class DummyFP:
            width_m = 10.0
            depth_m = 10.0
            area_sqft = 100.0

        class DummyPlacement:
            status = "VALID"
            footprints = [DummyFP()]
            spacing_required_m = 0.0
            placement_audit = []
            per_tower_core_validation = []

        mock_compute_placement.return_value = DummyPlacement()
        mock_evaluate_all.return_value = [
            RuleResult(
                rule_id="gdcr.fsi.base",
                source="GDCR",
                category="fsi",
                description="",
                status=PASS,
                required_value=None,
                actual_value=None,
            )
        ]

        sol = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        # Must not exceed the threshold where envelope becomes invalid
        self.assertLessEqual(sol.max_height_m, 15.0 + 0.02)  # tolerance from binary search
        self.assertGreater(sol.max_height_m, 0.0)

    @mock.patch("architecture.regulatory.height_solver._is_layout_viable")
    @mock.patch("architecture.regulatory.height_solver.evaluate_all")
    @mock.patch("architecture.regulatory.height_solver.compute_placement")
    @mock.patch("architecture.regulatory.height_solver.compute_envelope")
    @mock.patch("architecture.regulatory.height_solver.get_max_ground_coverage_pct")
    @mock.patch("architecture.regulatory.height_solver.get_max_fsi")
    @mock.patch("architecture.regulatory.height_solver.get_max_permissible_height_by_road_width")
    def test_layout_infeasible_reduces_height(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_compute_envelope,
        mock_compute_placement,
        mock_evaluate_all,
        mock_is_layout_viable,
    ):
        """
        Legal height = 30 m, storey_height = 3 m; layout viable only for floors <= 5.
        Expect final height = 15 m and controlling_constraint = LAYOUT_LIMIT.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from rules_engine.rules.base import RuleResult, PASS

        mock_get_h_road.return_value = 30.0
        mock_get_max_fsi.return_value = 10.0
        mock_get_max_gc.return_value = 100.0

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="layout1",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        class DummyEnv:
            status = "VALID"
            envelope_polygon = plot_geom
            envelope_area_sqft = 1000.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        mock_compute_envelope.return_value = DummyEnv()

        class DummyFP:
            width_m = 10.0
            depth_m = 10.0
            area_sqft = 200.0

        class DummyPlacement:
            status = "VALID"
            footprints = [DummyFP()]
            spacing_required_m = 0.0
            placement_audit = []
            per_tower_core_validation = []

        mock_compute_placement.return_value = DummyPlacement()
        mock_evaluate_all.return_value = [
            RuleResult(
                rule_id="gdcr.fsi.base",
                source="GDCR",
                category="fsi",
                description="",
                status=PASS,
                required_value=None,
                actual_value=None,
            )
        ]

        # Layout viable only when height_m <= 15 (floors <= 5)
        def layout_viable(plot, height_m, placement_ctx, storey_height_m):
            from math import floor
            floors = floor(height_m / storey_height_m)
            return floors <= 5

        mock_is_layout_viable.side_effect = layout_viable

        sol = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertAlmostEqual(sol.max_height_m, 15.0, delta=0.02)
        self.assertEqual(sol.controlling_constraint, "LAYOUT_LIMIT")
        self.assertEqual(sol.floors, 5)

    @mock.patch("architecture.regulatory.height_solver._is_layout_viable", return_value=False)
    @mock.patch("architecture.regulatory.height_solver.evaluate_all")
    @mock.patch("architecture.regulatory.height_solver.compute_placement")
    @mock.patch("architecture.regulatory.height_solver.compute_envelope")
    @mock.patch("architecture.regulatory.height_solver.get_max_ground_coverage_pct")
    @mock.patch("architecture.regulatory.height_solver.get_max_fsi")
    @mock.patch("architecture.regulatory.height_solver.get_max_permissible_height_by_road_width")
    def test_layout_failure_returns_zero(
        self,
        mock_get_h_road,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_compute_envelope,
        mock_compute_placement,
        mock_evaluate_all,
        mock_is_layout_viable,
    ):
        """
        Legal height > 0 but layout always fails. Expect max_height_m = 0.0,
        controlling_constraint = LAYOUT_INFEASIBLE.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from rules_engine.rules.base import RuleResult, PASS

        mock_get_h_road.return_value = 30.0
        mock_get_max_fsi.return_value = 10.0
        mock_get_max_gc.return_value = 100.0

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="layout2",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        class DummyEnv:
            status = "VALID"
            envelope_polygon = plot_geom
            envelope_area_sqft = 1000.0
            ground_coverage_pct = 10.0
            common_plot_area_sqft = 0.0
            edge_margin_audit = []

        mock_compute_envelope.return_value = DummyEnv()

        class DummyFP:
            width_m = 10.0
            depth_m = 10.0
            area_sqft = 200.0

        class DummyPlacement:
            status = "VALID"
            footprints = [DummyFP()]
            spacing_required_m = 0.0
            placement_audit = []
            per_tower_core_validation = []

        mock_compute_placement.return_value = DummyPlacement()
        mock_evaluate_all.return_value = [
            RuleResult(
                rule_id="gdcr.fsi.base",
                source="GDCR",
                category="fsi",
                description="",
                status=PASS,
                required_value=None,
                actual_value=None,
            )
        ]

        sol = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertEqual(sol.max_height_m, 0.0)
        self.assertEqual(sol.controlling_constraint, "LAYOUT_INFEASIBLE")
        self.assertEqual(sol.floors, 0)

