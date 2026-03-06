"""
Tests for Phase 2 resolution layer: resolve_unit_layout and wrapper.

Covers: STANDARD fail → COMPACT succeed, all fail → UnresolvedLayoutError,
wrapper resolve_unit_layout_from_skeleton.
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
from residential_layout.frames import derive_unit_local_frame
from residential_layout.orchestrator import resolve_unit_layout, resolve_unit_layout_from_skeleton
from residential_layout.errors import UnresolvedLayoutError


def _skeleton_depth_5_no_standard() -> tuple[FloorSkeleton, UnitZone]:
    """Zone depth 5 m: STANDARD needs 8 m (fail), COMPACT needs 6.8 m (fail), STUDIO needs 4.3 m (ok)."""
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
    return sk, zone


def _skeleton_tiny_unresolved() -> tuple[FloorSkeleton, UnitZone]:
    """Zone too small for STUDIO (e.g. 3 x 3) → UNRESOLVED."""
    unit_poly = shapely_box(0, 0, 3, 3)
    zone = UnitZone(
        band_id=0,
        polygon=unit_poly,
        orientation_axis=AXIS_WIDTH_DOMINANT,
        zone_width_m=3.0,
        zone_depth_m=3.0,
    )
    fp = shapely_box(-1, -1, 4, 4)
    core = shapely_box(-1, -1, 0, 4)
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


class TestResolveUnitLayout(TestCase):
    """Orchestrator: STANDARD → COMPACT → STUDIO; log and continue on failure."""

    def test_standard_fail_compact_fail_studio_succeeds(self):
        """Zone depth 5: STANDARD and COMPACT fail depth; STUDIO succeeds."""
        sk, zone = _skeleton_depth_5_no_standard()
        frame = derive_unit_local_frame(sk, 0)
        contract = resolve_unit_layout(zone, frame)
        self.assertIsNotNone(contract)
        types = [r.room_type for r in contract.rooms]
        self.assertEqual(types, ["LIVING", "TOILET"])

    def test_all_fail_raises_unresolved(self):
        """Zone too small for STUDIO → UnresolvedLayoutError with failure_reasons."""
        sk, zone = _skeleton_tiny_unresolved()
        frame = derive_unit_local_frame(sk, 0)
        with self.assertRaises(UnresolvedLayoutError) as ctx:
            resolve_unit_layout(zone, frame)
        self.assertEqual(ctx.exception.reason_code, "unresolved")
        self.assertGreaterEqual(len(ctx.exception.failure_reasons), 1)


class TestResolveFromSkeleton(TestCase):
    """Wrapper: derive frame, pull zone, call resolve_unit_layout."""

    def test_wrapper_returns_contract(self):
        sk, _ = _skeleton_depth_5_no_standard()
        contract = resolve_unit_layout_from_skeleton(sk, 0)
        self.assertIsNotNone(contract)
        self.assertEqual([r.room_type for r in contract.rooms], ["LIVING", "TOILET"])
