"""
Phase 3 test matrix (plan Section 13).

Covers: narrow band, exact fit, residual below threshold (N_raw>=2 and N_raw==1),
mixed templates, one slice unresolved, double/single-loaded, large band,
residual at threshold, N=1.
"""

from __future__ import annotations

from shapely.geometry import box as shapely_box

from django.test import TestCase

from floor_skeleton.models import (
    FloorSkeleton,
    UnitZone,
    AXIS_DEPTH_DOMINANT,
)
from residential_layout.frames import derive_unit_local_frame
from residential_layout.repetition import (
    repeat_band,
    BandLayoutContract,
    BandRepetitionError,
    BandRepetitionValidationError,
    MIN_RESIDUAL_M,
    DEFAULT_MODULE_WIDTH_M,
    MAX_UNITS_PER_BAND,
)
from residential_layout.errors import UnresolvedLayoutError


def _skeleton_for_band(band_length_m: float, band_depth_m: float) -> tuple[FloorSkeleton, UnitZone]:
    """One zone band: unit_poly 2..(2+band_depth_m) x 0..band_length_m (DEPTH_DOMINANT → band_length along Y)."""
    unit_poly = shapely_box(2, 0, 2 + band_depth_m, band_length_m)
    zone = UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_DEPTH_DOMINANT,
        zone_width_m=band_depth_m,
        zone_depth_m=band_length_m,
    )
    fp = shapely_box(0, -1, 2 + band_depth_m + 2, band_length_m + 1)
    core = shapely_box(0, -1, 2, band_length_m + 1)
    sk = FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=None,
        unit_zones=[zone],
        pattern_used="END_CORE",
        placement_label="END_CORE_LEFT",
        area_summary={},
        efficiency_ratio=0.0,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )
    return sk, zone


class TestRepetitionNarrowBand(TestCase):
    """1. Narrow band: band_length_m < module_width_m → N=0."""

    def test_narrow_band_n_zero(self):
        sk, zone = _skeleton_for_band(band_length_m=2.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=DEFAULT_MODULE_WIDTH_M)
        self.assertIsInstance(result, BandLayoutContract)
        self.assertEqual(result.n_units, 0)
        self.assertEqual(result.units, [])
        self.assertAlmostEqual(result.residual_width_m, 2.0, places=5)
        self.assertAlmostEqual(result.band_length_m, 2.0, places=5)


class TestRepetitionExactFit(TestCase):
    """2. Exact fit: band_length_m = K * module_width_m → N=K, residual=0."""

    def test_exact_fit_two_units(self):
        # 10.0 = 2 * 5.0 so N=2, residual=0 (exact fit; residual=0 does not trigger reduction)
        sk, zone = _skeleton_for_band(band_length_m=10.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=5.0)
        self.assertEqual(result.n_units, 2)
        self.assertAlmostEqual(result.residual_width_m, 0.0, places=5)
        self.assertEqual(len(result.units), 2)
        self.assertEqual(result.units[0].unit_id, "0_0")
        self.assertEqual(result.units[1].unit_id, "0_1")


class TestRepetitionResidualThreshold(TestCase):
    """3. Residual below threshold: N_raw>=2 → N-1; N_raw==1 → N=1 (Option B)."""

    def test_residual_below_threshold_n_raw_2_reduces(self):
        # band_length=7.5, module=3.6 → N_raw=2, residual_raw=0.3 < MIN_RESIDUAL_M → N=1
        sk, zone = _skeleton_for_band(band_length_m=7.5, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertEqual(result.n_units, 1)
        self.assertGreaterEqual(result.residual_width_m, MIN_RESIDUAL_M - 1e-5)

    def test_residual_below_threshold_n_raw_1_keeps_unit(self):
        # Option B: band_length=3.9, module=3.6 → N_raw=1, residual=0.3 → N=1
        sk, zone = _skeleton_for_band(band_length_m=3.9, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertEqual(result.n_units, 1)
        self.assertAlmostEqual(result.residual_width_m, 0.3, places=5)


class TestRepetitionMixedTemplates(TestCase):
    """4. Mixed templates per slice → all units returned, template names may differ."""

    def test_mixed_templates_possible(self):
        # Long enough for 2+ slices; resolution may differ per slice
        sk, zone = _skeleton_for_band(band_length_m=8.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertGreaterEqual(result.n_units, 2)
        for u in result.units:
            self.assertIn(u.resolved_template_name, ("STANDARD_1BHK", "COMPACT_1BHK", "STUDIO"))


class TestRepetitionOneSliceUnresolved(TestCase):
    """5. One slice unresolved → BandRepetitionError; no BandLayoutContract returned."""

    def test_tiny_slice_raises_band_repetition_error(self):
        # Band long enough for 2 slices, but each slice is narrow (3.6m) and shallow depth
        # Use a band that's 7.2m long but only 2m deep so each slice is 3.6x2 - may fail
        sk, zone = _skeleton_for_band(band_length_m=7.2, band_depth_m=2.0)
        frame = derive_unit_local_frame(sk, 0)
        with self.assertRaises(BandRepetitionError) as ctx:
            repeat_band(zone, frame, module_width_m=3.6)
        self.assertEqual(ctx.exception.band_id, 0)
        self.assertIsInstance(ctx.exception.cause, UnresolvedLayoutError)


class TestRepetitionDoubleAndSingleLoaded(TestCase):
    """6–7. Double-loaded and single-loaded one band → repeat_band yields N units, all valid."""

    def test_double_loaded_one_band(self):
        fp = shapely_box(0, 0, 12, 10)
        core = shapely_box(10, 0, 12, 10)
        unit_poly = shapely_box(0, 0, 8, 4)
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=8.0,
            zone_depth_m=4.0,
        )
        sk = FloorSkeleton(
            footprint_polygon=fp,
            core_polygon=core,
            corridor_polygon=None,
            unit_zones=[zone],
            pattern_used="DOUBLE_LOADED",
            placement_label="END_CORE_LEFT",
            area_summary={},
            efficiency_ratio=0.0,
            is_geometry_valid=True,
            passes_min_unit_guard=True,
            is_architecturally_viable=True,
            audit_log=[],
        )
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertGreaterEqual(result.n_units, 1)
        self.assertEqual(len(result.units), result.n_units)
        for u in result.units:
            self.assertIsNotNone(u.resolved_template_name)

    def test_single_loaded_one_band(self):
        sk, zone = _skeleton_for_band(band_length_m=8.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertGreaterEqual(result.n_units, 1)
        self.assertEqual(len(result.units), result.n_units)


class TestRepetitionLargeBand(TestCase):
    """8. Large band (6+ units) → N>=6, validation passes."""

    def test_large_band_capped_or_ok(self):
        # band_length_m for 6 units = 6 * 3.6 = 21.6
        sk, zone = _skeleton_for_band(band_length_m=22.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertGreaterEqual(result.n_units, 6)
        self.assertEqual(len(result.units), result.n_units)
        self.assertAlmostEqual(
            result.n_units * 3.6 + result.residual_width_m,
            result.band_length_m,
            places=5,
        )


class TestRepetitionResidualAtThreshold(TestCase):
    """9. Residual exactly at threshold → N unchanged (tolerance)."""

    def test_residual_at_threshold_no_reduction(self):
        # residual_raw = MIN_RESIDUAL_M exactly or just above
        # N_raw=2, residual_raw=0.4 → no reduction
        sk, zone = _skeleton_for_band(band_length_m=7.6, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertEqual(result.n_units, 2)
        self.assertAlmostEqual(result.residual_width_m, 0.4, places=5)


class TestRepetitionN1(TestCase):
    """10. N=1 → one unit, residual = band_length_m - module_width_m."""

    def test_n_one(self):
        sk, zone = _skeleton_for_band(band_length_m=5.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=3.6)
        self.assertEqual(result.n_units, 1)
        self.assertAlmostEqual(result.residual_width_m, 5.0 - 3.6, places=5)
        self.assertEqual(result.units[0].unit_id, "0_0")


class TestRepetitionDefaultModuleWidth(TestCase):
    """Default module_width_m when None → uses DEFAULT_MODULE_WIDTH_M."""

    def test_default_module_width(self):
        # 10.0 / 3.6 → N=2, residual ≈ 2.8
        sk, zone = _skeleton_for_band(band_length_m=10.0, band_depth_m=8.0)
        frame = derive_unit_local_frame(sk, 0)
        result = repeat_band(zone, frame, module_width_m=None)
        self.assertEqual(result.n_units, 2)
        self.assertAlmostEqual(result.residual_width_m, 10.0 - 2 * DEFAULT_MODULE_WIDTH_M, places=5)
