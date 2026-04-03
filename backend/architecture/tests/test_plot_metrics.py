"""
Tests for architecture.feasibility.plot_metrics.

Uses simple rectangular polygons and synthetic edge_margin_audit entries
to verify frontage length, plot depth, shape classification, and
height band labels.
"""

from __future__ import annotations

from django.test import TestCase
from shapely.geometry import Polygon

from architecture.feasibility.plot_metrics import (
    PlotMetrics,
    _classify_shape,
    _compute_frontage_length_m,
    _compute_plot_depth_m,
    _count_road_edges,
    _height_band_for_height,
    compute_plot_metrics,
)
from common.units import dxf_plane_area_to_sqm, dxf_to_metres, sqm_to_sqft


class TestPlotMetricsHelpers(TestCase):
    def test_frontage_and_road_edges(self):
        audit = [
            {"edge_type": "ROAD", "length_dxf": 20.0, "p1": [0.0, 0.0], "p2": [20.0, 0.0]},
            {"edge_type": "SIDE", "length_dxf": 10.0, "p1": [20.0, 0.0], "p2": [20.0, 10.0]},
            {"edge_type": "ROAD", "length_dxf": 5.0, "p1": [0.0, 10.0], "p2": [5.0, 10.0]},
        ]
        frontage_m = _compute_frontage_length_m(audit)
        n_road = _count_road_edges(audit)

        self.assertAlmostEqual(frontage_m, dxf_to_metres(25.0), places=6)
        self.assertEqual(n_road, 2)

    def test_plot_depth_for_simple_rectangle(self):
        # Rectangle 0,0 to 20,10 in DXF feet; primary ROAD edge along X at y=0
        poly = Polygon([(0, 0), (20, 0), (20, 10), (0, 10), (0, 0)])
        audit = [
            {"edge_type": "ROAD", "length_dxf": 20.0, "p1": [0.0, 0.0], "p2": [20.0, 0.0]},
        ]
        depth_m = _compute_plot_depth_m(poly, audit)

        # Depth should be approx 10 ft in metres
        self.assertAlmostEqual(depth_m, dxf_to_metres(10.0), places=6)

    def test_plot_depth_l_shaped_along_road_normal(self):
        # L-shaped: road along bottom (0,0)-(15,0). Depth = extent along normal (0,1).
        # Exterior: (0,0),(15,0),(15,8),(8,8),(8,25),(0,25),(0,0) -> y in [0,25] -> depth 25 DXF
        poly = Polygon([(0, 0), (15, 0), (15, 8), (8, 8), (8, 25), (0, 25), (0, 0)])
        audit = [
            {"edge_type": "ROAD", "length_dxf": 15.0, "p1": [0.0, 0.0], "p2": [15.0, 0.0]},
        ]
        depth_m = _compute_plot_depth_m(poly, audit)
        # Depth is projection along road normal only (no MBR fallback)
        self.assertAlmostEqual(depth_m, dxf_to_metres(25.0), places=6)

    def test_shape_class_rectangular_vs_irregular(self):
        rect = Polygon([(0, 0), (20, 0), (20, 10), (0, 10), (0, 0)])
        irregular = Polygon([(0, 0), (15, 0), (20, 5), (10, 10), (0, 7), (0, 0)])

        self.assertEqual(_classify_shape(rect), "RECTANGULAR")
        self.assertEqual(_classify_shape(irregular), "IRREGULAR")

    def test_height_band_mapping(self):
        self.assertEqual(_height_band_for_height(8.0), "LOW_RISE")
        self.assertEqual(_height_band_for_height(10.0), "LOW_RISE")
        self.assertEqual(_height_band_for_height(12.0), "MID_RISE")
        self.assertEqual(_height_band_for_height(15.0), "MID_RISE")
        self.assertEqual(_height_band_for_height(20.0), "HIGH_RISE")


class TestComputePlotMetricsEndToEnd(TestCase):
    def test_compute_plot_metrics_happy_path(self):
        # Square 0,0 to 10,10 in DXF plane units (metres): area = 100 m²
        poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
        wkt = poly.wkt
        area_sqm = dxf_plane_area_to_sqm(float(poly.area))
        area_intl_sqft = sqm_to_sqft(area_sqm)

        edge_audit = [
            {"edge_type": "ROAD", "length_dxf": 10.0, "p1": [0.0, 0.0], "p2": [10.0, 0.0]},
            {"edge_type": "SIDE", "length_dxf": 10.0, "p1": [10.0, 0.0], "p2": [10.0, 10.0]},
            {"edge_type": "SIDE", "length_dxf": 10.0, "p1": [10.0, 10.0], "p2": [0.0, 10.0]},
            {"edge_type": "SIDE", "length_dxf": 10.0, "p1": [0.0, 10.0], "p2": [0.0, 0.0]},
        ]

        metrics = compute_plot_metrics(
            plot_geom_wkt=wkt,
            plot_area_sqft=area_intl_sqft,
            plot_area_sqm=area_sqm,
            edge_margin_audit=edge_audit,
            building_height_m=16.5,
        )

        self.assertIsInstance(metrics, PlotMetrics)
        self.assertAlmostEqual(metrics.plot_area_sqft, area_intl_sqft, places=3)
        self.assertAlmostEqual(metrics.plot_area_sqm, area_sqm, places=6)

        # Frontage and depth both 10 m in DXF
        self.assertAlmostEqual(metrics.frontage_length_m, dxf_to_metres(10.0), places=6)
        self.assertAlmostEqual(metrics.plot_depth_m, dxf_to_metres(10.0), places=6)
        self.assertEqual(metrics.n_road_edges, 1)
        self.assertFalse(metrics.is_corner_plot)
        self.assertEqual(metrics.shape_class, "RECTANGULAR")
        self.assertEqual(metrics.height_band_label, "HIGH_RISE")

