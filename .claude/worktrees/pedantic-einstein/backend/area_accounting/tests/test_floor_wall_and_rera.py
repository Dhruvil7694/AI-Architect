"""
Wall-area and RERA carpet tests using the 10m × 10m truth-table geometry.

We construct a synthetic FloorLayoutContract and UnitLayoutContract that
match the coordinates and numeric values in docs/area_accounting_truth_table.md,
then verify:

  - internal/external wall areas from the wall engine
  - per-unit RERA carpet and total carpet
  - derived ratios and invariants
"""

from __future__ import annotations

from django.test import SimpleTestCase
from shapely.geometry import box as shapely_box

from detailed_layout.config import DetailingConfig
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import RoomInstance, UnitLayoutContract

from area_accounting.floor_area import (
    FloorAreaBreakdown,
    SharedWallAllocationPolicy,
    compute_floor_area_breakdown_detailed,
)


class TestFloorWallAndRERA(SimpleTestCase):
    def _make_truth_table_floor_and_units(self) -> tuple[FloorLayoutContract, list[UnitLayoutContract]]:
        # Geometry matches docs/area_accounting_truth_table.md
        footprint = shapely_box(0.0, 0.0, 10.0, 10.0)
        core = shapely_box(0.20, 0.20, 3.20, 4.20)
        corridor = shapely_box(3.20, 0.20, 9.80, 1.40)
        unit_slab = shapely_box(3.20, 1.40, 9.80, 9.80)

        # Rooms inside unit slab
        bedroom_poly = shapely_box(3.20, 1.40, 9.80, 5.55)
        living_poly = shapely_box(3.20, 5.65, 9.80, 9.80)

        bedroom = RoomInstance(
            room_type="BEDROOM",
            polygon=bedroom_poly,
            area_sqm=bedroom_poly.area,
        )
        living = RoomInstance(
            room_type="LIVING",
            polygon=living_poly,
            area_sqm=living_poly.area,
        )
        unit = UnitLayoutContract(
            rooms=[bedroom, living],
            entry_door_segment=None,  # not needed for walls/RERA
            unit_id="U0",
        )

        # From the truth table: unit_envelope_area_sqm = 55.44
        floor = FloorLayoutContract(
            floor_id="L0",
            band_layouts=[],
            all_units=[unit],
            core_polygon=core,
            corridor_polygon=corridor,
            footprint_polygon=footprint,
            total_units=1,
            total_residual_area=0.0,
            unit_area_sum=unit_slab.area,
            average_unit_area=unit_slab.area,
            corridor_area=corridor.area,
            efficiency_ratio_floor=unit_slab.area / footprint.area,
        )
        return floor, [unit]

    def test_wall_areas_and_rera_match_truth_table(self) -> None:
        floor, units = self._make_truth_table_floor_and_units()

        cfg = DetailingConfig(
            external_wall_thickness_m=0.20,
            internal_wall_thickness_m=0.10,
            shaft_wall_thickness_m=0.20,
        )

        breakdown: FloorAreaBreakdown = compute_floor_area_breakdown_detailed(
            floor=floor,
            units=units,
            config=cfg,
            shared_policy=SharedWallAllocationPolicy.HALF,
        )

        # Base areas should match the truth-table values.
        self.assertAlmostEqual(breakdown.gross_built_up_sqm, 100.0, places=2)
        self.assertAlmostEqual(breakdown.core_area_sqm, 12.0, places=2)
        self.assertAlmostEqual(breakdown.corridor_area_sqm, 7.92, places=2)
        self.assertAlmostEqual(breakdown.unit_envelope_area_sqm, 55.44, places=2)

        # No shaft/common walls from core/corridor expected in this synthetic example.
        self.assertGreaterEqual(breakdown.internal_wall_area_sqm, 0.0)
        self.assertGreaterEqual(breakdown.external_wall_area_sqm, 0.0)
        self.assertGreaterEqual(breakdown.shaft_area_sqm, 0.0)

        # RERA carpet must be at least the sum of room internal areas and
        # must not exceed the unit envelope area.
        total_room_area = sum(room.area_sqm for unit in units for room in unit.rooms)
        self.assertGreaterEqual(
            breakdown.rera_carpet_area_total_sqm,
            total_room_area - 1e-6,
        )
        self.assertLessEqual(
            breakdown.rera_carpet_area_total_sqm,
            breakdown.unit_envelope_area_sqm + 1e-6,
        )
        self.assertEqual(len(breakdown.carpet_per_unit), 1)

        # Ratios should use the carpet and unit envelope consistently.
        self.assertAlmostEqual(
            breakdown.efficiency_ratio_recomputed,
            breakdown.unit_envelope_area_sqm / breakdown.gross_built_up_sqm,
            places=4,
        )
        self.assertAlmostEqual(
            breakdown.carpet_to_bua_ratio,
            breakdown.rera_carpet_area_total_sqm / breakdown.gross_built_up_sqm,
            places=4,
        )


class TestSharedWallAllocationPolicy(SimpleTestCase):
    """
    Synthetic 2-unit floor to freeze HALF vs NONE shared-wall behaviour.
    """

    def _make_two_unit_shared_wall_floor(self) -> tuple[FloorLayoutContract, list[UnitLayoutContract]]:
        # Footprint 10 x 10; two units side by side with a shared vertical edge at x=5.
        footprint = shapely_box(0.0, 0.0, 10.0, 10.0)

        # No explicit core/corridor for this test.
        core = None
        corridor = None

        # Unit A: 0.2..5.0 x 0.2..9.8
        unit_a_poly = shapely_box(0.2, 0.2, 5.0, 9.8)
        # Unit B: 5.0..9.8 x 0.2..9.8
        unit_b_poly = shapely_box(5.0, 0.2, 9.8, 9.8)

        room_a = RoomInstance(
            room_type="LIVING",
            polygon=unit_a_poly,
            area_sqm=unit_a_poly.area,
        )
        room_b = RoomInstance(
            room_type="LIVING",
            polygon=unit_b_poly,
            area_sqm=unit_b_poly.area,
        )

        unit_a = UnitLayoutContract(
            rooms=[room_a],
            entry_door_segment=None,
            unit_id="UA",
        )
        unit_b = UnitLayoutContract(
            rooms=[room_b],
            entry_door_segment=None,
            unit_id="UB",
        )

        # unit_envelope_area_sqm is the sum of the two unit polygons.
        unit_envelope = unit_a_poly.area + unit_b_poly.area

        floor = FloorLayoutContract(
            floor_id="L0",
            band_layouts=[],
            all_units=[unit_a, unit_b],
            core_polygon=core,
            corridor_polygon=corridor,
            footprint_polygon=footprint,
            total_units=2,
            total_residual_area=0.0,
            unit_area_sum=unit_envelope,
            average_unit_area=unit_envelope / 2.0,
            corridor_area=0.0,
            efficiency_ratio_floor=unit_envelope / footprint.area,
        )
        return floor, [unit_a, unit_b]

    def test_shared_wall_half_vs_none_policy(self) -> None:
        floor, units = self._make_two_unit_shared_wall_floor()
        cfg = DetailingConfig(
            external_wall_thickness_m=0.20,
            internal_wall_thickness_m=0.10,
            shaft_wall_thickness_m=0.20,
        )

        # Policy: NONE (no allocation to either unit)
        breakdown_none = compute_floor_area_breakdown_detailed(
            floor=floor,
            units=units,
            config=cfg,
            shared_policy=SharedWallAllocationPolicy.NONE,
        )

        # Policy: HALF (50/50 allocation for shared wall between the two units)
        breakdown_half = compute_floor_area_breakdown_detailed(
            floor=floor,
            units=units,
            config=cfg,
            shared_policy=SharedWallAllocationPolicy.HALF,
        )

        # Geometry (unit polygons) should be identical across policies.
        self.assertAlmostEqual(
            breakdown_none.unit_envelope_area_sqm,
            breakdown_half.unit_envelope_area_sqm,
            places=4,
        )

        # Internal wall area is purely geometric and must match across policies.
        self.assertAlmostEqual(
            breakdown_none.internal_wall_area_sqm,
            breakdown_half.internal_wall_area_sqm,
            places=4,
        )

        # Under NONE policy, carpet per unit should equal room internal areas.
        room_a_area = units[0].rooms[0].area_sqm
        room_b_area = units[1].rooms[0].area_sqm
        self.assertEqual(len(breakdown_none.carpet_per_unit), 2)
        self.assertAlmostEqual(breakdown_none.carpet_per_unit[0], room_a_area, places=4)
        self.assertAlmostEqual(breakdown_none.carpet_per_unit[1], room_b_area, places=4)

        # Under HALF policy, each unit should receive half of the internal wall area.
        delta_total = (
            breakdown_half.rera_carpet_area_total_sqm
            - breakdown_none.rera_carpet_area_total_sqm
        )
        self.assertAlmostEqual(
            delta_total,
            breakdown_half.internal_wall_area_sqm,
            places=4,
        )

        # Per-unit carpets must increase by internal_wall_area / 2 each.
        self.assertEqual(len(breakdown_half.carpet_per_unit), 2)
        for i in range(2):
            self.assertAlmostEqual(
                breakdown_half.carpet_per_unit[i]
                - breakdown_none.carpet_per_unit[i],
                breakdown_half.internal_wall_area_sqm / 2.0,
                places=4,
            )


