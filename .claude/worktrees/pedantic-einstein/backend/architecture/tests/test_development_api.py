from __future__ import annotations

"""
API tests for the optimal development floor-plan endpoint.

These tests focus on the HTTP contract and mapping behaviour, not on the
underlying geometry or optimisation engines.
"""

from django.test import TestCase
from django.urls import reverse
from unittest import mock

from tp_ingestion.models import Plot


class OptimalDevelopmentAPITests(TestCase):
    def setUp(self):
        # Minimal Plot fixture; geometry can be a simple square.
        from django.contrib.gis.geos import Polygon

        geom = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        self.plot = Plot.objects.create(
            city="X",
            tp_scheme="TP14",
            fp_number="126",
            area_excel=1000.0,
            area_geometry=1000.0,
            geom=geom,
            validation_status=True,
        )
        self.plot.road_width_m = 18.0
        self.plot.save()

        self.url = "/api/v1/development/optimal-floor-plan/"

    @mock.patch(
        "api.views.development.generate_optimal_development_floor_plans",
    )
    def test_success_response_structure(self, mock_service):
        """
        When the service returns an OK result, the API should return a 200 with
        the expected top-level keys.
        """
        from architecture.services.development_pipeline import (
            DevelopmentFloorPlanResult,
            PlacementSummaryDTO,
            TowerFloorLayoutDTO,
        )
        from residential_layout.building_aggregation import BuildingLayoutContract
        from residential_layout.floor_aggregation import FloorLayoutContract

        placement_summary = PlacementSummaryDTO(
            n_towers=1,
            per_tower_footprint_sqft=[400.0],
            spacing_required_m=6.0,
            spacing_provided_m=None,
        )
        tower_layout = TowerFloorLayoutDTO(
            tower_index=0,
            floor_id="L0_T0",
            total_units=10,
            efficiency_ratio_floor=0.6,
            unit_area_sum_sqm=300.0,
            footprint_polygon_wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            core_polygon_wkt=None,
            corridor_polygon_wkt=None,
            raw_contract=None,
        )
        # Minimal building layout metadata; not deeply validated here.
        building_layout = BuildingLayoutContract(
            building_id="B0",
            floors=[],
            total_floors=0,
            total_units=0,
            total_unit_area=0.0,
            total_residual_area=0.0,
            building_efficiency=0.0,
            building_height_m=0.0,
        )
        result = DevelopmentFloorPlanResult(
            status="OK",
            failure_reason=None,
            failure_details=None,
            n_towers=1,
            floors=5,
            height_m=15.0,
            achieved_fsi=1.5,
            fsi_utilization_pct=60.0,
            total_bua_sqft=1500.0,
            gc_utilization_pct=35.0,
            controlling_constraint="FSI_MAXED",
            envelope_wkt="POLYGON((0 0,10 0,10 10,0 10,0 0))",
            placement_summary=placement_summary,
            tower_floor_layouts=[tower_layout],
            building_layout=building_layout,
        )
        mock_service.return_value = result

        payload = {
            "tp": 14,
            "fp": 126,
            "storey_height_m": 3.0,
            "min_width_m": 5.0,
            "min_depth_m": 3.5,
        }
        resp = self.client.post(self.url, data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "OK")
        self.assertIn("configuration", body)
        self.assertIn("geometry", body)
        self.assertIn("towers", body)

    @mock.patch(
        "api.views.development.generate_optimal_development_floor_plans",
    )
    def test_infeasible_returns_domain_failure(self, mock_service):
        from architecture.services.development_pipeline import DevelopmentFloorPlanResult

        mock_service.return_value = DevelopmentFloorPlanResult(
            status="INFEASIBLE",
            failure_reason="INFEASIBLE",
            failure_details={"message": "No feasible configuration"},
            n_towers=0,
            floors=0,
            height_m=0.0,
            achieved_fsi=0.0,
            fsi_utilization_pct=0.0,
            total_bua_sqft=0.0,
            gc_utilization_pct=0.0,
            controlling_constraint="INFEASIBLE",
            envelope_wkt=None,
            placement_summary=None,
            tower_floor_layouts=[],
            building_layout=None,
        )

        resp = self.client.post(
            self.url,
            data={"tp": 14, "fp": 126},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "INFEASIBLE")
        self.assertIn("failure_reason", body)

    def test_invalid_plot_returns_404(self):
        # Use a TP/FP combination that does not exist.
        resp = self.client.post(
            self.url,
            data={"tp": 99, "fp": 999},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.json())

    def test_invalid_input_returns_400(self):
        # Negative storey_height_m should fail validation.
        resp = self.client.post(
            self.url,
            data={"tp": 14, "fp": 126, "storey_height_m": -3.0},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("detail", body)

