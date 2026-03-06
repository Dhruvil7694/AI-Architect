from __future__ import annotations

"""
Unit tests for architecture.regulatory.fsi_optimizer.

These tests focus on optimiser behaviour (floor iteration, FSI comparison,
and controlling constraint attribution), using mocks for geometry and rules.
"""

from dataclasses import asdict
from unittest import mock

from django.test import TestCase

from architecture.regulatory.fsi_optimizer import (
    OptimalFSISolution,
    solve_optimal_fsi_configuration,
)


class FSIOptimizerTests(TestCase):
    def test_infeasible_plot_returns_zero(self):
        """When max_legal_floors <= 0, optimiser must return an INFEASIBLE zero solution."""
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from architecture.regulatory.height_solver import HeightSolution

        # Patch solve_max_legal_height so that legal height is zero.
        with mock.patch(
            "architecture.regulatory.fsi_optimizer.solve_max_legal_height",
            return_value=HeightSolution(
                max_height_m=0.0,
                controlling_constraint="INFEASIBLE",
                floors=0,
                footprint_area_sqft=0.0,
                achieved_fsi=0.0,
                fsi_utilization_pct=0.0,
                gc_utilization_pct=0.0,
                spacing_required_m=0.0,
                spacing_provided_m=None,
            ),
        ):
            plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
            plot = Plot(
                city="X",
                tp_scheme="TP0",
                fp_number="fsi0",
                area_excel=1000.0,
                area_geometry=1000.0,
                geom=plot_geom,
                validation_status=True,
            )
            plot.road_width_m = 18.0

            sol = solve_optimal_fsi_configuration(
                plot=plot,
                storey_height_m=3.0,
                min_width_m=5.0,
                min_depth_m=3.5,
            )

            self.assertEqual(sol.optimal_height_m, 0.0)
            self.assertEqual(sol.floors, 0)
            self.assertEqual(sol.achieved_fsi, 0.0)
            self.assertEqual(sol.controlling_constraint, "INFEASIBLE")

    @mock.patch("architecture.regulatory.fsi_optimizer._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_compliant_via_rules", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_feasible_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_ground_coverage_pct", return_value=100.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_fsi", return_value=2.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.solve_max_legal_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_permissible_height_by_road_width", return_value=18.0)
    def test_full_fsi_utilization(
        self,
        mock_get_h_road,
        mock_solve_max_height,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_is_feasible_height,
        mock_is_compliant_via_rules,
        mock_is_layout_viable,
    ):
        """
        When a configuration achieves ~100% FSI utilisation, optimiser should
        select it and report controlling_constraint == FSI_MAXED.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from architecture.regulatory.height_solver import HeightSolution

        # Legal height corresponds to 6 floors at 3m each.
        mock_solve_max_height.return_value = HeightSolution(
            max_height_m=18.0,
            controlling_constraint="ROAD_WIDTH_CAP",
            floors=6,
            footprint_area_sqft=500.0,
            achieved_fsi=2.0,
            fsi_utilization_pct=100.0,
            gc_utilization_pct=40.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

        class DummyReg:
            def __init__(self, fsi, util_pct, gc_pct):
                self.achieved_fsi = fsi
                self.fsi_utilization_pct = util_pct
                self.achieved_gc_pct = gc_pct

        # For any height, return a ctx with full FSI utilisation.
        def feasible_side_effect(*args, **kwargs):
            return True, {
                "regulatory": DummyReg(fsi=2.0, util_pct=100.0, gc_pct=40.0),
                "footprint_area_sqft": 500.0,
                "spacing_required_m": 0.0,
                "spacing_provided_m": None,
                "envelope": object(),
                "placement": object(),
            }

        mock_is_feasible_height.side_effect = feasible_side_effect

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="fsi1",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        sol = solve_optimal_fsi_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertAlmostEqual(sol.optimal_height_m, 18.0, places=6)
        self.assertEqual(sol.floors, 6)
        self.assertAlmostEqual(sol.achieved_fsi, 2.0, places=6)
        self.assertAlmostEqual(sol.fsi_utilization_pct, 100.0, places=3)
        self.assertEqual(sol.controlling_constraint, "FSI_MAXED")

    @mock.patch("architecture.regulatory.fsi_optimizer._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_compliant_via_rules", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_feasible_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_ground_coverage_pct", return_value=100.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_fsi", return_value=10.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.solve_max_legal_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_permissible_height_by_road_width", return_value=100.0)
    def test_tie_break_prefers_more_floors_for_equal_fsi(
        self,
        mock_get_h_road,
        mock_solve_max_height,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_is_feasible_height,
        mock_is_compliant_via_rules,
        mock_is_layout_viable,
    ):
        """
        When multiple configurations have essentially equal achieved FSI, optimiser
        should prefer the one with more floors (taller building).
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from architecture.regulatory.height_solver import HeightSolution

        # Legal height: 3 floors at 3m each.
        mock_solve_max_height.return_value = HeightSolution(
            max_height_m=9.0,
            controlling_constraint="FSI_LIMIT",
            floors=3,
            footprint_area_sqft=400.0,
            achieved_fsi=1.0,
            fsi_utilization_pct=50.0,
            gc_utilization_pct=40.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

        class DummyReg:
            def __init__(self, fsi, util_pct, gc_pct):
                self.achieved_fsi = fsi
                self.fsi_utilization_pct = util_pct
                self.achieved_gc_pct = gc_pct

        # Same achieved FSI at all floor counts (within tolerance).
        def feasible_side_effect(*args, **kwargs):
            return True, {
                "regulatory": DummyReg(fsi=1.0, util_pct=50.0, gc_pct=40.0),
                "footprint_area_sqft": 400.0,
                "spacing_required_m": 0.0,
                "spacing_provided_m": None,
                "envelope": object(),
                "placement": object(),
            }

        mock_is_feasible_height.side_effect = feasible_side_effect

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="fsi_tie",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        sol = solve_optimal_fsi_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        # All floors have equal FSI; optimiser should pick the tallest (3 floors).
        self.assertEqual(sol.floors, 3)

    @mock.patch("architecture.regulatory.fsi_optimizer._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_compliant_via_rules", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_feasible_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_ground_coverage_pct", return_value=100.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_fsi", return_value=10.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.solve_max_legal_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_permissible_height_by_road_width", return_value=100.0)
    def test_geometry_limits_before_fsi(
        self,
        mock_get_h_road,
        mock_solve_max_height,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_is_feasible_height,
        mock_is_compliant_via_rules,
        mock_is_layout_viable,
    ):
        """
        When FSI is not fully utilised and road cap is high, optimiser should
        attribute the limit to GEOMETRY_LIMIT.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from architecture.regulatory.height_solver import HeightSolution

        # Legal height: 10 floors at 3m each.
        mock_solve_max_height.return_value = HeightSolution(
            max_height_m=30.0,
            controlling_constraint="FSI_LIMIT",
            floors=10,
            footprint_area_sqft=400.0,
            achieved_fsi=1.5,
            fsi_utilization_pct=75.0,
            gc_utilization_pct=40.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

        class DummyReg:
            def __init__(self, fsi, util_pct, gc_pct):
                self.achieved_fsi = fsi
                self.fsi_utilization_pct = util_pct
                self.achieved_gc_pct = gc_pct

        # FSI grows with floors but never maxes out; best at highest floors.
        def feasible_side_effect(*args, **kwargs):
            height_m = kwargs.get("height_m") or args[1]
            floors = int(height_m / 3.0)
            fsi = 0.1 * floors
            util_pct = min(90.0, fsi * 10.0)
            return True, {
                "regulatory": DummyReg(fsi=fsi, util_pct=util_pct, gc_pct=40.0),
                "footprint_area_sqft": 400.0,
                "spacing_required_m": 0.0,
                "spacing_provided_m": None,
                "envelope": object(),
                "placement": object(),
            }

        mock_is_feasible_height.side_effect = feasible_side_effect

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="fsi2",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        sol = solve_optimal_fsi_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        # Best at the highest floors (10), but FSI not maxed; road cap very high → GEOMETRY_LIMIT.
        self.assertEqual(sol.floors, 10)
        self.assertAlmostEqual(sol.optimal_height_m, 30.0, places=6)
        self.assertEqual(sol.controlling_constraint, "GEOMETRY_LIMIT")

    @mock.patch("architecture.regulatory.fsi_optimizer._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_compliant_via_rules", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_feasible_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_ground_coverage_pct", return_value=50.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_fsi", return_value=10.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.solve_max_legal_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_permissible_height_by_road_width", return_value=100.0)
    def test_gc_limits_before_fsi(
        self,
        mock_get_h_road,
        mock_solve_max_height,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_is_feasible_height,
        mock_is_compliant_via_rules,
        mock_is_layout_viable,
    ):
        """
        When higher floors become infeasible (e.g. due to GC constraints) before
        FSI is maxed and road cap is high, optimiser should attribute limit to
        GEOMETRY_LIMIT.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from architecture.regulatory.height_solver import HeightSolution

        # Legal height: 8 floors at 3m each.
        mock_solve_max_height.return_value = HeightSolution(
            max_height_m=24.0,
            controlling_constraint="FSI_LIMIT",
            floors=8,
            footprint_area_sqft=400.0,
            achieved_fsi=1.0,
            fsi_utilization_pct=50.0,
            gc_utilization_pct=45.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )

        class DummyReg:
            def __init__(self, fsi, util_pct, gc_pct):
                self.achieved_fsi = fsi
                self.fsi_utilization_pct = util_pct
                self.achieved_gc_pct = gc_pct

        # Floors > 5 become infeasible (think GC binding); best feasible FSI at 5 floors.
        def feasible_side_effect(*args, **kwargs):
            height_m = kwargs.get("height_m") or args[1]
            floors = int(height_m / 3.0)
            if floors > 5:
                return False, None
            fsi = 0.2 * floors
            util_pct = fsi * 10.0
            gc_pct = 49.0  # under the mocked 50% cap
            return True, {
                "regulatory": DummyReg(fsi=fsi, util_pct=util_pct, gc_pct=gc_pct),
                "footprint_area_sqft": 400.0,
                "spacing_required_m": 0.0,
                "spacing_provided_m": None,
                "envelope": object(),
                "placement": object(),
            }

        mock_is_feasible_height.side_effect = feasible_side_effect

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="fsi_gc",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        sol = solve_optimal_fsi_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        # Highest feasible floors is 5; FSI not maxed, road cap high → GEOMETRY_LIMIT.
        self.assertEqual(sol.floors, 5)
        self.assertEqual(sol.controlling_constraint, "GEOMETRY_LIMIT")

    @mock.patch("architecture.regulatory.fsi_optimizer._is_layout_viable", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_compliant_via_rules", return_value=True)
    @mock.patch("architecture.regulatory.fsi_optimizer._is_feasible_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_ground_coverage_pct", return_value=100.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_fsi", return_value=10.0)
    @mock.patch("architecture.regulatory.fsi_optimizer.solve_max_legal_height")
    @mock.patch("architecture.regulatory.fsi_optimizer.get_max_permissible_height_by_road_width")
    def test_road_cap_limits_before_fsi(
        self,
        mock_get_h_road,
        mock_solve_max_height,
        mock_get_max_fsi,
        mock_get_max_gc,
        mock_is_feasible_height,
        mock_is_compliant_via_rules,
        mock_is_layout_viable,
    ):
        """
        When road cap binds before FSI is maxed, optimiser should attribute the
        limit to ROAD_WIDTH_CAP.
        """
        from tp_ingestion.models import Plot
        from django.contrib.gis.geos import Polygon
        from architecture.regulatory.height_solver import HeightSolution

        # Legal height: 8 floors at 3m each, assumed to be at road cap.
        mock_solve_max_height.return_value = HeightSolution(
            max_height_m=24.0,
            controlling_constraint="ROAD_WIDTH_CAP",
            floors=8,
            footprint_area_sqft=400.0,
            achieved_fsi=1.5,
            fsi_utilization_pct=75.0,
            gc_utilization_pct=40.0,
            spacing_required_m=0.0,
            spacing_provided_m=None,
        )
        mock_get_h_road.return_value = 24.0

        class DummyReg:
            def __init__(self, fsi, util_pct, gc_pct):
                self.achieved_fsi = fsi
                self.fsi_utilization_pct = util_pct
                self.achieved_gc_pct = gc_pct

        def feasible_side_effect(*args, **kwargs):
            height_m = kwargs.get("height_m") or args[1]
            floors = int(height_m / 3.0)
            fsi = 0.15 * floors  # below max_fsi
            util_pct = fsi * 10.0
            return True, {
                "regulatory": DummyReg(fsi=fsi, util_pct=util_pct, gc_pct=40.0),
                "footprint_area_sqft": 400.0,
                "spacing_required_m": 0.0,
                "spacing_provided_m": None,
                "envelope": object(),
                "placement": object(),
            }

        mock_is_feasible_height.side_effect = feasible_side_effect

        plot_geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        plot = Plot(
            city="X",
            tp_scheme="TP0",
            fp_number="fsi_road",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=plot_geom,
            validation_status=True,
        )
        plot.road_width_m = 18.0

        sol = solve_optimal_fsi_configuration(
            plot=plot,
            storey_height_m=3.0,
            min_width_m=5.0,
            min_depth_m=3.5,
        )

        self.assertEqual(sol.floors, 8)
        self.assertEqual(sol.controlling_constraint, "ROAD_WIDTH_CAP")


