"""
Phase 6.2 Multi-Variant Runner tests (plan Section 11).
Phase B: preset selection (subset execution).
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from architecture.multi_variant import (
    PRESET_ORDER,
    run_multi_variant,
    MultiVariantResult,
    VariantResult,
)
from architecture.multi_variant.presets import PRESETS, preset_to_advisor_like
from architecture.multi_variant.runner import _compute_ranking
from residential_layout.tests.test_floor_aggregation import _skeleton_one_zone


class TestMultiVariantPresets(TestCase):
    """Preset definitions and preset_to_advisor_like."""

    def test_preset_order_four(self):
        self.assertEqual(len(PRESET_ORDER), 4)
        self.assertEqual(PRESET_ORDER, ["SPACIOUS", "DENSE", "BALANCED", "BUDGET"])

    def test_presets_allowlist_only(self):
        for name, delta in PRESETS.items():
            for k in delta:
                self.assertIn(k, {"template_priority_order", "preferred_module_width", "storey_height_override", "density_bias", "constraint_flags"})

    def test_preset_to_advisor_like_returns_advisor_output(self):
        from ai_layer.schemas import AdvisorOutput
        for name in PRESET_ORDER:
            out = preset_to_advisor_like(name)
            self.assertIsInstance(out, AdvisorOutput)


class TestMultiVariantAllSucceed(TestCase):
    """All 4 presets produce BuildingLayoutContract; ranking has 4 entries."""

    def test_run_multi_variant_four_results(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = run_multi_variant(
            skeleton=sk,
            height_limit_m=6.0,
            plot_id="TP14_FP126",
            building_id="B0",
            ai_compare=False,
        )
        self.assertIsInstance(result, MultiVariantResult)
        self.assertEqual(len(result.variants), 4)
        self.assertEqual([v.preset_name for v in result.variants], PRESET_ORDER)
        success_count = sum(1 for v in result.variants if v.success_flag)
        self.assertEqual(success_count, 4, "All 4 presets should succeed with valid skeleton")
        self.assertEqual(len(result.ranking), 4)
        self.assertIsNone(result.comparison_note)
        # Phase A: when all succeed, best preset is first in ranking
        self.assertIsNotNone(result.best_preset_name)
        self.assertIsNotNone(result.best_variant_index)
        best_var = result.variants[result.best_variant_index]
        self.assertEqual(best_var.preset_name, result.best_preset_name)
        self.assertIsNotNone(best_var.building_contract)
        self.assertTrue(len(best_var.building_contract.floors) >= 1)


class TestMultiVariantRankingStable(TestCase):
    """Same inputs; two runs; ranking list identical."""

    def test_ranking_deterministic(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        r1 = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)
        r2 = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)
        self.assertEqual(r1.ranking, r2.ranking)

    def test_output_scalars_identical(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        r1 = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)
        r2 = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)
        for i, (v1, v2) in enumerate(zip(r1.variants, r2.variants)):
            self.assertEqual(v1.preset_name, v2.preset_name)
            self.assertEqual(v1.success_flag, v2.success_flag)
            if v1.building_contract_summary and v2.building_contract_summary:
                s1, s2 = v1.building_contract_summary, v2.building_contract_summary
                self.assertEqual(s1.total_units, s2.total_units)
                self.assertEqual(s1.total_floors, s2.total_floors)
                self.assertAlmostEqual(s1.building_efficiency, s2.building_efficiency, places=5)
                self.assertAlmostEqual(s1.total_unit_area, s2.total_unit_area, places=5)


class TestMultiVariantConfigIsolation(TestCase):
    """final_config_used differs per preset (no cross-preset leakage)."""

    def test_final_config_differs_per_preset(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)
        configs = [v.final_config_used for v in result.variants if v.success_flag]
        # At least SPACIOUS and BUDGET should have different preferred_module_width or storey
        pmw_values = [c.get("preferred_module_width") for c in configs]
        # SPACIOUS 4.2, DENSE 3.2, BALANCED None, BUDGET 3.2
        self.assertIn(4.2, pmw_values)
        self.assertIn(3.2, pmw_values)
        # BUDGET has storey_height_override 2.85
        sho_values = [c.get("storey_height_override") for c in configs]
        self.assertIn(2.85, sho_values)


class TestMultiVariantOneFails(TestCase):
    """When one preset fails (e.g. 5b raises), others still run; failed variant has success_flag False."""

    def test_one_preset_failure_recorded(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        call_count = [0]

        def fake_build_floor_layout(skeleton, floor_id="", module_width_m=None):
            call_count[0] += 1
            if call_count[0] == 2:
                from residential_layout import FloorAggregationError
                raise FloorAggregationError("mock fail", band_id=0, slice_index=0)
            from residential_layout import build_floor_layout
            return build_floor_layout(skeleton, floor_id=floor_id, module_width_m=module_width_m)

        with patch("architecture.multi_variant.runner.build_floor_layout", side_effect=fake_build_floor_layout):
            result = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)
        self.assertEqual(len(result.variants), 4)
        failed = [v for v in result.variants if not v.success_flag]
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0].failure_reason is not None)
        self.assertIsNone(failed[0].building_contract_summary)
        self.assertEqual(len(result.ranking), 4)
        # Ranking: 3 successful + 1 failed at end
        self.assertIn(failed[0].preset_name, result.ranking)


class TestRankingOneSuccess(TestCase):
    """If only one successful variant, ranking contains one element; no normalization instability."""

    def test_ranking_one_success(self):
        from ai_layer.schemas import ContractSummary
        single_summary = ContractSummary(
            building_id="B0",
            total_floors=1,
            total_units=5,
            total_unit_area=100.0,
            total_residual_area=10.0,
            building_efficiency=0.8,
            building_height_m=3.0,
            floors=[],
        )
        variants = [
            VariantResult("SPACIOUS", {}, None, False, "fail"),
            VariantResult("DENSE", {}, None, False, "fail"),
            VariantResult("BALANCED", {}, None, False, "fail"),
            VariantResult("BUDGET", {}, single_summary, True, None),
        ]
        ranking = _compute_ranking(variants)
        self.assertEqual(len(ranking), 4)
        self.assertEqual(ranking[0], "BUDGET")
        self.assertIn("SPACIOUS", ranking)
        self.assertIn("DENSE", ranking)
        self.assertIn("BALANCED", ranking)


class TestRankingAllFail(TestCase):
    """When all presets fail, ranking is still length 4 (all names in variant order); no crash."""

    def test_ranking_all_fail(self):
        variants = [
            VariantResult("SPACIOUS", {}, None, False, "fail"),
            VariantResult("DENSE", {}, None, False, "fail"),
            VariantResult("BALANCED", {}, None, False, "fail"),
            VariantResult("BUDGET", {}, None, False, "fail"),
        ]
        ranking = _compute_ranking(variants)
        self.assertEqual(len(ranking), 4)
        self.assertEqual(ranking, ["SPACIOUS", "DENSE", "BALANCED", "BUDGET"])


class TestMultiVariantBestExportSelection(TestCase):
    """Phase A: best preset selected; building contract stored; deterministic; no recomputation."""

    def test_multi_variant_best_export_selection(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = run_multi_variant(
            skeleton=sk,
            height_limit_m=6.0,
            plot_id="TP14_FP126",
            building_id="B0",
            ai_compare=False,
        )
        self.assertIsNotNone(result.best_preset_name)
        self.assertIsNotNone(result.best_variant_index)
        best_var = result.variants[result.best_variant_index]
        self.assertEqual(best_var.preset_name, result.best_preset_name)
        self.assertIsNotNone(best_var.building_contract, "Export must use stored contract, no recomputation")
        self.assertIsNotNone(best_var.building_contract_summary)
        self.assertTrue(len(best_var.building_contract.floors) >= 1)

    def test_multi_variant_deterministic_two_runs(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        r1 = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="TP14_FP126", ai_compare=False)
        r2 = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="TP14_FP126", ai_compare=False)
        self.assertEqual(r1.ranking, r2.ranking)
        self.assertEqual(r1.best_preset_name, r2.best_preset_name)
        self.assertEqual(r1.best_variant_index, r2.best_variant_index)


class TestMultiVariantAllFailExportFallback(TestCase):
    """Phase A: when all presets fail, best_preset_name is None; skeleton-only path; no crash."""

    def test_multi_variant_all_fail_export_fallback(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)

        def always_fail(*args, **kwargs):
            from residential_layout import FloorAggregationError
            raise FloorAggregationError("mock all fail", band_id=0, slice_index=0)

        with patch("architecture.multi_variant.runner.build_floor_layout", side_effect=always_fail):
            result = run_multi_variant(skeleton=sk, height_limit_m=6.0, plot_id="P1", ai_compare=False)

        self.assertIsNone(result.best_preset_name)
        self.assertIsNone(result.best_variant_index)
        self.assertEqual(len(result.variants), 4)
        for v in result.variants:
            self.assertFalse(v.success_flag)
            self.assertIsNone(v.building_contract)


class TestPresetSelectionSingle(TestCase):
    """Phase B: run with a single preset; one VariantResult; ranking length 1; best = that preset."""

    def test_single_preset_execution(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = run_multi_variant(
            skeleton=sk,
            height_limit_m=6.0,
            plot_id="TP14_FP126",
            building_id="B0",
            ai_compare=False,
            selected_presets=["SPACIOUS"],
        )
        self.assertEqual(len(result.variants), 1)
        self.assertEqual(result.variants[0].preset_name, "SPACIOUS")
        self.assertEqual(len(result.ranking), 1)
        self.assertEqual(result.ranking[0], "SPACIOUS")
        self.assertEqual(result.best_preset_name, "SPACIOUS")
        self.assertEqual(result.best_variant_index, 0)


class TestPresetSelectionSubset(TestCase):
    """Phase B: run with subset; order follows PRESET_ORDER; ranking length = subset size."""

    def test_subset_presets_execution(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        # User order DENSE, SPACIOUS → canonical order must be SPACIOUS, DENSE
        result = run_multi_variant(
            skeleton=sk,
            height_limit_m=6.0,
            plot_id="P1",
            ai_compare=False,
            selected_presets=["DENSE", "SPACIOUS"],
        )
        self.assertEqual(len(result.variants), 2)
        self.assertEqual(result.variants[0].preset_name, "SPACIOUS")
        self.assertEqual(result.variants[1].preset_name, "DENSE")
        self.assertEqual(len(result.ranking), 2)
        self.assertIsNotNone(result.best_preset_name)
        self.assertIn(result.best_preset_name, ("SPACIOUS", "DENSE"))

    def test_determinism_with_subset(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        subset = ["BALANCED", "DENSE"]
        r1 = run_multi_variant(
            skeleton=sk, height_limit_m=6.0, plot_id="P1",
            selected_presets=subset, ai_compare=False,
        )
        r2 = run_multi_variant(
            skeleton=sk, height_limit_m=6.0, plot_id="P1",
            selected_presets=subset, ai_compare=False,
        )
        self.assertEqual(r1.ranking, r2.ranking)
        self.assertEqual(r1.best_preset_name, r2.best_preset_name)


class TestPresetSelectionCLI(TestCase):
    """Phase B: CLI validation — invalid preset and --preset without --multi-variant."""

    def test_invalid_preset_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "generate_floorplan",
                    "--tp", 14, "--fp", 126, "--height", 16.5,
                    "--export-dir", tmp,
                    "--multi-variant", "--preset", "INVALID",
                )
            self.assertIn("Invalid preset", str(ctx.exception))
            self.assertIn("Valid:", str(ctx.exception))

    def test_without_multi_variant_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "generate_floorplan",
                    "--tp", 14, "--fp", 126, "--height", 16.5,
                    "--export-dir", tmp,
                    "--preset", "SPACIOUS",
                )
            self.assertIn("--multi-variant", str(ctx.exception))
