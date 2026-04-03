"""
Tests for feasibility aggregation (buildability, regulatory, service).
"""
from django.test import TestCase

from architecture.feasibility.buildability_metrics import (
    BuildabilityMetrics,
    build_buildability_metrics,
)
from architecture.feasibility.regulatory_metrics import (
    RegulatoryMetrics,
    build_regulatory_metrics,
    COP_REQUIRED_FRACTION,
)
from architecture.feasibility.compliance_summary import (
    ComplianceSummary,
    build_compliance_summary_from_rule_results,
)
from rules_engine.rules.base import RuleResult, PASS, FAIL


class TestBuildabilityMetrics(TestCase):
    def test_build_buildability_metrics(self):
        m = build_buildability_metrics(
            envelope_area_sqft=400.0,
            footprint_width_m=7.0,
            footprint_depth_m=5.0,
            footprint_area_sqft=350.0,
            core_area_sqm=12.0,
            remaining_usable_sqm=25.0,
            efficiency_ratio=0.45,
            core_ratio=0.08,
            circulation_ratio=0.05,
        )
        self.assertIsInstance(m, BuildabilityMetrics)
        self.assertEqual(m.envelope_area_sqft, 400.0)
        self.assertEqual(m.footprint_width_m, 7.0)
        # envelope_area_sqft is DXF plane area (m²): convert 1:1 to sqm.
        self.assertAlmostEqual(m.envelope_area_sqm, 400.0, places=4)
        self.assertEqual(m.efficiency_ratio, 0.45)

    def test_build_without_skeleton_ratios(self):
        m = build_buildability_metrics(
            envelope_area_sqft=300.0,
            footprint_width_m=6.0,
            footprint_depth_m=4.0,
            footprint_area_sqft=250.0,
            core_area_sqm=10.0,
            remaining_usable_sqm=20.0,
        )
        self.assertEqual(m.efficiency_ratio, 0.0)
        self.assertEqual(m.core_ratio, 0.0)
        self.assertEqual(m.circulation_ratio, 0.0)


class TestRegulatoryMetrics(TestCase):
    def test_build_regulatory_metrics(self):
        # Plot must be above COP threshold (~2000 m²); 50k sq.ft ≈ 4645 m².
        plot_area_sqft = 50000.0
        total_bua_sqft = 100000.0
        m = build_regulatory_metrics(
            plot_area_sqft=plot_area_sqft,
            total_bua_sqft=total_bua_sqft,
            achieved_gc_pct=25.0,
            cop_provided_sqft=200.0,
            spacing_required_m=5.5,
            spacing_provided_m=6.0,
        )
        self.assertIsInstance(m, RegulatoryMetrics)
        self.assertGreater(m.achieved_fsi, 0)
        self.assertAlmostEqual(m.achieved_fsi, total_bua_sqft / plot_area_sqft, places=4)
        self.assertGreater(m.cop_required_sqft, 0.0)
        self.assertAlmostEqual(
            m.cop_required_sqft, plot_area_sqft * COP_REQUIRED_FRACTION, places=1
        )
        self.assertEqual(m.spacing_provided_m, 6.0)

    def test_fsi_utilization(self):
        m = build_regulatory_metrics(
            plot_area_sqft=1000.0,
            total_bua_sqft=2700.0,
            achieved_gc_pct=40.0,
            cop_provided_sqft=100.0,
            spacing_required_m=5.0,
        )
        self.assertAlmostEqual(m.achieved_fsi, 2.7, places=2)
        self.assertGreater(m.fsi_utilization_pct, 0)


class TestComplianceSummary(TestCase):
    def test_build_from_rule_results(self):
        results = [
            RuleResult("gdcr.fsi.base", "GDCR", "fsi", "Base FSI", PASS, required_value=1.8, actual_value=1.5),
            RuleResult("gdcr.fsi.max", "GDCR", "fsi", "Max FSI", FAIL, required_value=2.7, actual_value=3.0),
        ]
        summary = build_compliance_summary_from_rule_results(results)
        self.assertIsInstance(summary, ComplianceSummary)
        self.assertEqual(summary.total, 2)
        self.assertEqual(summary.pass_count, 1)
        self.assertEqual(summary.fail_count, 1)
        self.assertFalse(summary.compliant)
        self.assertEqual(len(summary.results), 2)
