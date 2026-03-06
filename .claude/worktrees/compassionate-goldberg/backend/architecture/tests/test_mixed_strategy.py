"""
Tests for Phase 1 mixed development strategy: band generator, floor resolver,
FSI validation, evaluator, service, and CLI. Uses minimal SlabMetrics and mocks.
"""

from __future__ import annotations

from django.test import TestCase

from development_strategy.slab_metrics import SlabMetrics
from development_strategy.strategy_generator import UnitType
from development_strategy.mixed_generator import (
    BandCombination,
    generate_band_combinations,
    MAX_UNITS_PER_BAND,
    MAX_COMBINATIONS_PER_BAND,
)
from development_strategy.mixed_resolver import (
    FloorCombination,
    MixedDevelopmentStrategy,
    resolve_floor_combinations,
)
from development_strategy.evaluator import (
    EvaluatorWeights,
    evaluate_mixed_strategies,
    get_mixed_evaluator_weights,
    MixedStrategyEvaluation,
)
from development_strategy.service import resolve_mixed_development_strategy

from floor_skeleton.models import AXIS_WIDTH_DOMINANT, AXIS_DEPTH_DOMINANT


def _slab_single_band(repeat_m: float, depth_m: float, axis: str = AXIS_WIDTH_DOMINANT) -> SlabMetrics:
    """One band: width and length according to axis (width=repeat for WIDTH_DOMINANT)."""
    if axis == AXIS_WIDTH_DOMINANT:
        widths, lengths = [repeat_m], [depth_m]
    else:
        widths, lengths = [depth_m], [repeat_m]
    return SlabMetrics(
        gross_slab_area_sqm=repeat_m * depth_m,
        core_area_sqm=10.0,
        corridor_area_sqm=5.0,
        net_usable_area_sqm=repeat_m * depth_m - 15.0,
        efficiency_ratio=0.8,
        band_lengths_m=lengths,
        band_widths_m=widths,
        band_orientation_axes=[axis],
    )


def _slab_two_bands(
    w1: float, d1: float, w2: float, d2: float,
    axis1: str = AXIS_WIDTH_DOMINANT,
    axis2: str = AXIS_WIDTH_DOMINANT,
) -> SlabMetrics:
    """Two bands for double-loaded."""
    return SlabMetrics(
        gross_slab_area_sqm=w1 * d1 + w2 * d2,
        core_area_sqm=15.0,
        corridor_area_sqm=8.0,
        net_usable_area_sqm=w1 * d1 + w2 * d2 - 23.0,
        efficiency_ratio=0.75,
        band_lengths_m=[d1, d2],
        band_widths_m=[w1, w2],
        band_orientation_axes=[axis1, axis2],
    )


class TestBandGeneratorSmallSlabStudioOnly(TestCase):
    """Small band: only small unit types fit; total_units capped."""

    def test_small_slab_capped(self):
        # Narrow band: few units, all combos respect MAX_UNITS_PER_BAND.
        slab = _slab_single_band(4.0, 5.0)
        combos = generate_band_combinations(slab, 0)
        self.assertGreater(len(combos), 0)
        for bc in combos:
            self.assertLessEqual(bc.total_units, MAX_UNITS_PER_BAND)
            self.assertLessEqual(len(bc.units), 3)


class TestBandGeneratorMediumSlabMultiType(TestCase):
    """Band allows 1BHK and 2BHK; expect homogeneous and mixed combos."""

    def test_has_homogeneous_and_mixed(self):
        # Repeat 7m, depth 7m: only 1*2BHK fits; 1*1BHK+1*2BHK (7m) fits. 2*2BHK (8m) does not, so (2,125) mixed is non-dominated.
        slab = _slab_single_band(7.0, 7.0)
        combos = generate_band_combinations(slab, 0)
        self.assertGreater(len(combos), 0)
        self.assertLessEqual(len(combos), MAX_COMBINATIONS_PER_BAND)
        types_seen = set()
        for bc in combos:
            for t in bc.units:
                types_seen.add(t)
        self.assertIn(UnitType.BHK2, types_seen, "2BHK fits 7x7 band and should appear in some combo")
        mixed = [bc for bc in combos if len(bc.units) >= 2]
        self.assertGreater(len(mixed), 0, "expect at least one 2-type combo (e.g. 1*1BHK+1*2BHK)")


class TestBandGeneratorParetoPruning(TestCase):
    """Dominated combos (lower BUA and lower units) are pruned."""

    def test_pareto_removes_dominated(self):
        slab = _slab_single_band(20.0, 8.0)
        combos = generate_band_combinations(slab, 0)
        for i, a in enumerate(combos):
            for b in combos:
                if a is b:
                    continue
                if b.bua_per_floor_sqm >= a.bua_per_floor_sqm and b.total_units >= a.total_units:
                    if b.bua_per_floor_sqm > a.bua_per_floor_sqm or b.total_units > a.total_units:
                        self.fail("Dominated combo left in list")
        self.assertGreater(len(combos), 0)


class TestSingleBandFloorCombination(TestCase):
    """Single-band skeleton: FloorCombination list matches band combos."""

    def test_one_to_one(self):
        slab = _slab_single_band(10.0, 6.0)
        band_combos = generate_band_combinations(slab, 0)
        floor_combos = resolve_floor_combinations([band_combos])
        self.assertEqual(len(floor_combos), len(band_combos))
        for fc in floor_combos:
            self.assertIsNone(fc.band_b)
            self.assertEqual(fc.total_units, fc.band_a.total_units)
            self.assertEqual(fc.bua_per_floor_sqm, fc.band_a.bua_per_floor_sqm)


class TestDoubleLoadedDeduplication(TestCase):
    """Two bands: dedupe by mix_signature; cap 100."""

    def test_cap_and_dedupe(self):
        slab = _slab_two_bands(10.0, 6.0, 10.0, 6.0)
        a_list = generate_band_combinations(slab, 0)
        b_list = generate_band_combinations(slab, 1)
        floor_combos = resolve_floor_combinations([a_list, b_list])
        self.assertLessEqual(len(floor_combos), 100)
        sigs = [fc.mix_signature for fc in floor_combos]
        self.assertEqual(len(sigs), len(set(sigs)), "duplicate mix_signature should be deduped")


class TestFSIRejection(TestCase):
    """Feasible mixed strategies respect FSI cap."""

    def test_feasible_respects_fsi(self):
        from architecture.tests.test_development_strategy import _make_skeleton, _make_feasibility_aggregate
        plot_area_sqm = 200.0
        max_fsi = 1.5
        max_total_bua = plot_area_sqm * max_fsi
        skeleton = _make_skeleton(12.0, 7.0, [12.0], [7.0])
        agg = _make_feasibility_aggregate(plot_area_sqm=plot_area_sqm, max_fsi=max_fsi, num_floors_estimated=4)
        best, top = resolve_mixed_development_strategy(skeleton, agg, 14.0, max_fsi, 3.0, top_k=5)
        if best is not None:
            self.assertLessEqual(best.strategy.total_bua_sqm, max_total_bua * 1.001)


class TestDeterministicRanking(TestCase):
    """Ranking is deterministic over multiple runs."""

    def test_deterministic(self):
        slab = _slab_single_band(15.0, 8.0)
        strategies = [
            MixedDevelopmentStrategy(
                mix={UnitType.BHK2: 2, UnitType.BHK3: 1},
                floors=5,
                total_units=15,
                avg_unit_area_sqm=85.0,
                total_bua_sqm=1275.0,
                fsi_utilization=0.9,
                efficiency_ratio=0.75,
                mix_diversity_score=0.5,
                luxury_bias_score=0.77,
                density_bias_score=3.0,
                feasible=True,
            ),
            MixedDevelopmentStrategy(
                mix={UnitType.BHK3: 3},
                floors=5,
                total_units=15,
                avg_unit_area_sqm=110.0,
                total_bua_sqm=1650.0,
                fsi_utilization=0.95,
                efficiency_ratio=0.82,
                mix_diversity_score=0.0,
                luxury_bias_score=1.0,
                density_bias_score=3.0,
                feasible=True,
            ),
        ]
        out1 = evaluate_mixed_strategies(strategies, slab)
        out2 = evaluate_mixed_strategies(strategies, slab)
        self.assertEqual(len(out1), len(out2))
        for a, b in zip(out1, out2):
            self.assertEqual(a.rank, b.rank)
            self.assertAlmostEqual(a.score, b.score)


class TestDiversityAndLuxuryTradeoff(TestCase):
    """Changing weights changes which candidate ranks first."""

    def test_weight_flip(self):
        slab = _slab_single_band(20.0, 8.0)
        luxury = MixedDevelopmentStrategy(
            mix={UnitType.BHK3: 3},
            floors=5,
            total_units=15,
            avg_unit_area_sqm=110.0,
            total_bua_sqm=1650.0,
            fsi_utilization=0.9,
            efficiency_ratio=0.7,
            mix_diversity_score=0.0,
            luxury_bias_score=1.0,
            density_bias_score=3.0,
            feasible=True,
        )
        diverse = MixedDevelopmentStrategy(
            mix={UnitType.BHK1: 1, UnitType.BHK2: 1, UnitType.BHK3: 1},
            floors=5,
            total_units=15,
            avg_unit_area_sqm=78.33,
            total_bua_sqm=1175.0,
            fsi_utilization=0.8,
            efficiency_ratio=0.65,
            mix_diversity_score=1.0,
            luxury_bias_score=0.71,
            density_bias_score=3.0,
            feasible=True,
        )
        w_lux = EvaluatorWeights(w_fsi=0.15, w_efficiency=0.15, w_total_units=0.1, w_mix_diversity=0.1, w_luxury_bias=0.5)
        w_div = EvaluatorWeights(w_fsi=0.15, w_efficiency=0.15, w_total_units=0.1, w_mix_diversity=0.5, w_luxury_bias=0.1)
        out_lux = evaluate_mixed_strategies([luxury, diverse], slab, w_lux)
        out_div = evaluate_mixed_strategies([luxury, diverse], slab, w_div)
        self.assertGreater(len(out_lux), 0)
        self.assertGreater(len(out_div), 0)
        self.assertEqual(out_lux[0].strategy.mix_diversity_score, 0.0, "luxury weights: homogeneous should rank first")
        self.assertEqual(out_div[0].strategy.mix_diversity_score, 1.0, "diversity weights: 3-type mix should rank first")


class TestMixedServiceReturnsBest(TestCase):
    """resolve_mixed_development_strategy returns best and top_k."""

    def test_returns_best_and_list(self):
        from architecture.tests.test_development_strategy import _make_skeleton, _make_feasibility_aggregate
        skeleton = _make_skeleton(15.0, 12.0, [15.0], [12.0], core_area=20.0, corridor_area=10.0)
        agg = _make_feasibility_aggregate(plot_area_sqm=500.0, max_fsi=2.7, num_floors_estimated=5)
        best, top = resolve_mixed_development_strategy(skeleton, agg, 16.5, 2.7, 3.0, top_k=10)
        if best is not None:
            self.assertEqual(best, top[0])
            self.assertLessEqual(len(top), 10)
