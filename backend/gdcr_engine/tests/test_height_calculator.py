"""
Tests for gdcr_engine.height_calculator.

Verifies:
1. Road-width to max-height mapping (GDCR Table 6.23).
2. DW3 access restriction (road < 9 m).
3. FSI-derived height limit computation.
4. Controlling constraint attribution.
5. Storey count calculation.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from gdcr_engine.height_calculator import (
    compute_height_limits,
    compute_storey_count,
    _height_from_road_width,
)


_HEIGHT_MAP = [
    {"road_max": 9, "max_height": 10},
    {"road_max": 12, "max_height": 16.5},
    {"road_max": 18, "max_height": 30},
    {"road_max": 36, "max_height": 45},
    {"road_max": 999, "max_height": 70},
]

_GDCR_STUB = {
    "fsi_rules": {"base_fsi": 1.8, "premium_tiers": []},
    "height_rules": {"road_width_height_map": _HEIGHT_MAP},
    "road_side_margin": {
        "road_width_margin_map": [],
        "height_formula": "H / 5",
        "minimum_road_side_margin": 1.5,
    },
    "side_rear_margin": {"height_margin_map": []},
    "ground_coverage": {"max_percentage_dw3": 40},
    "access_rules": {
        "minimum_road_width_for_dw3": 9,
        "if_road_width_less_than_9": {"max_height": 10},
    },
    "common_open_plot": {
        "applies_if_plot_area_above_sqm": 2000,
        "required_fraction": 0.10,
        "minimum_total_area_sqm": 200,
    },
    "lift_requirement": {"if_height_above": 10},
    "basement": {"height_min": 2.4},
    "fire_safety": {
        "fire_noc_required_if_height_above": 15,
        "refuge_area_if_height_above": 25,
    },
    "height_band_rules": {"low_rise_max_m": 10, "mid_rise_max_m": 15},
    "inter_building_margin": {"minimum_spacing_m": 3.0},
}


def _patch_gdcr():
    return mock.patch("rules_engine.rules.loader.get_gdcr_config", return_value=_GDCR_STUB)


class HeightFromRoadWidthTests(TestCase):
    def test_road_9m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_height_from_road_width(9.0), 10.0)

    def test_road_12m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_height_from_road_width(12.0), 16.5)

    def test_road_18m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_height_from_road_width(18.0), 30.0)

    def test_road_36m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_height_from_road_width(36.0), 45.0)

    def test_road_60m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_height_from_road_width(60.0), 70.0)

    def test_road_6m_below_9(self):
        """Road 6m < 9m → first entry catches road_max=9, height=10."""
        with _patch_gdcr():
            self.assertAlmostEqual(_height_from_road_width(6.0), 10.0)


class HeightLimitsTests(TestCase):
    def test_road_cap_only_no_fsi(self):
        """Without FSI/footprint inputs, constraint is ROAD_WIDTH_CAP."""
        with _patch_gdcr():
            result = compute_height_limits(road_width_m=18.0)
        self.assertAlmostEqual(result.h_road_cap_m, 30.0)
        self.assertEqual(result.controlling_constraint, "ROAD_WIDTH_CAP")
        self.assertIsNone(result.h_fsi_limit_m)

    def test_fsi_limits_before_road_cap(self):
        """
        Road cap = 45m but FSI only allows 6 floors (18m):
        controlling_constraint = FSI_LIMIT.
        """
        with _patch_gdcr():
            result = compute_height_limits(
                road_width_m=36.0,         # road cap = 45 m
                plot_area_sqm=1000.0,
                footprint_area_sqm=300.0,
                max_fsi=1.8,               # max_bua=1800, floors=floor(1800/300)=6
                storey_height_m=3.0,
            )
        # h_fsi_limit = 6 * 3 = 18.0, which is < h_road_cap=45.0
        self.assertAlmostEqual(result.h_fsi_limit_m, 18.0, places=3)
        self.assertAlmostEqual(result.h_effective_m, 18.0, places=3)
        self.assertEqual(result.controlling_constraint, "FSI_LIMIT")

    def test_dw3_access_restriction(self):
        """Road < 9m: DW3 not permitted, max height capped at 10m."""
        with _patch_gdcr():
            result = compute_height_limits(road_width_m=7.0)
        self.assertFalse(result.dw3_permitted)
        self.assertAlmostEqual(result.h_dw3_restriction_m, 10.0)
        self.assertAlmostEqual(result.h_effective_m, 10.0)
        self.assertEqual(result.controlling_constraint, "DW3_ACCESS")

    def test_storey_count_at_effective_height(self):
        """max_floors = floor(h_effective / storey_height)."""
        with _patch_gdcr():
            result = compute_height_limits(road_width_m=18.0, storey_height_m=3.0)
        # h_effective = 30.0, storey = 3.0 → 10 floors
        self.assertEqual(result.max_floors, 10)

    def test_road_36m_no_fsi_cap(self):
        """Large plot with high FSI max → road cap controls at 45m."""
        with _patch_gdcr():
            result = compute_height_limits(
                road_width_m=36.0,
                plot_area_sqm=5000.0,
                footprint_area_sqm=200.0,
                max_fsi=4.0,               # max_bua=20000, floors=100 → well above road cap
                storey_height_m=3.0,
            )
        self.assertAlmostEqual(result.h_road_cap_m, 45.0)
        self.assertAlmostEqual(result.h_effective_m, 45.0)
        self.assertEqual(result.controlling_constraint, "ROAD_WIDTH_CAP")


class StoreyCountTests(TestCase):
    def test_basic(self):
        self.assertEqual(compute_storey_count(9.0, 3.0), 3)

    def test_non_exact_floor(self):
        """floor(16.5 / 3.0) = 5."""
        self.assertEqual(compute_storey_count(16.5, 3.0), 5)

    def test_zero_height(self):
        self.assertEqual(compute_storey_count(0.0, 3.0), 0)

    def test_invalid_storey_height_raises(self):
        with self.assertRaises(ValueError):
            compute_storey_count(10.0, 0.0)
