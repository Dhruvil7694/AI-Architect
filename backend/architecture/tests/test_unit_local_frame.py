"""
Tests for Phase 1.5 UnitLocalFrame: frame derivation, band_id invariant,
edge detection, and stability. Uses minimal FloorSkeleton fixtures and
real skeleton_builder where needed.
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
from floor_skeleton.frame_deriver import derive_local_frame
from floor_skeleton.skeleton_builder import build_skeleton
from floor_skeleton.core_placement_candidates import generate_candidates
from placement_engine.geometry.core_fit import CoreDimensions


def _skeleton_end_core_vertical_one_band() -> tuple[FloorSkeleton, UnitZone]:
    """END_CORE vertical: core left (0..2 x 0..8), unit zone right (2..10 x 0..8)."""
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


def _skeleton_double_loaded_two_bands() -> FloorSkeleton:
    """DOUBLE_LOADED: core on right (gap so units do not touch core), corridor middle, two unit bands."""
    # Footprint 12 x 10. Unit A: 0..8 x 0..4. Corridor: 0..8 x 4..5.2. Unit B: 0..8 x 5.2..10. Core: 10..12 x 0..10 (gap 8..10).
    fp = shapely_box(0, 0, 12, 10)
    core = shapely_box(10, 0, 12, 10)
    corridor = shapely_box(0, 4, 8, 5.2)
    unit_a = shapely_box(0, 0, 8, 4)
    unit_b = shapely_box(0, 5.2, 8, 10)
    zones = [
        UnitZone(band_id=0, polygon=unit_a, orientation_axis=AXIS_DEPTH_DOMINANT, zone_width_m=8.0, zone_depth_m=4.0),
        UnitZone(band_id=1, polygon=unit_b, orientation_axis=AXIS_DEPTH_DOMINANT, zone_width_m=8.0, zone_depth_m=4.8),
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


def _skeleton_single_loaded_one_band() -> FloorSkeleton:
    """SINGLE_LOADED: core left, corridor strip, unit band right of corridor."""
    fp = shapely_box(0, 0, 10, 8)
    core = shapely_box(0, 0, 2, 8)
    corridor = shapely_box(2, 0, 10, 1.2)
    unit_poly = shapely_box(2, 1.2, 10, 8)
    zone = UnitZone(band_id=0, polygon=unit_poly, orientation_axis=AXIS_DEPTH_DOMINANT, zone_width_m=8.0, zone_depth_m=6.8)
    return FloorSkeleton(
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


class TestUnitLocalFrameEndCoreVertical(TestCase):
    """END_CORE vertical: 1 band, repeat_axis (0,1), origin min corner, core_facing_edge detected."""

    def test_repeat_axis_and_origin(self):
        sk, zone = _skeleton_end_core_vertical_one_band()
        frame = derive_local_frame(sk, zone)
        self.assertEqual(frame.repeat_axis, (0.0, 1.0))
        self.assertEqual(frame.depth_axis, (1.0, 0.0))
        self.assertEqual(frame.origin, (2.0, 0.0))
        self.assertEqual(frame.band_length_m, 8.0)
        self.assertEqual(frame.band_depth_m, 8.0)

    def test_core_facing_edge_detected(self):
        sk, zone = _skeleton_end_core_vertical_one_band()
        frame = derive_local_frame(sk, zone)
        self.assertIsNotNone(frame.core_facing_edge)
        start, end = frame.core_facing_edge
        self.assertEqual(len(start), 2)
        self.assertEqual(len(end), 2)
        # Shared edge is x=2 from y=0 to y=8; normalized lexicographically (2,0), (2,8)
        self.assertEqual(start[0], 2.0)
        self.assertEqual(end[0], 2.0)

    def test_corridor_facing_none(self):
        sk, zone = _skeleton_end_core_vertical_one_band()
        frame = derive_local_frame(sk, zone)
        self.assertIsNone(frame.corridor_facing_edge)


class TestUnitLocalFrameDoubleLoaded(TestCase):
    """DOUBLE_LOADED: 2 bands, band_id 0 and 1. Edge detection reflects geometry; both may be non-None when band touches both."""

    def test_two_bands_band_id(self):
        sk = _skeleton_double_loaded_two_bands()
        self.assertEqual(len(sk.unit_zones), 2)
        self.assertEqual(sk.unit_zones[0].band_id, 0)
        self.assertEqual(sk.unit_zones[1].band_id, 1)

    def test_correct_axes(self):
        sk = _skeleton_double_loaded_two_bands()
        for zone in sk.unit_zones:
            frame = derive_local_frame(sk, zone)
            self.assertEqual(frame.repeat_axis, (0.0, 1.0))
            self.assertEqual(frame.depth_axis, (1.0, 0.0))

    def test_corridor_facing_detected(self):
        sk = _skeleton_double_loaded_two_bands()
        # Both bands touch corridor; at least one should have corridor_facing_edge
        frames = [derive_local_frame(sk, z) for z in sk.unit_zones]
        corridor_count = sum(1 for f in frames if f.corridor_facing_edge is not None)
        self.assertGreaterEqual(corridor_count, 1)


class TestEdgeDetectionMatchesGeometry(TestCase):
    """Edge detection reflects real adjacency: if zone shares boundary with core/corridor -> edge set; if no intersection -> None. No exclusivity."""

    def test_zone_touching_core_has_core_facing_edge(self):
        sk, zone = _skeleton_end_core_vertical_one_band()
        frame = derive_local_frame(sk, zone)
        self.assertIsNotNone(frame.core_facing_edge, "Zone shares boundary with core -> core_facing_edge must be set")

    def test_zone_not_touching_core_has_no_core_facing_edge(self):
        fp = shapely_box(0, 0, 20, 10)
        core = shapely_box(0, 0, 2, 10)
        unit_poly = shapely_box(5, 0, 20, 10)
        zone = UnitZone(band_id=0, polygon=unit_poly, orientation_axis=AXIS_DEPTH_DOMINANT, zone_width_m=15.0, zone_depth_m=10.0)
        sk = FloorSkeleton(
            footprint_polygon=fp,
            core_polygon=core,
            corridor_polygon=None,
            unit_zones=[zone],
            pattern_used="END_CORE",
            placement_label="END_CORE_RIGHT",
            area_summary={},
            efficiency_ratio=0.0,
            is_geometry_valid=True,
            passes_min_unit_guard=True,
            is_architecturally_viable=True,
            audit_log=[],
        )
        frame = derive_local_frame(sk, zone)
        self.assertIsNone(frame.core_facing_edge, "Zone has no shared boundary with core -> core_facing_edge must be None")

    def test_zone_touching_corridor_has_corridor_facing_edge(self):
        sk = _skeleton_single_loaded_one_band()
        frame = derive_local_frame(sk, sk.unit_zones[0])
        self.assertIsNotNone(frame.corridor_facing_edge, "Zone shares boundary with corridor -> corridor_facing_edge must be set")

    def test_no_corridor_yields_none_corridor_facing_edge(self):
        sk, zone = _skeleton_end_core_vertical_one_band()
        frame = derive_local_frame(sk, zone)
        self.assertIsNone(frame.corridor_facing_edge, "No corridor polygon -> corridor_facing_edge must be None")


class TestUnitLocalFrameSingleLoaded(TestCase):
    """SINGLE_LOADED: 1 band, corridor_facing_edge present."""

    def test_corridor_edge_exists(self):
        sk = _skeleton_single_loaded_one_band()
        zone = sk.unit_zones[0]
        frame = derive_local_frame(sk, zone)
        self.assertIsNotNone(frame.corridor_facing_edge)


class TestFrameStability(TestCase):
    """Two identical runs yield identical local_frame data."""

    def test_same_skeleton_twice_identical_frames(self):
        sk, zone = _skeleton_end_core_vertical_one_band()
        frame1 = derive_local_frame(sk, zone)
        frame2 = derive_local_frame(sk, zone)
        self.assertEqual(frame1.origin, frame2.origin)
        self.assertEqual(frame1.repeat_axis, frame2.repeat_axis)
        self.assertEqual(frame1.depth_axis, frame2.depth_axis)
        self.assertEqual(frame1.band_length_m, frame2.band_length_m)
        self.assertEqual(frame1.band_depth_m, frame2.band_depth_m)
        self.assertEqual(frame1.core_facing_edge, frame2.core_facing_edge)
        self.assertEqual(frame1.corridor_facing_edge, frame2.corridor_facing_edge)


class TestNoCoreCase(TestCase):
    """Zone that does not touch core: must not crash, core_facing_edge None."""

    def test_zone_not_touching_core(self):
        # Unit zone far from core (no shared boundary with core)
        fp = shapely_box(0, 0, 20, 10)
        core = shapely_box(0, 0, 2, 10)
        unit_poly = shapely_box(5, 0, 20, 10)  # no shared edge with core
        zone = UnitZone(band_id=0, polygon=unit_poly, orientation_axis=AXIS_DEPTH_DOMINANT, zone_width_m=15.0, zone_depth_m=10.0)
        sk = FloorSkeleton(
            footprint_polygon=fp,
            core_polygon=core,
            corridor_polygon=None,
            unit_zones=[zone],
            pattern_used="END_CORE",
            placement_label="END_CORE_RIGHT",
            area_summary={},
            efficiency_ratio=0.0,
            is_geometry_valid=True,
            passes_min_unit_guard=True,
            is_architecturally_viable=True,
            audit_log=[],
        )
        frame = derive_local_frame(sk, zone)
        self.assertIsNone(frame.core_facing_edge)

    def test_empty_core_sentinel_does_not_crash(self):
        # Minimal sentinel-like: empty core
        fp = shapely_box(0, 0, 1, 1)
        core = shapely_box(0, 0, 0, 0)
        unit_poly = shapely_box(0, 0, 1, 1)
        zone = UnitZone(band_id=0, polygon=unit_poly, orientation_axis=AXIS_DEPTH_DOMINANT, zone_width_m=1.0, zone_depth_m=1.0)
        sk = FloorSkeleton(
            footprint_polygon=fp,
            core_polygon=core,
            corridor_polygon=None,
            unit_zones=[zone],
            pattern_used="NO_SKELETON",
            placement_label="NONE",
            area_summary={},
            efficiency_ratio=0.0,
            is_geometry_valid=False,
            passes_min_unit_guard=False,
            is_architecturally_viable=False,
            audit_log=[],
        )
        frame = derive_local_frame(sk, zone)
        self.assertIsNone(frame.core_facing_edge)


class TestBandIdEqualsListIndex(TestCase):
    """For any skeleton from the builder, unit_zones[i].band_id == i."""

    def test_builder_assigns_band_id_sequential(self):
        dims = CoreDimensions()
        W, D = 12.0, 8.0
        cpw, cpd = 2.0, 3.6
        candidates = generate_candidates(W, D, cpw, cpd, dims)
        self.assertGreater(len(candidates), 0)
        # Build END_CORE with one or two zones depending on candidate
        for cand in candidates[:3]:
            sk = build_skeleton(cand, "END_CORE", W, D, dims)
            for i, zone in enumerate(sk.unit_zones):
                self.assertEqual(zone.band_id, i, f"unit_zones[{i}].band_id must equal {i}")
