"""
Test matrix for Phase 2 composer (plan Section 12).

Covers: single-loaded, double-loaded, end-core, minimal zone,
depth/width budget fail, width_budget_fail, dimension/area fail.
No orchestrator (fallback) in this file.
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
from residential_layout.frames import derive_unit_local_frame
from residential_layout.composer import compose_unit
from residential_layout.templates import (
    STANDARD_1BHK,
    COMPACT_1BHK,
    STUDIO,
)
from residential_layout.errors import (
    UnitZoneTooSmallError,
    LayoutCompositionError,
)


def _skeleton_end_core_one_zone() -> tuple[FloorSkeleton, UnitZone]:
    """END_CORE: core left (0..2 x 0..8), unit zone right (2..10 x 0..8). band_depth=8, band_length=8."""
    fp = shapely_box(0, 0, 10, 8)
    core = shapely_box(0, 0, 2, 8)
    unit_poly = shapely_box(2, 0, 10, 8)
    zone = UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_DEPTH_DOMINANT,
        zone_width_m=8.0,
        zone_depth_m=8.0,
    )
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


def _skeleton_double_loaded_two_zones() -> FloorSkeleton:
    """DOUBLE_LOADED: two bands; each zone 8 x 4 (or 4.8)."""
    fp = shapely_box(0, 0, 12, 10)
    core = shapely_box(10, 0, 12, 10)
    corridor = shapely_box(0, 4, 8, 5.2)
    unit_a = shapely_box(0, 0, 8, 4)
    unit_b = shapely_box(0, 5.2, 8, 10)
    zones = [
        UnitZone(
            band_id=0,
            polygon=unit_a,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=8.0,
            zone_depth_m=4.0,
        ),
        UnitZone(
            band_id=1,
            polygon=unit_b,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=8.0,
            zone_depth_m=4.8,
        ),
    ]
    return FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=corridor,
        unit_zones=zones,
        pattern_used="DOUBLE_LOADED",
        placement_label="END_CORE_LEFT",
        area_summary={},
        efficiency_ratio=0.0,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )


def _skeleton_single_loaded_one_zone() -> tuple[FloorSkeleton, UnitZone]:
    """SINGLE_LOADED: one zone with corridor and core edges."""
    fp = shapely_box(0, 0, 10, 8)
    core = shapely_box(0, 0, 2, 8)
    corridor = shapely_box(2, 0, 10, 1.0)
    unit_poly = shapely_box(2, 0, 10, 8)
    zone = UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_DEPTH_DOMINANT,
        zone_width_m=8.0,
        zone_depth_m=8.0,
    )
    sk = FloorSkeleton(
        footprint_polygon=fp,
        core_polygon=core,
        corridor_polygon=corridor,
        unit_zones=[zone],
        pattern_used="SINGLE_LOADED",
        placement_label="END_CORE_LEFT",
        area_summary={},
        efficiency_ratio=0.0,
        is_geometry_valid=True,
        passes_min_unit_guard=True,
        is_architecturally_viable=True,
        audit_log=[],
    )
    return sk, zone


class TestComposerEndCore(TestCase):
    """End-core slab: corridor_edge None; entry on frontage_edge; valid layout."""

    def test_end_core_one_zone_standard_1bhk(self):
        sk, zone = _skeleton_end_core_one_zone()
        frame = derive_unit_local_frame(sk, 0)
        contract = compose_unit(zone, frame, STANDARD_1BHK)
        self.assertIsNotNone(contract)
        types = [r.room_type for r in contract.rooms]
        self.assertEqual(types, ["LIVING", "BEDROOM", "TOILET", "KITCHEN"])
        self.assertEqual(len(contract.entry_door_segment.coords), 2)
        self.assertIsNone(contract.unit_id)

    def test_end_core_studio(self):
        sk, zone = _skeleton_end_core_one_zone()
        frame = derive_unit_local_frame(sk, 0)
        contract = compose_unit(zone, frame, STUDIO)
        types = [r.room_type for r in contract.rooms]
        self.assertEqual(types, ["LIVING", "TOILET"])


class TestComposerDoubleLoaded(TestCase):
    """Double-loaded slab: two zones; two layouts; wet_wall_line per band."""

    def test_double_loaded_two_layouts(self):
        sk = _skeleton_double_loaded_two_zones()
        for idx in range(2):
            zone = sk.unit_zones[idx]
            frame = derive_unit_local_frame(sk, idx)
            # Band depth 4.0 and 4.8 are below STANDARD_1BHK min_depth 8; use COMPACT (6.8) or STUDIO (4.3)
            contract = compose_unit(zone, frame, STUDIO)
            self.assertIsNotNone(contract)
            self.assertIn("LIVING", [r.room_type for r in contract.rooms])
            self.assertIn("TOILET", [r.room_type for r in contract.rooms])


class TestComposerSingleLoaded(TestCase):
    """Single-loaded: one zone, corridor and core edges; entry on corridor."""

    def test_single_loaded_standard_1bhk(self):
        sk, zone = _skeleton_single_loaded_one_zone()
        frame = derive_unit_local_frame(sk, 0)
        contract = compose_unit(zone, frame, STANDARD_1BHK)
        self.assertEqual([r.room_type for r in contract.rooms], ["LIVING", "BEDROOM", "TOILET", "KITCHEN"])


class TestComposerMinimalZone(TestCase):
    """Minimal viable zone: dimensions at template min; success, rooms at min."""

    def test_minimal_zone_compact_1bhk(self):
        # COMPACT min_width=3, min_depth=6.8 → zone 3.0 x 6.8
        unit_poly = shapely_box(0, 0, 3.0, 6.8)
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_WIDTH_DOMINANT,
            zone_width_m=3.0,
            zone_depth_m=6.8,
        )
        fp = shapely_box(-1, -1, 4, 8)
        core = shapely_box(-1, -1, 0, 8)
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
        frame = derive_unit_local_frame(sk, 0)
        contract = compose_unit(zone, frame, COMPACT_1BHK)
        self.assertEqual([r.room_type for r in contract.rooms], ["LIVING", "BEDROOM", "TOILET", "KITCHEN"])


class TestComposerDepthBudgetFail(TestCase):
    """Depth budget: required_depth > band_depth_m → UnitZoneTooSmallError."""

    def test_depth_too_small_raises(self):
        # Zone depth 5 m; STANDARD_1BHK requires 8 m
        unit_poly = shapely_box(0, 0, 5, 5)
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_DEPTH_DOMINANT,
            zone_width_m=5.0,
            zone_depth_m=5.0,
        )
        fp = shapely_box(-1, -1, 6, 6)
        core = shapely_box(-1, -1, 0, 6)
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
        frame = derive_unit_local_frame(sk, 0)
        with self.assertRaises(UnitZoneTooSmallError) as ctx:
            compose_unit(zone, frame, STANDARD_1BHK)
        self.assertEqual(ctx.exception.reason_code, "zone_too_small")
        self.assertEqual(ctx.exception.which, "depth")


class TestComposerWidthBudgetFail(TestCase):
    """Width budget: w_toilet + w_kitchen > band_length_m → LayoutCompositionError width_budget_fail."""

    def test_width_budget_fail_raises(self):
        # Narrow band: length 3 m. STANDARD w_toilet+w_kitchen = 1.5+2 = 3.5 > 3
        unit_poly = shapely_box(0, 0, 3, 9)
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_WIDTH_DOMINANT,
            zone_width_m=3.0,
            zone_depth_m=9.0,
        )
        fp = shapely_box(-1, -1, 4, 10)
        core = shapely_box(-1, -1, 0, 10)
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
        frame = derive_unit_local_frame(sk, 0)
        with self.assertRaises(LayoutCompositionError) as ctx:
            compose_unit(zone, frame, STANDARD_1BHK)
        self.assertEqual(ctx.exception.reason_code, "width_budget_fail")
