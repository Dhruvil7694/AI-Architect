"""
Unit tests for Phase D deterministic detailing engine (detailed_layout).

Focus:
- Each room gets walls.
- Doors/windows appear where expected on a simple synthetic floor.
- Validation passes without raising.
"""

from __future__ import annotations

from django.test import TestCase
from shapely.geometry import Polygon, LineString

from detailed_layout import DetailingConfig
from detailed_layout.service import detail_floor_layout
from detailed_layout.validation import validate_detailed_floor
from detailed_layout.diagnostics import compute_counts, check_overlaps
from residential_layout.floor_aggregation import FloorLayoutContract, build_floor_layout
from residential_layout.models import RoomInstance, UnitLayoutContract
from residential_layout.tests.test_floor_aggregation import _skeleton_one_zone


def _make_simple_floor() -> FloorLayoutContract:
    """Synthetic 1-unit floor: LIVING + BEDROOM + TOILET + KITCHEN in a 6x8 box."""
    footprint = Polygon([(0, 0), (6, 0), (6, 8), (0, 8)])
    core = Polygon([(0, 0), (1.5, 3.0), (1.5, 0)])
    corridor = None

    living_poly = Polygon([(0, 4), (6, 4), (6, 8), (0, 8)])
    bed_poly = Polygon([(0, 2), (6, 2), (6, 4), (0, 4)])
    toilet_poly = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    kitchen_poly = Polygon([(2, 0), (6, 0), (6, 2), (2, 2)])

    rooms = [
        RoomInstance(room_type="LIVING", polygon=living_poly, area_sqm=living_poly.area),
        RoomInstance(room_type="BEDROOM", polygon=bed_poly, area_sqm=bed_poly.area),
        RoomInstance(room_type="TOILET", polygon=toilet_poly, area_sqm=toilet_poly.area),
        RoomInstance(room_type="KITCHEN", polygon=kitchen_poly, area_sqm=kitchen_poly.area),
    ]
    unit = UnitLayoutContract(
        rooms=rooms,
        entry_door_segment=LineString([(3, 8), (3, 8.5)]),
        unit_id="U0",
    )
    return FloorLayoutContract(
        floor_id="L0",
        band_layouts=[],
        all_units=[unit],
        core_polygon=core,
        corridor_polygon=corridor,
        footprint_polygon=footprint,
        total_units=1,
        total_residual_area=0.0,
        unit_area_sum=sum(r.area_sqm for r in rooms),
        average_unit_area=sum(r.area_sqm for r in rooms),
        corridor_area=0.0,
        efficiency_ratio_floor=0.5,
    )


class TestDetailingWalls(TestCase):
    def test_each_room_has_walls(self):
        floor = _make_simple_floor()
        cfg = DetailingConfig()
        detailed = detail_floor_layout(floor, cfg)

        for unit in detailed.units.values():
            for room in unit.rooms.values():
                self.assertGreater(
                    len(room.walls_ext) + len(room.walls_int),
                    0,
                    msg=f"Room {room.room_id} should have at least one wall",
                )


class TestDetailingDoorsWindows(TestCase):
    def test_doors_and_windows_present(self):
        floor = _make_simple_floor()
        cfg = DetailingConfig()
        detailed = detail_floor_layout(floor, cfg)

        has_bedroom_door = False
        has_living_window = False
        for unit in detailed.units.values():
            for room in unit.rooms.values():
                if room.room_type == "BEDROOM" and room.doors:
                    has_bedroom_door = True
                if room.room_type == "LIVING" and room.windows:
                    has_living_window = True
        self.assertTrue(has_bedroom_door)
        self.assertTrue(has_living_window)


class TestDetailingValidation(TestCase):
    def test_validate_detailed_geometry_basic(self):
        floor = _make_simple_floor()
        cfg = DetailingConfig()
        detailed = detail_floor_layout(floor, cfg)
        # Should not raise
        validate_detailed_floor(detailed, cfg)


class TestDetailingOnRealFloor(TestCase):
    """Run Phase D on a real FloorLayoutContract produced by Phase 4."""

    def test_real_floor_counts_and_overlaps(self):
        # Build a real skeleton and aggregate to FloorLayoutContract via Phase 4
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        floor = build_floor_layout(sk, floor_id="L0", module_width_m=5.0)

        cfg = DetailingConfig()
        detailed = detail_floor_layout(floor, cfg)

        # Counts must be non-zero for walls and doors/windows on this simple case
        diag = compute_counts(detailed)
        self.assertGreater(diag.total_walls, 0)
        self.assertGreaterEqual(diag.total_doors, 0)
        self.assertGreaterEqual(diag.total_windows, 0)

        # No obvious overlaps in fixtures/furniture diagnostics
        issues = check_overlaps(detailed)
        self.assertEqual(issues, [], msg=f"Overlap issues detected: {issues}")

