"""
Tests for architecture.feasibility.validation (Part 7).
"""
from django.test import TestCase

from architecture.feasibility.validation import (
    ValidationCheck,
    validate_aggregate_against_expected,
    TOLERANCE_FSI,
    TOLERANCE_GC_PCT,
)
from architecture.feasibility.aggregate import FeasibilityAggregate
from architecture.feasibility.plot_metrics import PlotMetrics
from architecture.feasibility.regulatory_metrics import RegulatoryMetrics
from architecture.feasibility.buildability_metrics import BuildabilityMetrics


def _make_aggregate(
    achieved_fsi=1.5,
    achieved_gc_pct=25.0,
    cop_provided_sqft=160.0,
    cop_required_sqft=163.0,
    frontage_m=13.3,
    height_band="HIGH_RISE",
):
    pm = PlotMetrics(
        plot_area_sqft=1633.0,
        plot_area_sqm=151.7,
        frontage_length_m=frontage_m,
        plot_depth_m=11.3,
        n_road_edges=1,
        is_corner_plot=False,
        shape_class="IRREGULAR",
        height_band_label=height_band,
    )
    rm = RegulatoryMetrics(
        base_fsi=1.8,
        max_fsi=2.7,
        achieved_fsi=achieved_fsi,
        fsi_utilization_pct=55.0,
        permissible_gc_pct=40.0,
        achieved_gc_pct=achieved_gc_pct,
        cop_required_sqft=cop_required_sqft,
        cop_provided_sqft=cop_provided_sqft,
        spacing_required_m=5.5,
        spacing_provided_m=None,
    )
    bm = BuildabilityMetrics(
        envelope_area_sqft=399.0,
        envelope_area_sqm=37.0,
        footprint_width_m=7.39,
        footprint_depth_m=4.95,
        footprint_area_sqft=350.0,
        core_area_sqm=12.0,
        remaining_usable_sqm=25.0,
        efficiency_ratio=0.42,
        core_ratio=0.08,
        circulation_ratio=0.05,
    )
    return FeasibilityAggregate(
        plot_metrics=pm,
        regulatory_metrics=rm,
        buildability_metrics=bm,
        compliance_summary=None,
        audit_metadata=None,
    )


class TestValidationChecks(TestCase):
    def test_fsi_pass_within_tolerance(self):
        agg = _make_aggregate(achieved_fsi=1.5)
        checks = validate_aggregate_against_expected(agg, expected_fsi=1.5)
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0].passed)

    def test_fsi_fail_outside_tolerance(self):
        agg = _make_aggregate(achieved_fsi=1.5)
        checks = validate_aggregate_against_expected(agg, expected_fsi=1.6)
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].passed)

    def test_gc_and_height_band(self):
        agg = _make_aggregate(achieved_gc_pct=25.0, height_band="HIGH_RISE")
        checks = validate_aggregate_against_expected(
            agg,
            expected_gc_pct=25.0,
            expected_height_band="HIGH_RISE",
        )
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(c.passed for c in checks))

    def test_height_band_fail(self):
        agg = _make_aggregate(height_band="HIGH_RISE")
        checks = validate_aggregate_against_expected(agg, expected_height_band="LOW_RISE")
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].passed)

    def test_skip_missing_expected(self):
        agg = _make_aggregate()
        checks = validate_aggregate_against_expected(agg)
        self.assertEqual(len(checks), 0)


class TestValidateAgainstExpectedJson(TestCase):
    """validate_aggregate_against_expected_json maps JSON keys to validation checks."""

    def test_json_maps_to_checks(self):
        from architecture.feasibility.validation import validate_aggregate_against_expected_json

        agg = _make_aggregate(achieved_fsi=1.5, achieved_gc_pct=25.0, height_band="HIGH_RISE")
        expected_dict = {
            "fsi_achieved": 1.5,
            "gc_achieved_pct": 25.0,
            "height_band": "HIGH_RISE",
        }
        checks = validate_aggregate_against_expected_json(agg, expected_dict)
        self.assertEqual(len(checks), 3)
        self.assertTrue(all(c.passed for c in checks))

    def test_json_validation_fail(self):
        from architecture.feasibility.validation import validate_aggregate_against_expected_json

        agg = _make_aggregate(height_band="HIGH_RISE")
        checks = validate_aggregate_against_expected_json(agg, {"height_band": "LOW_RISE"})
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0].passed)


class TestLoadExpectedCsv(TestCase):
    def test_load_expected_csv(self):
        import tempfile
        import os
        from architecture.feasibility.validation import load_expected_csv
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
            f.write("fp_number,expected_fsi,expected_gc_pct,expected_frontage_m,expected_height_band\n")
            f.write("101,1.21,24.5,13.3,HIGH_RISE\n")
            f.write("102,\n")
            path = f.name
        try:
            out = load_expected_csv(path)
            self.assertIn("101", out)
            self.assertEqual(out["101"]["expected_fsi"], 1.21)
            self.assertEqual(out["101"]["expected_height_band"], "HIGH_RISE")
        finally:
            os.unlink(path)
