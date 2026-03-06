"""
Phase C — End-to-End Stability Hardening (CLI-level smoke tests).

Validates full pipeline runs, multi-variant ranking/export, subset execution,
determinism, and graceful all-fail. No engine/ranking/AI logic changes.
Uses temp directories; no AI keys required.
Requires a Plot in the test DB for TP14 FP126 (created in setUp).
"""

from __future__ import annotations

import os
import re
import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from tp_ingestion.models import Plot


# Known-good plot for E2E (TP14 FP126 — DOUBLE_LOADED, two bands).
TP, FP, HEIGHT = 14, 126, 16.5
E2E_CITY = "E2E_Test"


def _create_e2e_plot():
    """Create a Plot for TP14 FP126 so generate_floorplan can run (Steps 1–6)."""
    from django.contrib.gis.geos import Polygon as GEOSPolygon
    # Rectangle large enough for envelope + placement + skeleton (feet; pipeline uses plot geom).
    area_sqft = 9600.0
    side = area_sqft ** 0.5
    w, h = side * 1.2, side / 1.2
    geom = GEOSPolygon(((0, 0), (w, 0), (w, h), (0, h), (0, 0)), srid=0)
    plot = Plot(
        city=E2E_CITY,
        tp_scheme=f"TP{TP}",
        fp_number=str(FP),
        area_excel=area_sqft,
        area_geometry=area_sqft,
        geom=geom,
        validation_status=True,
        road_width_m=15.0,
        road_edges="0",
    )
    plot.save()
    return plot


def _run_generate_floorplan(export_dir: str, **kwargs) -> tuple[str, str]:
    """Run generate_floorplan; return (stdout, stderr)."""
    out = StringIO()
    err = StringIO()
    call_command(
        "generate_floorplan",
        "--tp", TP,
        "--fp", FP,
        "--height", str(HEIGHT),
        "--export-dir", export_dir,
        stdout=out,
        stderr=err,
        **kwargs,
    )
    return out.getvalue(), err.getvalue()


def _dxf_path(export_dir: str) -> str:
    """Expected DXF path for TP14 FP126 and default height."""
    return os.path.join(export_dir, f"TP{TP}_FP{FP}_H{HEIGHT}.dxf")


class E2EPipelineTestCase(TestCase):
    """Base: ensure Plot TP14 FP126 exists for generate_floorplan."""

    def setUp(self):
        super().setUp()
        _create_e2e_plot()

    def tearDown(self):
        Plot.objects.filter(city=E2E_CITY, tp_scheme=f"TP{TP}", fp_number=str(FP)).delete()
        super().tearDown()


class TestSingleRunE2E(E2EPipelineTestCase):
    """Single-run pipeline completes; DXF exists; no multi-variant/AI logs."""

    def test_single_run_e2e_known_good_plot(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = _run_generate_floorplan(tmp)
            self.assertIn("[6] DXF Exported", out)
            self.assertNotIn("[MULTI]", out)
            self.assertNotIn("[AI Evaluator]", out)
            path = _dxf_path(tmp)
            self.assertTrue(os.path.isfile(path), f"DXF file should exist: {path}")


class TestMultiVariantFullRunE2E(E2EPipelineTestCase):
    """Multi-variant full run: ranking, best preset, layout DXF; no skeleton fallback."""

    def test_multi_variant_full_run_e2e(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = _run_generate_floorplan(tmp, multi_variant=True)
            self.assertIn("[MULTI] Ranking:", out)
            self.assertIn("Best preset selected:", out)
            self.assertIn("[MULTI] Exporting layout for best preset:", out)
            self.assertNotIn("[MULTI] All presets failed. Exporting skeleton only.", out)
            path = _dxf_path(tmp)
            self.assertTrue(os.path.isfile(path), f"Layout DXF should exist: {path}")


class TestMultiVariantSubsetE2E(E2EPipelineTestCase):
    """Multi-variant with --presets SPACIOUS,DENSE: only those two; ranking length 2."""

    def test_multi_variant_subset_e2e(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = _run_generate_floorplan(
                tmp, multi_variant=True, presets="SPACIOUS,DENSE"
            )
            self.assertIn("[MULTI] Preset: SPACIOUS", out)
            self.assertIn("[MULTI] Preset: DENSE", out)
            self.assertNotIn("[MULTI] Preset: BALANCED", out)
            self.assertNotIn("[MULTI] Preset: BUDGET", out)
            ranking_lines = [line for line in out.splitlines() if re.match(r"\[MULTI\] \d+\. \w+", line)]
            self.assertEqual(len(ranking_lines), 2)
            self.assertIn("[6] DXF Exported", out)
            path = _dxf_path(tmp)
            self.assertTrue(os.path.isfile(path), f"DXF should exist: {path}")


class TestMultiVariantAllFailGracefulE2E(E2EPipelineTestCase):
    """All presets fail: no crash; skeleton-only message; skeleton DXF exists."""

    def test_multi_variant_all_fail_graceful(self):
        from architecture.multi_variant import MultiVariantResult, VariantResult
        from architecture.multi_variant.presets import PRESET_ORDER

        all_fail_result = MultiVariantResult(
            plot_id=f"TP{TP}_FP{FP}",
            building_id="B0",
            variants=[
                VariantResult(preset_name=p, final_config_used={}, building_contract_summary=None, success_flag=False, failure_reason="mock")
                for p in PRESET_ORDER
            ],
            ranking=PRESET_ORDER,
            comparison_note=None,
            best_preset_name=None,
            best_variant_index=None,
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch("architecture.multi_variant.run_multi_variant", return_value=all_fail_result):
                out, err = _run_generate_floorplan(tmp, multi_variant=True)
            self.assertIn("[MULTI] All presets failed. Exporting skeleton only.", out)
            path = _dxf_path(tmp)
            self.assertTrue(os.path.isfile(path), f"Skeleton DXF should exist: {path}")


def _parse_multi_variant_output(out: str) -> dict:
    """Extract ranking, best preset, and first variant units for determinism comparison."""
    ranking = []
    for line in out.splitlines():
        m = re.match(r"\[MULTI\] (\d+)\. (\w+)", line)
        if m:
            ranking.append((int(m.group(1)), m.group(2)))
    best_preset = None
    for line in out.splitlines():
        if "Best preset selected:" in line:
            best_preset = line.split("Best preset selected:")[-1].strip()
            break
    total_units_from_variant = None
    for line in out.splitlines():
        if "[MULTI] Preset:" in line and "Units:" in line:
            m = re.search(r"Units: (\d+)", line)
            if m:
                total_units_from_variant = int(m.group(1))
                break
    return {"ranking": ranking, "best_preset": best_preset, "total_units": total_units_from_variant}


class TestMultiVariantDeterministicCLI(E2EPipelineTestCase):
    """Two identical multi-variant runs produce identical ranking and best preset."""

    def test_multi_variant_deterministic_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out1, _ = _run_generate_floorplan(tmp, multi_variant=True)
            out2, _ = _run_generate_floorplan(tmp, multi_variant=True)
        p1 = _parse_multi_variant_output(out1)
        p2 = _parse_multi_variant_output(out2)
        self.assertEqual(p1["ranking"], p2["ranking"], "Ranking must be identical across runs")
        self.assertEqual(p1["best_preset"], p2["best_preset"], "Best preset must be identical")
        if p1["total_units"] is not None and p2["total_units"] is not None:
            self.assertEqual(p1["total_units"], p2["total_units"], "Variant total_units must be identical")


# Golden metrics for E2E synthetic plot (TP14 FP126 shape, height 16.5) from single-run [5c].
# If engine logic changes, update after verifying; purpose is regression protection.
GOLDEN_TP14_FP126 = {
    "total_floors": 5,
    "total_units": 10,
    "building_efficiency": 0.121,  # 12.1% from E2E synthetic plot
}


def _parse_5c_metrics(out: str) -> dict | None:
    """Parse [5c] Building Layout line: Floors, Total Units, Efficiency."""
    for line in out.splitlines():
        if "[5c] Building Layout" not in line:
            continue
        m_floors = re.search(r"Floors: (\d+)", line)
        m_units = re.search(r"Total Units: (\d+)", line)
        m_eff = re.search(r"Efficiency: ([\d.]+)%", line)
        if m_floors and m_units and m_eff:
            eff_pct = float(m_eff.group(1))
            return {
                "total_floors": int(m_floors.group(1)),
                "total_units": int(m_units.group(1)),
                "building_efficiency": round(eff_pct / 100.0, 3),
            }
    return None


class TestGoldenMetricsE2E(E2EPipelineTestCase):
    """Minimal golden metrics guard for known-good plot (TP14 FP126)."""

    def test_golden_metrics_single_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = _run_generate_floorplan(tmp)
        metrics = _parse_5c_metrics(out)
        self.assertIsNotNone(metrics, "Should have [5c] Building Layout line")
        self.assertEqual(metrics["total_floors"], GOLDEN_TP14_FP126["total_floors"])
        self.assertEqual(metrics["total_units"], GOLDEN_TP14_FP126["total_units"])
        self.assertEqual(metrics["building_efficiency"], GOLDEN_TP14_FP126["building_efficiency"])
