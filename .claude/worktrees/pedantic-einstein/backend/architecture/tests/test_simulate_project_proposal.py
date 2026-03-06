"""
Integration tests for simulate_project_proposal management command.

Runs real pipeline (no mocks of core engines). Requires a Plot in the DB
for success paths; missing-plot and validation-failure paths are self-contained.
"""

from __future__ import annotations

import json
import os
import tempfile
from io import StringIO

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from tp_ingestion.models import Plot


def _create_test_plot(tp: int, fp: int, area_sqft: float = 2000.0):
    """Create and save a Plot with a rectangular polygon (DXF feet)."""
    from django.contrib.gis.geos import Polygon as GEOSPolygon

    # Rectangle so that polygon area matches area_sqft (e.g. 50 x 40 = 2000)
    side = area_sqft ** 0.5
    w, h = side * 1.2, side / 1.2
    geom = GEOSPolygon(((0, 0), (w, 0), (w, h), (0, h), (0, 0)), srid=0)
    plot = Plot(
        city="Test",
        tp_scheme=f"TP{tp}",
        fp_number=str(fp),
        area_excel=area_sqft,
        area_geometry=area_sqft,
        geom=geom,
        validation_status=True,
    )
    plot.save()
    return plot


class TestSimulateProjectProposalMissingPlot(TestCase):
    """Missing plot must fail cleanly (CommandError)."""

    def test_missing_plot_raises_command_error(self):
        # No plot created for TP99 FP99999
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "simulate_project_proposal",
                "--tp", "99",
                "--fp", "99999",
                "--height", "16.5",
                "--road-width", "12.0",
                "--zone", "R1",
                "--authority", "SUDA",
            )
        self.assertIn("Plot not found", str(ctx.exception))


class TestSimulateProjectProposalValidRun(TestCase):
    """Valid compliant scenario: create plot, run full pipeline, assert summary."""

    def setUp(self):
        self.tp, self.fp = 0, 9001
        _create_test_plot(self.tp, self.fp, area_sqft=2000.0)

    def tearDown(self):
        Plot.objects.filter(city="Test", tp_scheme=f"TP{self.tp}", fp_number=str(self.fp)).delete()

    def test_valid_compliant_scenario(self):
        out = StringIO()
        call_command(
            "simulate_project_proposal",
            "--tp", str(self.tp),
            "--fp", str(self.fp),
            "--height", "16.5",
            "--road-width", "12.0",
            "--zone", "R1",
            "--authority", "SUDA",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("PROJECT SIMULATION SUMMARY", output)
        self.assertIn("FSI", output)
        self.assertIn("GC", output)
        self.assertIn("Compliance:", output)


class TestSimulateProjectProposalExpectedJson(TestCase):
    """Expected JSON validation: success and failure."""

    def setUp(self):
        self.tp, self.fp = 0, 9002
        _create_test_plot(self.tp, self.fp, area_sqft=2000.0)

    def tearDown(self):
        Plot.objects.filter(city="Test", tp_scheme=f"TP{self.tp}", fp_number=str(self.fp)).delete()

    def test_expected_json_validation_success(self):
        # Use height_band that the pipeline will produce for H=16.5 (HIGH_RISE)
        expected = {
            "height_band": "HIGH_RISE",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(expected, f)
            path = f.name
        try:
            out = StringIO()
            call_command(
                "simulate_project_proposal",
                "--tp", str(self.tp),
                "--fp", str(self.fp),
                "--height", "16.5",
                "--road-width", "12.0",
                "--zone", "R1",
                "--authority", "SUDA",
                "--expected-json", path,
                stdout=out,
            )
            self.assertIn("Validation:", out.getvalue())
        finally:
            os.unlink(path)

    def test_expected_json_validation_failure(self):
        # Expect wrong height band so validation fails
        expected = {"height_band": "LOW_RISE"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(expected, f)
            path = f.name
        try:
            out = StringIO()
            call_command(
                "simulate_project_proposal",
                "--tp", str(self.tp),
                "--fp", str(self.fp),
                "--height", "16.5",
                "--road-width", "12.0",
                "--zone", "R1",
                "--authority", "SUDA",
                "--expected-json", path,
                stdout=out,
            )
            output = out.getvalue()
            self.assertIn("Validation:", output)
            self.assertIn("FAIL", output)
        finally:
            os.unlink(path)


class TestSimulateProjectProposalStrictMode(TestCase):
    """Strict mode: validation failure with --strict raises CommandError."""

    def setUp(self):
        self.tp, self.fp = 0, 9003
        _create_test_plot(self.tp, self.fp, area_sqft=2000.0)

    def tearDown(self):
        Plot.objects.filter(city="Test", tp_scheme=f"TP{self.tp}", fp_number=str(self.fp)).delete()

    def test_strict_mode_validation_failure_raises(self):
        expected = {"height_band": "LOW_RISE"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(expected, f)
            path = f.name
        try:
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "simulate_project_proposal",
                    "--tp", str(self.tp),
                    "--fp", str(self.fp),
                    "--height", "16.5",
                    "--road-width", "12.0",
                    "--zone", "R1",
                    "--authority", "SUDA",
                    "--expected-json", path,
                    "--strict",
                )
            self.assertIn("validation failed", str(ctx.exception).lower())
        finally:
            os.unlink(path)


class TestSimulateProjectProposalExport(TestCase):
    """Export dir produces feasibility_summary.json, compliance_summary.json, validation_result.json."""

    def setUp(self):
        self.tp, self.fp = 0, 9004
        _create_test_plot(self.tp, self.fp, area_sqft=2000.0)

    def tearDown(self):
        Plot.objects.filter(city="Test", tp_scheme=f"TP{self.tp}", fp_number=str(self.fp)).delete()

    def test_export_dir_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as export_dir:
            call_command(
                "simulate_project_proposal",
                "--tp", str(self.tp),
                "--fp", str(self.fp),
                "--height", "16.5",
                "--road-width", "12.0",
                "--zone", "R1",
                "--authority", "SUDA",
                "--export-dir", export_dir,
            )
            self.assertTrue(os.path.isfile(os.path.join(export_dir, "feasibility_summary.json")))
            self.assertTrue(os.path.isfile(os.path.join(export_dir, "compliance_summary.json")))
            with open(os.path.join(export_dir, "feasibility_summary.json"), encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("plot_metrics", data)
            self.assertIn("regulatory_metrics", data)
            self.assertIn("compliance_summary", data)
