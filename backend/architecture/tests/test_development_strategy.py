"""
Tests for development_strategy: slab metrics, strategy generation,
evaluation, and service. Uses minimal FloorSkeleton and FeasibilityAggregate
(no DB, no full pipeline).
"""

from __future__ import annotations

from shapely.geometry import box as shapely_box

from django.test import TestCase

from floor_skeleton.models import (
    FloorSkeleton,
    UnitZone,
    AXIS_WIDTH_DOMINANT,
    AXIS_DEPTH_DOMINANT,
)
from architecture.feasibility.aggregate import FeasibilityAggregate
from architecture.feasibility.plot_metrics import PlotMetrics
from architecture.feasibility.regulatory_metrics import RegulatoryMetrics
from architecture.feasibility.buildability_metrics import BuildabilityMetrics
from architecture.feasibility.aggregate import AuditMetadata

from development_strategy.slab_metrics import SlabMetrics, compute_slab_metrics
from development_strategy.strategy_generator import (
    UnitType,
    DevelopmentStrategy,
    generate_strategies,
)
from development_strategy.evaluator import (
    StrategyEvaluation,
    evaluate_strategies,
    get_evaluator_weights,
)
from development_strategy.service import resolve_development_strategy


def _make_skeleton(
    footprint_w: float,
    footprint_d: float,
    unit_zone_widths: list[float],
    unit_zone_depths: list[float],
    orientation_axes: list[str] | None = None,
    core_area: float = 10.0,
    corridor_area: float = 5.0,
) -> FloorSkeleton:
    """Build a minimal FloorSkeleton with given unit zone dimensions."""
    fp = shapely_box(0, 0, footprint_w, footprint_d)
    core = shapely_box(0, 0, 2, 2)  # placeholder
    corr = shapely_box(0, 0, 1, 1)  # placeholder
    unit_area = sum(w * d for w, d in zip(unit_zone_widths, unit_zone_depths))
    fp_area = footprint_w * footprint_d
    eff = unit_area / fp_area if fp_area > 0 else 0.0
    axes = orientation_axes or [AXIS_WIDTH_DOMINANT] * len(unit_zone_widths)
    unit_zones = []
    x0 = 0.0
    for w, d, ax in zip(unit_zone_widths, unit_zone_depths, axes):
        poly = shapely_box(x0, 0, x0 + w, d)
        unit_zones.append(
            UnitZone(polygon=poly, orientation_axis=ax, zone_width_m=w, zone_depth_m=d)
        )
        x0 += w
    area_summary = {
        "footprint_area_sqm": round(fp_area, 4),
        "core_area_sqm": core_area,
        "corridor_area_sqm": corridor_area,
        "unit_area_sqm": round(unit_area, 4),
        "efficiency_ratio": round(eff, 6),
        "unit_band_widths": [round(x, 3) for x in unit_zone_widths],
        "unit_band_depths": [round(x, 3) for x in unit_zone_depths],
    }
    return FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=corr,
        unit_zones=unit_zones,
        pattern_used="SINGLE_LOADED",
        placement_label="END_CORE_LEFT",
        area_summary=area_summary,
        efficiency_ratio=eff,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )


def _make_feasibility_aggregate(
    plot_area_sqm: float = 200.0,
    max_fsi: float = 2.7,
    num_floors_estimated: int | None = 5,
    storey_height_used_m: float | None = 3.0,
) -> FeasibilityAggregate:
    """Minimal FeasibilityAggregate for service tests."""
    pm = PlotMetrics(
        plot_area_sqft=plot_area_sqm * 10.76,
        plot_area_sqm=plot_area_sqm,
        frontage_length_m=10.0,
        plot_depth_m=20.0,
        n_road_edges=1,
        is_corner_plot=False,
        shape_class="RECTANGULAR",
        height_band_label="MID_RISE",
    )
    rm = RegulatoryMetrics(
        base_fsi=1.8,
        max_fsi=max_fsi,
        achieved_fsi=1.5,
        fsi_utilization_pct=55.0,
        permissible_gc_pct=40.0,
        achieved_gc_pct=35.0,
        cop_required_sqft=200.0,
        cop_provided_sqft=220.0,
        spacing_required_m=5.0,
        spacing_provided_m=None,
    )
    bm = BuildabilityMetrics(
        envelope_area_sqft=500.0,
        envelope_area_sqm=46.5,
        footprint_width_m=10.0,
        footprint_depth_m=8.0,
        footprint_area_sqft=400.0,
        core_area_sqm=12.0,
        remaining_usable_sqm=68.0,
        efficiency_ratio=0.72,
        core_ratio=0.15,
        circulation_ratio=0.08,
    )
    return FeasibilityAggregate(
        plot_metrics=pm,
        regulatory_metrics=rm,
        buildability_metrics=bm,
        compliance_summary=None,
        audit_metadata=AuditMetadata(
            tp_scheme="TP1",
            fp_number="1",
            building_height_m=15.0,
            road_width_m=12.0,
        ),
        storey_height_used_m=storey_height_used_m,
        num_floors_estimated=num_floors_estimated,
    )


class TestSlabMetrics(TestCase):
    def test_compute_slab_metrics(self):
        sk = _make_skeleton(
            20.0, 15.0,
            unit_zone_widths=[12.0], unit_zone_depths=[10.0],
        )
        slab = compute_slab_metrics(sk)
        self.assertIsInstance(slab, SlabMetrics)
        self.assertEqual(slab.gross_slab_area_sqm, 300.0)
        self.assertEqual(slab.net_usable_area_sqm, 120.0)
        self.assertEqual(slab.efficiency_ratio, 120.0 / 300.0)
        self.assertEqual(len(slab.band_widths_m), 1)
        self.assertEqual(len(slab.band_lengths_m), 1)
        self.assertEqual(len(slab.band_orientation_axes), 1)
        self.assertEqual(slab.band_widths_m[0], 12.0)
        self.assertEqual(slab.band_lengths_m[0], 10.0)


class TestStrategyGeneratorSmallSlab(TestCase):
    """Small slab: only STUDIO (or STUDIO + 1BHK) feasible due to band geometry."""

    def test_single_narrow_band_studio_only(self):
        # One band: width 3.5m, depth 12m. STUDIO frontage 3m, depth 4.5 -> 1 unit. 2BHK needs 4m x 6m -> no.
        slab = SlabMetrics(
            gross_slab_area_sqm=42.0,
            core_area_sqm=10.0,
            corridor_area_sqm=5.0,
            net_usable_area_sqm=42.0,
            efficiency_ratio=0.8,
            band_widths_m=[3.5],
            band_lengths_m=[12.0],
            band_orientation_axes=[AXIS_WIDTH_DOMINANT],
        )
        strategies = generate_strategies(slab, plot_area_sqm=200.0, max_fsi=2.7, floors=5)
        self.assertEqual(len(strategies), 4)
        studio = next(s for s in strategies if s.unit_type == UnitType.STUDIO)
        bhk2 = next(s for s in strategies if s.unit_type == UnitType.BHK2)
        self.assertTrue(studio.feasible)
        self.assertFalse(bhk2.feasible)
        self.assertEqual(studio.units_per_floor, 1)


class TestStrategyGeneratorMediumSlab(TestCase):
    """Medium slab: 1BHK and 2BHK feasible."""

    def test_medium_slab_1bhk_2bhk_feasible(self):
        # One band 10m x 6m: 2BHK (4x6) -> 2 units/floor; 1BHK (3x4.5) -> 3 units/floor. Use plot 500 so FSI cap allows.
        slab = SlabMetrics(
            gross_slab_area_sqm=80.0,
            core_area_sqm=12.0,
            corridor_area_sqm=8.0,
            net_usable_area_sqm=60.0,
            efficiency_ratio=0.75,
            band_widths_m=[10.0],
            band_lengths_m=[6.0],
            band_orientation_axes=[AXIS_WIDTH_DOMINANT],
        )
        strategies = generate_strategies(slab, plot_area_sqm=500.0, max_fsi=2.7, floors=5)
        bhk1 = next(s for s in strategies if s.unit_type == UnitType.BHK1)
        bhk2 = next(s for s in strategies if s.unit_type == UnitType.BHK2)
        self.assertTrue(bhk1.feasible)
        self.assertTrue(bhk2.feasible)
        self.assertGreaterEqual(bhk1.units_per_floor, 1)
        self.assertGreaterEqual(bhk2.units_per_floor, 1)


class TestStrategyGeneratorLargeSlab(TestCase):
    """Large slab: 3BHK feasible."""

    def test_large_slab_3bhk_feasible(self):
        # Band 12m x 8m: 3BHK (4.5 x 7.5) -> 2 units/floor. Need plot large enough for FSI (2*110*6=1320).
        slab = SlabMetrics(
            gross_slab_area_sqm=150.0,
            core_area_sqm=15.0,
            corridor_area_sqm=12.0,
            net_usable_area_sqm=123.0,
            efficiency_ratio=0.82,
            band_widths_m=[12.0],
            band_lengths_m=[8.0],
            band_orientation_axes=[AXIS_WIDTH_DOMINANT],
        )
        strategies = generate_strategies(slab, plot_area_sqm=600.0, max_fsi=2.7, floors=6)
        bhk3 = next(s for s in strategies if s.unit_type == UnitType.BHK3)
        self.assertTrue(bhk3.feasible)


class TestStrategyGeneratorHeightLimit(TestCase):
    def test_reduced_floors_reduces_total_units(self):
        slab = SlabMetrics(
            gross_slab_area_sqm=100.0,
            core_area_sqm=12.0,
            corridor_area_sqm=8.0,
            net_usable_area_sqm=80.0,
            efficiency_ratio=0.8,
            band_widths_m=[10.0],
            band_lengths_m=[6.0],
            band_orientation_axes=[AXIS_WIDTH_DOMINANT],
        )
        # Plot 400 sqm so 2BHK is feasible for both 5 and 2 floors (total_bua under max)
        s_5 = generate_strategies(slab, 400.0, 2.7, floors=5)
        s_2 = generate_strategies(slab, 400.0, 2.7, floors=2)
        bhk2_5 = next(s for s in s_5 if s.unit_type == UnitType.BHK2 and s.feasible)
        bhk2_2 = next(s for s in s_2 if s.unit_type == UnitType.BHK2 and s.feasible)
        self.assertGreater(bhk2_5.total_units, bhk2_2.total_units)


class TestStrategyGeneratorFsiCap(TestCase):
    def test_fsi_exceeded_rejected(self):
        slab = SlabMetrics(
            gross_slab_area_sqm=200.0,
            core_area_sqm=15.0,
            corridor_area_sqm=10.0,
            net_usable_area_sqm=175.0,
            efficiency_ratio=0.85,
            band_widths_m=[15.0],
            band_lengths_m=[8.0],
            band_orientation_axes=[AXIS_WIDTH_DOMINANT],
        )
        # Very low max BUA so 2BHK strategy would exceed
        strategies = generate_strategies(slab, plot_area_sqm=100.0, max_fsi=0.5, floors=5)
        # At least one strategy should be infeasible due to FSI
        fsi_rejects = [s for s in strategies if s.rejection_reason == "fsi_exceeds_max"]
        self.assertGreater(len(fsi_rejects), 0)


class TestEvaluator(TestCase):
    def test_ordering_and_ranks(self):
        strategies = [
            DevelopmentStrategy(
                unit_type=UnitType.BHK1,
                units_per_floor=2,
                floors=5,
                total_units=10,
                avg_unit_area_sqm=50.0,
                total_bua_sqm=500.0,
                fsi_utilization=0.6,
                efficiency_ratio=0.7,
                feasible=True,
                rejection_reason=None,
            ),
            DevelopmentStrategy(
                unit_type=UnitType.BHK2,
                units_per_floor=1,
                floors=5,
                total_units=5,
                avg_unit_area_sqm=75.0,
                total_bua_sqm=375.0,
                fsi_utilization=0.45,
                efficiency_ratio=0.5,
                feasible=True,
                rejection_reason=None,
            ),
        ]
        slab = SlabMetrics(
            gross_slab_area_sqm=100.0,
            core_area_sqm=10.0,
            corridor_area_sqm=8.0,
            net_usable_area_sqm=82.0,
            efficiency_ratio=0.82,
            band_widths_m=[10.0],
            band_lengths_m=[8.0],
            band_orientation_axes=[AXIS_WIDTH_DOMINANT],
        )
        evals = evaluate_strategies(strategies, slab)
        self.assertEqual(len(evals), 2)
        self.assertEqual(evals[0].rank, 1)
        self.assertEqual(evals[1].rank, 2)
        self.assertGreaterEqual(evals[0].score, evals[1].score)


class TestService(TestCase):
    def test_resolve_returns_evaluation_or_none(self):
        sk = _make_skeleton(
            12.0, 8.0,
            unit_zone_widths=[10.0], unit_zone_depths=[6.0],
        )
        agg = _make_feasibility_aggregate(
            plot_area_sqm=200.0, max_fsi=2.7,
            num_floors_estimated=5, storey_height_used_m=3.0,
        )
        result = resolve_development_strategy(
            sk, agg, height_limit_m=15.0, max_fsi=2.7, storey_height_m=3.0
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, StrategyEvaluation)
        self.assertTrue(result.strategy.feasible)

    def test_resolve_none_when_no_feasible(self):
        # Tiny band: no unit type fits
        sk = _make_skeleton(
            3.0, 3.0,
            unit_zone_widths=[2.0], unit_zone_depths=[2.0],
        )
        agg = _make_feasibility_aggregate(plot_area_sqm=50.0, max_fsi=2.7)
        result = resolve_development_strategy(
            sk, agg, height_limit_m=9.0, max_fsi=2.7, storey_height_m=3.0
        )
        self.assertIsNone(result)
