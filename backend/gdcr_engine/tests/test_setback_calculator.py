"""
Tests for gdcr_engine.setback_calculator.

Verifies:
1. Road-side margin from Table 6.24.
2. Road-side margin from H/5 formula.
3. Combined road margin = max(table, H/5, 1.5).
4. Side/rear margin from Table 6.26 (height-based).
5. Inter-building margin = max(H/3, 3.0).
6. validate_setbacks pass/fail logic.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from gdcr_engine.setback_calculator import (
    compute_setback_requirements,
    validate_setbacks,
    _road_side_margin_from_table,
    _road_side_margin_from_height,
    _side_rear_margin,
    _inter_building_margin,
)


_GDCR_STUB = {
    "fsi_rules": {"base_fsi": 1.8, "premium_tiers": []},
    "height_rules": {"road_width_height_map": []},
    "road_side_margin": {
        "road_width_margin_map": [
            {"road_max": 9, "margin": 3.0},
            {"road_max": 12, "margin": 4.5},
            {"road_max": 18, "margin": 6.0},
            {"road_max": 36, "margin": 9.0},
            {"road_max": 999, "margin": 12.0},
        ],
        "height_formula": "H / 5",
        "minimum_road_side_margin": 1.5,
    },
    "side_rear_margin": {
        "height_margin_map": [
            {"height_max": 16.5, "rear": 3.0, "side": 3.0},
            {"height_max": 25, "rear": 4.0, "side": 4.0},
            {"height_max": 45, "rear": 6.0, "side": 6.0},
            {"height_max": 999, "rear": 8.0, "side": 8.0},
        ]
    },
    "inter_building_margin": {"formula": "H / 3", "minimum_spacing_m": 3.0},
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
}


def _patch_gdcr():
    return mock.patch("rules_engine.rules.loader.get_gdcr_config", return_value=_GDCR_STUB)


class RoadSideMarginTableTests(TestCase):
    def test_road_9m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_road_side_margin_from_table(9.0), 3.0)

    def test_road_12m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_road_side_margin_from_table(12.0), 4.5)

    def test_road_18m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_road_side_margin_from_table(18.0), 6.0)

    def test_road_36m(self):
        with _patch_gdcr():
            self.assertAlmostEqual(_road_side_margin_from_table(36.0), 9.0)

    def test_road_60m(self):
        """Road > 36m should use last entry (12.0 m)."""
        with _patch_gdcr():
            self.assertAlmostEqual(_road_side_margin_from_table(60.0), 12.0)


class RoadSideMarginHeightTests(TestCase):
    def test_h_over_5(self):
        self.assertAlmostEqual(_road_side_margin_from_height(20.0), 4.0)

    def test_h_over_5_large(self):
        self.assertAlmostEqual(_road_side_margin_from_height(60.0), 12.0)


class SideRearMarginTests(TestCase):
    def test_low_rise_16_5(self):
        with _patch_gdcr():
            side, rear = _side_rear_margin(16.5)
        self.assertAlmostEqual(side, 3.0)
        self.assertAlmostEqual(rear, 3.0)

    def test_mid_range_25(self):
        with _patch_gdcr():
            side, rear = _side_rear_margin(25.0)
        self.assertAlmostEqual(side, 4.0)
        self.assertAlmostEqual(rear, 4.0)

    def test_high_rise_45(self):
        with _patch_gdcr():
            side, rear = _side_rear_margin(45.0)
        self.assertAlmostEqual(side, 6.0)
        self.assertAlmostEqual(rear, 6.0)

    def test_very_tall_above_45(self):
        with _patch_gdcr():
            side, rear = _side_rear_margin(70.0)
        self.assertAlmostEqual(side, 8.0)
        self.assertAlmostEqual(rear, 8.0)


class InterBuildingMarginTests(TestCase):
    def test_h_over_3_dominates(self):
        """For H=15, H/3=5.0 > minimum 3.0."""
        with _patch_gdcr():
            m = _inter_building_margin(15.0)
        self.assertAlmostEqual(m, 5.0)

    def test_minimum_floor(self):
        """For H=6, H/3=2.0 < minimum 3.0; minimum applies."""
        with _patch_gdcr():
            m = _inter_building_margin(6.0)
        self.assertAlmostEqual(m, 3.0)


class ComputeSetbackRequirementsTests(TestCase):
    def test_road_margin_is_whichever_higher(self):
        """
        Road=18m, H=30m:
            table_margin   = 6.0 m
            H/5            = 30/5 = 6.0 m
            minimum        = 1.5 m
            required       = max(6.0, 6.0, 1.5) = 6.0 m
        """
        with _patch_gdcr():
            result = compute_setback_requirements(road_width_m=18.0, building_height_m=30.0)
        self.assertAlmostEqual(result.road_margin_required_m, 6.0, places=3)
        self.assertAlmostEqual(result.road_margin_table_m, 6.0, places=3)
        self.assertAlmostEqual(result.road_margin_height_m, 6.0, places=3)

    def test_height_formula_dominates_for_tall_building(self):
        """
        Road=18m, H=45m:
            table_margin   = 6.0 m
            H/5            = 45/5 = 9.0 m
            required       = max(6.0, 9.0, 1.5) = 9.0 m (H/5 wins)
        """
        with _patch_gdcr():
            result = compute_setback_requirements(road_width_m=18.0, building_height_m=45.0)
        self.assertAlmostEqual(result.road_margin_required_m, 9.0, places=3)

    def test_setback_side_rear_for_30m_building(self):
        """30m building: height_max 45 tier → side=6.0, rear=6.0."""
        with _patch_gdcr():
            result = compute_setback_requirements(road_width_m=18.0, building_height_m=30.0)
        self.assertAlmostEqual(result.side_margin_required_m, 6.0, places=3)
        self.assertAlmostEqual(result.rear_margin_required_m, 6.0, places=3)


class ValidateSetbacksTests(TestCase):
    def _make_setbacks(self, road_m=6.0, side_m=6.0, rear_m=6.0, inter_m=10.0):
        from gdcr_engine.setback_calculator import SetbackRequirements
        return SetbackRequirements(
            road_margin_table_m=6.0,
            road_margin_height_m=6.0,
            road_margin_required_m=road_m,
            side_margin_required_m=side_m,
            rear_margin_required_m=rear_m,
            inter_building_required_m=inter_m,
            road_width_m=18.0,
            building_height_m=30.0,
        )

    def test_all_pass_when_sufficient(self):
        """All checks pass when provided >= required."""
        with _patch_gdcr():
            req = self._make_setbacks()
        results = validate_setbacks(
            required=req,
            provided_road_margin_m=7.0,
            provided_side_margin_m=7.0,
            provided_rear_margin_m=7.0,
            provided_inter_building_m=11.0,
        )
        self.assertTrue(all(r["passed"] for r in results))

    def test_fail_when_road_margin_insufficient(self):
        """Road margin check FAIL when provided < required."""
        with _patch_gdcr():
            req = self._make_setbacks(road_m=6.0)
        results = validate_setbacks(
            required=req,
            provided_road_margin_m=4.0,
        )
        road_check = next(r for r in results if r["dimension"] == "road_margin")
        self.assertFalse(road_check["passed"])

    def test_none_provided_returns_none_passed(self):
        """When a dimension is not provided, passed is None (not fail)."""
        with _patch_gdcr():
            req = self._make_setbacks()
        results = validate_setbacks(required=req)
        for r in results:
            self.assertIsNone(r["passed"])
