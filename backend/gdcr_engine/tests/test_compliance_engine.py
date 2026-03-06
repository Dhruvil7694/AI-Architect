"""
Tests for gdcr_engine.compliance_engine.

Verifies:
1. Compliant proposals pass all FAIL-producing rules.
2. FSI overrun produces FAIL.
3. Ground coverage overrun produces FAIL.
4. COP threshold logic (applies only when plot > 2000 sqm).
5. Road-side margin rule present in results.
6. Correct max_fsi selection (2.7 non-corridor, 4.0 corridor).
7. Debug trace string is generated.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from gdcr_engine.compliance_engine import (
    ComplianceContext,
    evaluate_gdcr_compliance,
    PASS, FAIL, INFO, NA,
)


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
    return mock.patch("rules_engine.rules.loader.get_gdcr_config", return_value=_GDCR_STUB)


def _compliant_ctx(**overrides) -> ComplianceContext:
    """Build a minimally-compliant context for testing."""
    base = dict(
        plot_area_sqm=1500.0,
        road_width_m=18.0,
        building_height_m=27.0,
        total_bua_sqm=4050.0,     # 1500 * 2.7 = 4050 (exactly at non-corridor max)
        footprint_area_sqm=450.0,
        num_floors=9,
        storey_height_m=3.0,
        corridor_eligible=False,
        ground_coverage_pct=30.0,
        has_lift=True,
        debug=False,
    )
    base.update(overrides)
    return ComplianceContext(**base)


class CompliantProposalTests(TestCase):
    def test_compliant_proposal_has_no_fails(self):
        """A proposal at exactly the non-corridor FSI cap must have zero FAIL rules."""
        with _patch_gdcr():
            ctx = _compliant_ctx()
            report = evaluate_gdcr_compliance(ctx)
        self.assertEqual(report.fail_count, 0)
        self.assertTrue(report.compliant)

    def test_achieved_fsi_equals_non_corridor_max(self):
        """Achieved FSI must be 2.7 (exactly at non-corridor cap)."""
        with _patch_gdcr():
            report = evaluate_gdcr_compliance(_compliant_ctx())
        self.assertAlmostEqual(report.achieved_fsi, 2.7, places=4)
        self.assertAlmostEqual(report.applicable_max_fsi, 2.7, places=4)

    def test_corridor_eligible_plot_reports_fsi_4_0(self):
        """Corridor-eligible plot on 60m road uses FSI cap 4.0."""
        with _patch_gdcr():
            ctx = _compliant_ctx(
                plot_area_sqm=3678.532,
                road_width_m=60.0,
                building_height_m=42.0,
                total_bua_sqm=14714.128,   # 3678.532 * 4.0
                footprint_area_sqm=919.633,
                num_floors=14,
                corridor_eligible=True,
                ground_coverage_pct=25.0,
                cop_provided_sqm=400.0,
            )
            report = evaluate_gdcr_compliance(ctx)
        self.assertAlmostEqual(report.applicable_max_fsi, 4.0, places=4)
        self.assertAlmostEqual(report.achieved_fsi, 4.0, places=2)
        self.assertEqual(report.fail_count, 0)

    def test_rule_results_sorted_by_rule_id(self):
        """Rule results must be sorted deterministically by rule_id."""
        with _patch_gdcr():
            report = evaluate_gdcr_compliance(_compliant_ctx())
        ids = [r.rule_id for r in report.rule_results]
        self.assertEqual(ids, sorted(ids))


class FSIViolationTests(TestCase):
    def test_fsi_overrun_non_corridor(self):
        """FSI above 2.7 on non-corridor plot must FAIL gdcr.fsi.max."""
        with _patch_gdcr():
            ctx = _compliant_ctx(total_bua_sqm=5000.0)  # FSI = 5000/1500 ≈ 3.33 > 2.7
            report = evaluate_gdcr_compliance(ctx)
        fsi_max_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.fsi.max")
        self.assertEqual(fsi_max_rule.status, FAIL)
        self.assertFalse(report.compliant)

    def test_fsi_above_base_below_max_passes_max_check(self):
        """FSI between 1.8 and 2.7: base rule is INFO (premium required), max PASS."""
        with _patch_gdcr():
            ctx = _compliant_ctx(total_bua_sqm=3000.0)  # FSI = 2.0
            report = evaluate_gdcr_compliance(ctx)
        base_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.fsi.base")
        max_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.fsi.max")
        self.assertEqual(base_rule.status, INFO)  # 2.0 > 1.8 but <= 2.7: premium FSI needed
        self.assertEqual(max_rule.status, PASS)   # 2.0 <= 2.7


class GroundCoverageTests(TestCase):
    def test_gc_overrun_fails(self):
        """Ground coverage > 40% must FAIL gdcr.gc.max."""
        with _patch_gdcr():
            ctx = _compliant_ctx(ground_coverage_pct=45.0)
            report = evaluate_gdcr_compliance(ctx)
        gc_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.gc.max")
        self.assertEqual(gc_rule.status, FAIL)

    def test_gc_at_limit_passes(self):
        """Ground coverage exactly at 40% must PASS."""
        with _patch_gdcr():
            ctx = _compliant_ctx(ground_coverage_pct=40.0)
            report = evaluate_gdcr_compliance(ctx)
        gc_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.gc.max")
        self.assertEqual(gc_rule.status, PASS)

    def test_gc_not_provided_is_info(self):
        """Omitting ground_coverage_pct yields INFO (not FAIL)."""
        with _patch_gdcr():
            ctx = _compliant_ctx(ground_coverage_pct=None)
            report = evaluate_gdcr_compliance(ctx)
        gc_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.gc.max")
        self.assertEqual(gc_rule.status, INFO)


class COPThresholdTests(TestCase):
    def test_cop_not_required_below_2000_sqm(self):
        """Plot area <= 2000 sqm: COP rule is NA."""
        with _patch_gdcr():
            ctx = _compliant_ctx(plot_area_sqm=1500.0)
            report = evaluate_gdcr_compliance(ctx)
        cop_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.cop.required")
        self.assertEqual(cop_rule.status, NA)

    def test_cop_required_above_2000_sqm_without_cop_is_info(self):
        """Plot > 2000 sqm with no cop_provided: INFO (not FAIL)."""
        with _patch_gdcr():
            ctx = _compliant_ctx(
                plot_area_sqm=3000.0,
                cop_provided_sqm=None,
            )
            report = evaluate_gdcr_compliance(ctx)
        cop_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.cop.required")
        self.assertEqual(cop_rule.status, INFO)

    def test_cop_passes_when_sufficient(self):
        """cop_provided >= 10% of plot_area: COP rule PASS."""
        with _patch_gdcr():
            ctx = _compliant_ctx(
                plot_area_sqm=3000.0,
                total_bua_sqm=8100.0,  # 3000 * 2.7
                footprint_area_sqm=900.0,
                ground_coverage_pct=30.0,
                cop_provided_sqm=320.0,  # > max(300, 200) = 300
            )
            report = evaluate_gdcr_compliance(ctx)
        cop_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.cop.required")
        self.assertEqual(cop_rule.status, PASS)

    def test_cop_fails_when_insufficient(self):
        """cop_provided < required: FAIL."""
        with _patch_gdcr():
            ctx = _compliant_ctx(
                plot_area_sqm=3000.0,
                total_bua_sqm=8100.0,
                footprint_area_sqm=900.0,
                ground_coverage_pct=30.0,
                cop_provided_sqm=100.0,  # < max(300, 200) = 300
            )
            report = evaluate_gdcr_compliance(ctx)
        cop_rule = next(r for r in report.rule_results if r.rule_id == "gdcr.cop.required")
        self.assertEqual(cop_rule.status, FAIL)


class RoadSideMarginRuleTests(TestCase):
    def test_road_side_margin_rule_present(self):
        """gdcr.margin.road_side must be present in rule results."""
        with _patch_gdcr():
            report = evaluate_gdcr_compliance(_compliant_ctx())
        ids = [r.rule_id for r in report.rule_results]
        self.assertIn("gdcr.margin.road_side", ids)

    def test_road_side_margin_info_when_not_provided(self):
        """Without road_margin_provided_m, rule is INFO."""
        with _patch_gdcr():
            ctx = _compliant_ctx(road_margin_provided_m=None)
            report = evaluate_gdcr_compliance(ctx)
        rule = next(r for r in report.rule_results if r.rule_id == "gdcr.margin.road_side")
        self.assertEqual(rule.status, INFO)

    def test_road_side_margin_pass(self):
        """Road margin provided >= required → PASS."""
        with _patch_gdcr():
            ctx = _compliant_ctx(road_margin_provided_m=8.0)  # >= 6.0 (18m road, H=27m)
            report = evaluate_gdcr_compliance(ctx)
        rule = next(r for r in report.rule_results if r.rule_id == "gdcr.margin.road_side")
        self.assertEqual(rule.status, PASS)

    def test_road_side_margin_fail(self):
        """Road margin below required → FAIL."""
        with _patch_gdcr():
            ctx = _compliant_ctx(road_margin_provided_m=2.0)  # < 6.0
            report = evaluate_gdcr_compliance(ctx)
        rule = next(r for r in report.rule_results if r.rule_id == "gdcr.margin.road_side")
        self.assertEqual(rule.status, FAIL)


class DebugTraceTests(TestCase):
    def test_debug_trace_is_present(self):
        """ComplianceReport.debug_trace must be non-empty."""
        with _patch_gdcr():
            ctx = _compliant_ctx(debug=True)
            report = evaluate_gdcr_compliance(ctx)
        self.assertTrue(len(report.debug_trace) > 0)

    def test_debug_trace_contains_fsi_values(self):
        """Debug trace must mention plot_area_sqm and max_fsi."""
        with _patch_gdcr():
            ctx = _compliant_ctx(debug=True, plot_area_sqm=1500.0)
            report = evaluate_gdcr_compliance(ctx)
        self.assertIn("plot_area_sqm", report.debug_trace)
        self.assertIn("max_fsi", report.debug_trace)
