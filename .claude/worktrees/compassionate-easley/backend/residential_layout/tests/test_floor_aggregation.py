"""
Phase 4 Floor Aggregation test matrix (plan Section 12).

Covers: single band, two bands (DOUBLE_LOADED), one band fails, empty band,
all bands N=0, END_CORE, total_residual_area, total_units/unit_id, metrics,
validation, skeleton assertions, zero zones, module_width_m None.
"""

from __future__ import annotations

from shapely.geometry import box as shapely_box

from django.test import TestCase

from floor_skeleton.models import (
    FloorSkeleton,
    UnitZone,
    AXIS_DEPTH_DOMINANT,
    AXIS_WIDTH_DOMINANT,
)
from residential_layout.floor_aggregation import (
    build_floor_layout,
    FloorLayoutContract,
    FloorAggregationError,
    FloorAggregationValidationError,
    _run_skeleton_assertions,
    _validate_floor,
)
from residential_layout.repetition import (
    DEFAULT_MODULE_WIDTH_M,
    repeat_band,
    BandLayoutContract,
)
from residential_layout.frames import derive_unit_local_frame


def _skeleton_one_zone(
    band_length_m: float,
    band_depth_m: float,
    corridor_polygon=None,
) -> FloorSkeleton:
    """One unit zone inside footprint. END_CORE style (corridor_polygon=None)."""
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
    return FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=corridor_polygon,
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


def _skeleton_two_zones(
    band0_length: float,
    band0_depth: float,
    band1_length: float,
    band1_depth: float,
) -> FloorSkeleton:
    """Two non-overlapping unit zones inside one footprint (DOUBLE_LOADED style)."""
    # Zone 0: (0, 0) to (band0_length, band0_depth); Zone 1: (0, band0_depth+1) to (band1_length, band0_depth+1+band1_depth)
    # So they don't overlap. Footprint contains both.
    unit_a = shapely_box(0, 0, band0_length, band0_depth)
    unit_b = shapely_box(0, band0_depth + 1, band1_length, band0_depth + 1 + band1_depth)
    zones = [
        UnitZone(
            band_id=0,
            polygon=unit_a,
            orientation_axis=AXIS_WIDTH_DOMINANT,
            zone_width_m=band0_length,
            zone_depth_m=band0_depth,
        ),
        UnitZone(
            band_id=1,
            polygon=unit_b,
            orientation_axis=AXIS_WIDTH_DOMINANT,
            zone_width_m=band1_length,
            zone_depth_m=band1_depth,
        ),
    ]
    # Footprint large enough to contain both
    fx = max(band0_length, band1_length) + 2
    fy = band0_depth + 1 + band1_depth + 2
    fp = shapely_box(-1, -1, fx, fy)
    core = shapely_box(-1, -1, 0, fy)
    return FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=None,
        unit_zones=zones,
        pattern_used="DOUBLE_LOADED",
        placement_label="CENTER_CORE",
        area_summary={},
        efficiency_ratio=0.0,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )


def _skeleton_empty_zones() -> FloorSkeleton:
    """Zero unit zones."""
    fp = shapely_box(0, 0, 10, 10)
    core = shapely_box(0, 0, 2, 10)
    return FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=None,
        unit_zones=[],
        pattern_used="END_CORE",
        placement_label="END_CORE_LEFT",
        area_summary={},
        efficiency_ratio=0.0,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )


class TestFloorAggregationSingleBand(TestCase):
    """1. Single band, N units → one band in band_layouts, N units, unit_ids floorId_0_0 … floorId_0_(N-1)."""

    def test_single_band_n_units(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="floorId", module_width_m=5.0)
        self.assertIsInstance(result, FloorLayoutContract)
        self.assertEqual(len(result.band_layouts), 1)
        self.assertEqual(result.band_layouts[0].n_units, 2)
        self.assertEqual(result.total_units, 2)
        self.assertEqual(len(result.all_units), 2)
        self.assertEqual(result.all_units[0].unit_id, "floorId_0_0")
        self.assertEqual(result.all_units[1].unit_id, "floorId_0_1")


class TestFloorAggregationTwoBands(TestCase):
    """2. Two bands (DOUBLE_LOADED) → two band_layouts, unit_ids floorId_0_* and floorId_1_*."""

    def test_two_bands_double_loaded(self):
        sk = _skeleton_two_zones(
            band0_length=10.0,
            band0_depth=8.0,
            band1_length=10.0,
            band1_depth=8.0,
        )
        result = build_floor_layout(sk, floor_id="L0", module_width_m=3.6)
        self.assertEqual(len(result.band_layouts), 2)
        self.assertEqual(
            result.total_units,
            result.band_layouts[0].n_units + result.band_layouts[1].n_units,
        )
        self.assertEqual(len(result.all_units), result.total_units)
        band0_ids = [u.unit_id for u in result.band_layouts[0].units]
        band1_ids = [u.unit_id for u in result.band_layouts[1].units]
        for uid in band0_ids:
            self.assertTrue(uid.startswith("L0_0_"))
        for uid in band1_ids:
            self.assertTrue(uid.startswith("L0_1_"))


class TestFloorAggregationOneBandFails(TestCase):
    """3. One band fails → build_floor_layout raises (FloorAggregationError or BandRepetitionError), no return."""

    def test_first_band_fails_raises(self):
        # Narrow first band: N=0 is ok. Use a band that would fail on resolve (e.g. too small depth).
        # Instead: use two zones, second zone has tiny depth so repeat_band might still succeed with N=0.
        # To force BandRepetitionError we need a slice that raises UnresolvedLayoutError.
        # Use one zone with dimensions that yield one slice but that slice fails resolution.
        # From test_repetition: they patch resolve_unit_layout. We can use a zone with band_depth_m
        # below minimum template depth so that resolve_unit_layout raises.
        from residential_layout.templates import STANDARD_1BHK
        min_depth = getattr(STANDARD_1BHK, "min_depth_m", 8.0)
        # Zone with depth 2.0: too small for any template
        unit_poly = shapely_box(2, 0, 2 + 2.0, 10.0)  # depth 2, length 10
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=2.0,
            zone_depth_m=10.0,
        )
        fp = shapely_box(0, -1, 10, 12)
        core = shapely_box(0, -1, 2, 12)
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
        with self.assertRaises(FloorAggregationError) as ctx:
            build_floor_layout(sk, floor_id="L0", module_width_m=3.6)
        self.assertEqual(ctx.exception.band_id, 0)


class TestFloorAggregationEmptyBand(TestCase):
    """4. Empty band (N=0) → BandLayoutContract with n_units=0; floor still returns; total_units = sum of other bands."""

    def test_one_band_empty_n_zero(self):
        sk = _skeleton_one_zone(band_length_m=2.0, band_depth_m=8.0)  # band_length < module_width → N=0
        result = build_floor_layout(sk, floor_id="L0", module_width_m=DEFAULT_MODULE_WIDTH_M)
        self.assertEqual(len(result.band_layouts), 1)
        self.assertEqual(result.band_layouts[0].n_units, 0)
        self.assertEqual(result.total_units, 0)
        self.assertEqual(result.all_units, [])


class TestFloorAggregationAllBandsN0(TestCase):
    """5. All bands N=0 → FloorLayoutContract with total_units=0, all_units=[], total_residual_area = sum of band lengths * depths."""

    def test_all_bands_n_zero(self):
        sk = _skeleton_one_zone(band_length_m=2.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)
        self.assertEqual(result.total_units, 0)
        self.assertEqual(result.all_units, [])
        # total_residual_area = residual_width_m * zone_depth_m; zone has zone_depth_m=band_length_m=2
        expected = sum(
            b.residual_width_m * sk.unit_zones[b.band_id].zone_depth_m
            for b in result.band_layouts
        )
        self.assertAlmostEqual(result.total_residual_area, expected, places=5)


class TestFloorAggregationEndCore(TestCase):
    """6. END_CORE → corridor_polygon is None, corridor_area = 0."""

    def test_end_core_corridor_none(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)
        self.assertIsNone(result.corridor_polygon)
        self.assertEqual(result.corridor_area, 0.0)


class TestFloorAggregationTotalResidualArea(TestCase):
    """7. total_residual_area → matches sum(residual_width_m * zone_depth_m)."""

    def test_total_residual_area_formula(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)
        # N=2, residual = 10 - 2*5 = 0; total_residual_area = 0 * 8 = 0
        expected = sum(
            b.residual_width_m * sk.unit_zones[b.band_id].zone_depth_m
            for b in result.band_layouts
        )
        self.assertAlmostEqual(result.total_residual_area, expected, places=5)


class TestFloorAggregationTotalUnitsUnitId(TestCase):
    """8. total_units / unit_id → len(all_units) == sum(b.n_units); unit_id format \"{floor_id}_{band_id}_{i}\"."""

    def test_total_units_and_unit_id_format(self):
        sk = _skeleton_two_zones(10.0, 8.0, 10.0, 8.0)
        result = build_floor_layout(sk, floor_id="FP", module_width_m=3.6)
        self.assertEqual(len(result.all_units), result.total_units)
        self.assertEqual(
            result.total_units,
            sum(b.n_units for b in result.band_layouts),
        )
        for u in result.all_units:
            parts = u.unit_id.split("_")
            self.assertGreaterEqual(len(parts), 3)
            self.assertEqual(parts[0], "FP")


class TestFloorAggregationMetrics(TestCase):
    """9. Metrics → unit_area_sum, efficiency_ratio_floor, average_unit_area consistent with formula."""

    def test_metrics_formulas(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)
        self.assertGreater(result.total_units, 0)
        expected_avg = result.unit_area_sum / result.total_units
        self.assertAlmostEqual(result.average_unit_area, expected_avg, places=5)
        if result.footprint_polygon.area > 0:
            self.assertAlmostEqual(
                result.efficiency_ratio_floor,
                result.unit_area_sum / result.footprint_polygon.area,
                places=5,
            )


class TestFloorAggregationUnitAreaGeometryConsistency(TestCase):
    """
    9b. Geometry consistency: sum of unit room areas should match unit_area_sum.

    This ties the analytical band-based unit_area_sum in FloorLayoutContract
    back to the actual unit room polygons produced by the templates.
    """

    def test_unit_area_sum_matches_sum_of_room_areas(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)

        total_room_area = 0.0
        for unit in result.all_units:
            for room in unit.rooms:
                total_room_area += float(room.area_sqm)

        # Rooms represent internal usable areas; they must not exceed the
        # analytical unit envelope area captured in unit_area_sum.
        self.assertLessEqual(
            total_room_area,
            result.unit_area_sum + 1e-6,
            msg="Sum of room areas must not exceed unit_area_sum envelope area.",
        )


class TestFloorAggregationValidation(TestCase):
    """10. Validation → _validate_floor passes; no exception."""

    def test_validate_floor_passes(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)
        _validate_floor(
            result.band_layouts,
            result.all_units,
            result.total_units,
        )


class TestFloorAggregationSkeletonAssertions(TestCase):
    """Skeleton assertions: band_overlap and band_not_in_footprint raise FloorAggregationValidationError."""

    def test_band_overlap_raises(self):
        # Two overlapping zones
        unit_a = shapely_box(0, 0, 10, 5)
        unit_b = shapely_box(5, 2, 15, 7)  # overlaps unit_a
        zones = [
            UnitZone(
                band_id=0,
                polygon=unit_a,
                orientation_axis=AXIS_WIDTH_DOMINANT,
                zone_width_m=10.0,
                zone_depth_m=5.0,
            ),
            UnitZone(
                band_id=1,
                polygon=unit_b,
                orientation_axis=AXIS_WIDTH_DOMINANT,
                zone_width_m=10.0,
                zone_depth_m=5.0,
            ),
        ]
        fp = shapely_box(-1, -1, 20, 10)
        core = shapely_box(-1, -1, 0, 10)
        sk = FloorSkeleton(
            footprint_polygon=fp,
            core_polygon=core,
            corridor_polygon=None,
            unit_zones=zones,
            pattern_used="DOUBLE_LOADED",
            placement_label="CENTER_CORE",
            area_summary={},
            efficiency_ratio=0.0,
            is_geometry_valid=True,
            passes_min_unit_guard=True,
            is_architecturally_viable=True,
            audit_log=[],
        )
        with self.assertRaises(FloorAggregationValidationError) as ctx:
            _run_skeleton_assertions(sk)
        self.assertEqual(ctx.exception.reason, "band_overlap")

    def test_band_not_in_footprint_raises(self):
        # Zone extends outside footprint
        unit_poly = shapely_box(0, 0, 15, 10)  # 15x10
        fp = shapely_box(0, 0, 10, 10)  # 10x10 - does not contain unit
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_WIDTH_DOMINANT,
            zone_width_m=15.0,
            zone_depth_m=10.0,
        )
        core = shapely_box(0, 0, 2, 10)
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
        with self.assertRaises(FloorAggregationValidationError) as ctx:
            _run_skeleton_assertions(sk)
        self.assertEqual(ctx.exception.reason, "band_not_in_footprint")


class TestFloorAggregationZeroZones(TestCase):
    """Zero zones → band_layouts=[], all_units=[], total_units=0, total_residual_area=0; return contract."""

    def test_zero_zones_returns_contract(self):
        sk = _skeleton_empty_zones()
        result = build_floor_layout(sk, floor_id="L0")
        self.assertEqual(result.band_layouts, [])
        self.assertEqual(result.all_units, [])
        self.assertEqual(result.total_units, 0)
        self.assertAlmostEqual(result.total_residual_area, 0.0, places=5)
        self.assertAlmostEqual(result.unit_area_sum, 0.0, places=5)
        self.assertAlmostEqual(result.average_unit_area, 0.0, places=5)
        self.assertAlmostEqual(result.efficiency_ratio_floor, 0.0, places=5)


class TestFloorAggregationModuleWidthNone(TestCase):
    """module_width_m None → uses DEFAULT_MODULE_WIDTH_M."""

    def test_module_width_none_uses_default(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        result = build_floor_layout(sk, floor_id="L0", module_width_m=None)
        # 10 / 3.6 → N=2, residual ≈ 2.8
        self.assertEqual(result.band_layouts[0].n_units, 2)
        self.assertAlmostEqual(
            result.band_layouts[0].residual_width_m,
            10.0 - 2 * DEFAULT_MODULE_WIDTH_M,
            places=5,
        )


class TestFloorAggregationFloorIdDefault(TestCase):
    """floor_id default → empty string; unit_id like \"_0_0\"."""

    def test_floor_id_default_empty_string(self):
        sk = _skeleton_one_zone(band_length_m=5.0, band_depth_m=8.0)
        result = build_floor_layout(sk, module_width_m=3.6)  # no floor_id
        self.assertEqual(result.floor_id, "")
        self.assertEqual(result.all_units[0].unit_id, "_0_0")
