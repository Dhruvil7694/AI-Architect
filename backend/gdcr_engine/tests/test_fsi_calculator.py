"""
Tests for gdcr_engine.fsi_calculator.

Verifies:
1. FSI parameters for corridor vs non-corridor plots.
2. Achieved FSI calculation and utilisation percentages.
3. BUA estimation from footprint and height.
4. Max floors from FSI ceiling.
5. FSI tier selection matches GDCR.yaml premium_tiers.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from gdcr_engine.fsi_calculator import (
    compute_fsi_parameters,
    compute_achieved_fsi,
    estimate_bua_from_footprint,
    compute_max_floors_from_fsi,
    debug_fsi_trace,
)


# Deterministic GDCR.yaml stub (matches real GDCR.yaml structure)
_GDCR_STUB = {
    "fsi_rules": {
        "base_fsi": 1.8,
        "premium_tiers": [
            {"additional_fsi": 0.9, "resulting_cap": 2.7, "jantri_rate_percent": 40},
            {"additional_fsi": 1.8, "resulting_cap": 3.6, "jantri_rate_percent": 40, "corridor_required": True},
            {"additional_fsi": 2.2, "resulting_cap": 4.0, "jantri_rate_percent": 40, "corridor_required": True},
        ],
        "corridor_rule": {
            "eligible_if": {"road_width_min_m": 36.0, "buffer_distance_m": 200.0}
        },
    },
    "height_rules": {"road_width_height_map": [
        {"road_max": 9, "max_height": 10},
        {"road_max": 12, "max_height": 16.5},
        {"road_max": 18, "max_height": 30},
        {"road_max": 36, "max_height": 45},
        {"road_max": 999, "max_height": 70},
    ]},
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
    "inter_building_margin": {"formula": "H / 3", "minimum_spacing_m": 3.0},
}


def _patch_gdcr():
    """Return a mock.patch context manager for get_gdcr_config."""
    return mock.patch("rules_engine.rules.loader.get_gdcr_config", return_value=_GDCR_STUB)


class FSIParametersTests(TestCase):
    """Tests for compute_fsi_parameters."""

    def test_non_corridor_max_fsi_is_2_7(self):
        """Non-corridor plot: highest non-corridor-required cap = 2.7."""
        with _patch_gdcr():
            params = compute_fsi_parameters(plot_area_sqm=1000.0, corridor_eligible=False)
        self.assertAlmostEqual(params.applicable_max_fsi, 2.7, places=6)
        self.assertAlmostEqual(params.max_fsi_non_corridor, 2.7, places=6)

    def test_corridor_max_fsi_is_4_0(self):
        """Corridor-eligible plot: highest cap across all tiers = 4.0."""
        with _patch_gdcr():
            params = compute_fsi_parameters(plot_area_sqm=1000.0, corridor_eligible=True)
        self.assertAlmostEqual(params.applicable_max_fsi, 4.0, places=6)
        self.assertAlmostEqual(params.max_fsi_with_corridor, 4.0, places=6)

    def test_base_fsi_always_1_8(self):
        """Base FSI must always be 1.8 regardless of corridor eligibility."""
        with _patch_gdcr():
            params = compute_fsi_parameters(plot_area_sqm=500.0, corridor_eligible=False)
        self.assertAlmostEqual(params.base_fsi, 1.8, places=6)

    def test_max_bua_non_corridor(self):
        """max_bua_applicable = max_fsi * plot_area for non-corridor plot."""
        with _patch_gdcr():
            params = compute_fsi_parameters(plot_area_sqm=1000.0, corridor_eligible=False)
        # 2.7 * 1000 = 2700
        self.assertAlmostEqual(params.max_bua_applicable_sqm, 2700.0, places=2)

    def test_max_bua_corridor(self):
        """max_bua_applicable = 4.0 * plot_area for corridor-eligible plot."""
        with _patch_gdcr():
            params = compute_fsi_parameters(plot_area_sqm=3678.532, corridor_eligible=True)
        # 4.0 * 3678.532 = 14714.128
        self.assertAlmostEqual(params.max_bua_applicable_sqm, 14714.128, places=2)

    def test_max_bua_base_is_correct(self):
        """max_bua_base = base_fsi * plot_area."""
        with _patch_gdcr():
            params = compute_fsi_parameters(plot_area_sqm=1000.0)
        self.assertAlmostEqual(params.max_bua_base_sqm, 1800.0, places=2)


class AchievedFSITests(TestCase):
    """Tests for compute_achieved_fsi."""

    def test_achieved_fsi_formula(self):
        """achieved_fsi = total_bua_sqm / plot_area_sqm."""
        with _patch_gdcr():
            result = compute_achieved_fsi(
                plot_area_sqm=1000.0,
                total_bua_sqm=2700.0,
                corridor_eligible=False,
            )
        self.assertAlmostEqual(result.achieved_fsi, 2.7, places=4)

    def test_achieved_fsi_utilisation_100_pct(self):
        """Full utilisation when achieved == max."""
        with _patch_gdcr():
            result = compute_achieved_fsi(
                plot_area_sqm=1000.0,
                total_bua_sqm=2700.0,
                corridor_eligible=False,
            )
        self.assertAlmostEqual(result.max_fsi_utilization_pct, 100.0, places=2)

    def test_exceeds_base_flag(self):
        """exceeds_base = True when achieved > 1.8."""
        with _patch_gdcr():
            result = compute_achieved_fsi(
                plot_area_sqm=1000.0,
                total_bua_sqm=2000.0,
                corridor_eligible=False,
            )
        self.assertTrue(result.exceeds_base)   # 2.0 > 1.8
        self.assertFalse(result.exceeds_max)   # 2.0 < 2.7

    def test_exceeds_max_flag(self):
        """exceeds_max = True when achieved > applicable_max_fsi."""
        with _patch_gdcr():
            result = compute_achieved_fsi(
                plot_area_sqm=1000.0,
                total_bua_sqm=2800.0,
                corridor_eligible=False,
            )
        self.assertTrue(result.exceeds_max)    # 2.8 > 2.7

    def test_remaining_bua_positive(self):
        """remaining_bua_sqm > 0 when achieved < max."""
        with _patch_gdcr():
            result = compute_achieved_fsi(
                plot_area_sqm=1000.0,
                total_bua_sqm=2000.0,
                corridor_eligible=False,
            )
        self.assertGreater(result.remaining_bua_sqm, 0.0)  # 2700 - 2000 = 700

    def test_zero_plot_area_returns_zero_fsi(self):
        """Zero plot area yields achieved_fsi = 0.0."""
        with _patch_gdcr():
            result = compute_achieved_fsi(
                plot_area_sqm=0.0,
                total_bua_sqm=1000.0,
            )
        self.assertEqual(result.achieved_fsi, 0.0)


class BUAEstimationTests(TestCase):
    """Tests for estimate_bua_from_footprint and compute_max_floors_from_fsi."""

    def test_estimate_bua_basic(self):
        """BUA = footprint * floors, floors = floor(height / storey_height)."""
        num_floors, bua = estimate_bua_from_footprint(
            footprint_area_sqm=500.0,
            building_height_m=9.0,
            storey_height_m=3.0,
        )
        self.assertEqual(num_floors, 3)
        self.assertAlmostEqual(bua, 1500.0, places=4)

    def test_estimate_bua_minimum_1_floor(self):
        """Even very short buildings get at least 1 floor."""
        num_floors, bua = estimate_bua_from_footprint(
            footprint_area_sqm=200.0,
            building_height_m=1.0,
            storey_height_m=3.0,
        )
        self.assertEqual(num_floors, 1)

    def test_max_floors_from_fsi(self):
        """max_floors = floor(max_bua / footprint_area)."""
        max_floors, h_limit = compute_max_floors_from_fsi(
            plot_area_sqm=1000.0,
            footprint_area_sqm=250.0,
            max_fsi=2.7,
            storey_height_m=3.0,
        )
        # max_bua = 2700 / 250 = 10 floors, h = 30.0
        self.assertEqual(max_floors, 10)
        self.assertAlmostEqual(h_limit, 30.0, places=4)

    def test_max_floors_zero_when_footprint_exceeds_bua(self):
        """max_floors = 0 when footprint >= max_bua."""
        max_floors, h_limit = compute_max_floors_from_fsi(
            plot_area_sqm=100.0,
            footprint_area_sqm=500.0,
            max_fsi=2.7,
        )
        self.assertEqual(max_floors, 0)
        self.assertAlmostEqual(h_limit, 0.0, places=4)


class DebugTraceTests(TestCase):
    """Tests for debug_fsi_trace output format."""

    def test_trace_contains_key_values(self):
        """Debug trace must include all key parameters."""
        trace = debug_fsi_trace(
            plot_area_sqm=3678.532,
            road_width_m=60.0,
            max_fsi=4.0,
            total_bua_sqm=14714.128,
            achieved_fsi=4.0,
            max_bua_sqm=14714.128,
        )
        self.assertIn("plot_area_sqm=3678.5320", trace)
        self.assertIn("road_width_m=60.000", trace)
        self.assertIn("max_fsi=4.0", trace)
        self.assertIn("max_bua_sqm=14714.1280", trace)
        self.assertIn("achieved_fsi=4.0000", trace)
