"""
Phase 5 Building Aggregation test matrix (plan Section 9).

Covers: 1 floor, 5 floors, 0 floors, floor failure (mid/first), efficiency formula,
unit_id uniqueness, building_height_m, _validate_building pass/fail, first_floor_contract.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from residential_layout.building_aggregation import (
    build_building_layout,
    BuildingLayoutContract,
    BuildingAggregationError,
    BuildingAggregationValidationError,
    _validate_building,
)
from residential_layout.floor_aggregation import (
    build_floor_layout,
    FloorLayoutContract,
    FloorAggregationError,
)
from residential_layout.tests.test_floor_aggregation import _skeleton_one_zone


class TestBuildingAggregationOneFloor(TestCase):
    """1. One floor — building equals single build_floor_layout(skeleton, L0)."""

    def test_one_floor_equals_single_floor_layout(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        storey = 3.0
        height = 3.5  # 1 floor
        building = build_building_layout(
            sk, height_limit_m=height, storey_height_m=storey, building_id="B0"
        )
        self.assertIsInstance(building, BuildingLayoutContract)
        self.assertEqual(building.total_floors, 1)
        self.assertEqual(len(building.floors), 1)
        single = build_floor_layout(sk, floor_id="L0", module_width_m=None)
        self.assertEqual(building.total_units, single.total_units)
        self.assertAlmostEqual(building.total_unit_area, single.unit_area_sum, places=5)
        self.assertAlmostEqual(
            building.building_efficiency, single.efficiency_ratio_floor, places=5
        )
        self.assertAlmostEqual(building.building_height_m, storey, places=5)


class TestBuildingAggregationFiveFloors(TestCase):
    """2. Five floors — total_floors=5; totals = 5 * per-floor."""

    def test_five_floors_aggregation(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        storey = 3.0
        height = 15.0  # 5 floors
        building = build_building_layout(
            sk, height_limit_m=height, storey_height_m=storey
        )
        self.assertEqual(building.total_floors, 5)
        self.assertEqual(len(building.floors), 5)
        per_floor_units = building.floors[0].total_units
        self.assertEqual(building.total_units, 5 * per_floor_units)
        per_floor_area = building.floors[0].unit_area_sum
        self.assertAlmostEqual(building.total_unit_area, 5 * per_floor_area, places=5)
        fp_area = sk.footprint_polygon.area
        expected_eff = (5 * per_floor_area) / (fp_area * 5)
        self.assertAlmostEqual(building.building_efficiency, expected_eff, places=5)
        self.assertAlmostEqual(building.building_height_m, 15.0, places=5)


class TestBuildingAggregationZeroFloors(TestCase):
    """3. Zero floors — height_limit_m < storey_height_m or 0 → empty contract."""

    def test_zero_floors_empty_contract(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        building = build_building_layout(
            sk, height_limit_m=2.0, storey_height_m=3.0
        )
        self.assertEqual(building.total_floors, 0)
        self.assertEqual(building.floors, [])
        self.assertEqual(building.total_units, 0)
        self.assertAlmostEqual(building.total_unit_area, 0.0, places=5)
        self.assertAlmostEqual(building.total_residual_area, 0.0, places=5)
        self.assertAlmostEqual(building.building_efficiency, 0.0, places=5)
        self.assertAlmostEqual(building.building_height_m, 0.0, places=5)

    def test_height_zero_returns_empty(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        building = build_building_layout(
            sk, height_limit_m=0.0, storey_height_m=3.0
        )
        self.assertEqual(building.total_floors, 0)
        self.assertEqual(building.total_units, 0)


class TestBuildingAggregationFloorFails(TestCase):
    """4. Floor 2 fails — BuildingAggregationError floor_index=2; no partial building."""

    def test_floor_two_fails_raises(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        call_count = [0]

        def mock_build_floor_layout(skeleton, floor_id="", module_width_m=None):
            call_count[0] += 1
            if floor_id == "L2":
                raise FloorAggregationError("mock fail", band_id=0, slice_index=0)
            return build_floor_layout(skeleton, floor_id=floor_id, module_width_m=module_width_m)

        with patch(
            "residential_layout.building_aggregation.build_floor_layout",
            side_effect=mock_build_floor_layout,
        ):
            with self.assertRaises(BuildingAggregationError) as ctx:
                build_building_layout(
                    sk, height_limit_m=10.0, storey_height_m=3.0
                )
            self.assertEqual(ctx.exception.floor_index, 2)


class TestBuildingAggregationEfficiencyFormula(TestCase):
    """5. Efficiency formula — building_efficiency == (3 * unit_area_per_floor) / (footprint * 3)."""

    def test_efficiency_formula_three_floors(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        storey = 3.0
        height = 9.5  # 3 floors
        building = build_building_layout(
            sk, height_limit_m=height, storey_height_m=storey
        )
        self.assertEqual(building.total_floors, 3)
        unit_area_per_floor = building.floors[0].unit_area_sum
        footprint_area = sk.footprint_polygon.area
        expected = (3 * unit_area_per_floor) / (footprint_area * 3)
        self.assertAlmostEqual(building.building_efficiency, expected, places=5)


class TestBuildingAggregationUnitIdUniqueness(TestCase):
    """6. unit_id uniqueness across floors — all unit_ids distinct (e.g. L0_0_0, L1_0_0)."""

    def test_unit_id_uniqueness_two_floors(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        building = build_building_layout(
            sk, height_limit_m=6.5, storey_height_m=3.0
        )
        self.assertEqual(building.total_floors, 2)
        all_ids = []
        for f in building.floors:
            for u in f.all_units:
                all_ids.append(u.unit_id)
        self.assertEqual(len(all_ids), len(set(all_ids)), "unit_ids must be unique")
        self.assertIn("L0_0_0", all_ids)
        self.assertIn("L1_0_0", all_ids)


class TestBuildingAggregationBuildingHeightM(TestCase):
    """7. building_height_m — num_floors=4, storey_height_m=3.0 → 12.0."""

    def test_building_height_m_formula(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        storey = 3.0
        height = 12.5  # 4 floors
        building = build_building_layout(
            sk, height_limit_m=height, storey_height_m=storey
        )
        self.assertEqual(building.total_floors, 4)
        self.assertAlmostEqual(building.building_height_m, 12.0, places=5)


class TestBuildingAggregationFirstFloorFails(TestCase):
    """8. First floor fails — BuildingAggregationError floor_index=0."""

    def test_first_floor_fails_raises(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)

        def mock_raise_first(_skeleton, floor_id="", module_width_m=None):
            if floor_id == "L0":
                raise FloorAggregationError("mock", band_id=0, slice_index=0)
            return build_floor_layout(_skeleton, floor_id=floor_id, module_width_m=module_width_m)

        with patch(
            "residential_layout.building_aggregation.build_floor_layout",
            side_effect=mock_raise_first,
        ):
            with self.assertRaises(BuildingAggregationError) as ctx:
                build_building_layout(
                    sk, height_limit_m=6.0, storey_height_m=3.0
                )
            self.assertEqual(ctx.exception.floor_index, 0)


class TestBuildingAggregationValidateBuilding(TestCase):
    """9. _validate_building — valid contract does not raise."""

    def test_validate_building_passes(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        building = build_building_layout(
            sk, height_limit_m=3.5, storey_height_m=3.0
        )
        _validate_building(building, 3.0)  # no raise


class TestBuildingAggregationValidateBuildingFailure(TestCase):
    """10. _validate_building failure — hand-built broken contract raises."""

    def test_validate_building_total_units_mismatch_raises(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        building = build_building_layout(
            sk, height_limit_m=3.5, storey_height_m=3.0
        )
        # Break total_units
        broken = BuildingLayoutContract(
            building_id=building.building_id,
            floors=building.floors,
            total_floors=building.total_floors,
            total_units=building.total_units + 1,
            total_unit_area=building.total_unit_area,
            total_residual_area=building.total_residual_area,
            building_efficiency=building.building_efficiency,
            building_height_m=building.building_height_m,
        )
        with self.assertRaises(BuildingAggregationValidationError) as ctx:
            _validate_building(broken, 3.0)
        self.assertEqual(ctx.exception.reason, "total_units_consistency")


class TestBuildingAggregationFirstFloorContract(TestCase):
    """first_floor_contract provided — floor 0 reused; build_floor_layout not called for L0."""

    def test_first_floor_contract_reused_floor_zero_not_recomputed(self):
        sk = _skeleton_one_zone(band_length_m=10.0, band_depth_m=8.0)
        first = build_floor_layout(sk, floor_id="L0", module_width_m=None)
        call_count = [0]

        def counting_build_floor_layout(skeleton, floor_id="", module_width_m=None):
            call_count[0] += 1
            return build_floor_layout(skeleton, floor_id=floor_id, module_width_m=module_width_m)

        with patch(
            "residential_layout.building_aggregation.build_floor_layout",
            side_effect=counting_build_floor_layout,
        ):
            building = build_building_layout(
                sk,
                height_limit_m=9.5,
                storey_height_m=3.0,
                first_floor_contract=first,
            )
        # num_floors = 3; with first_floor_contract we call build_floor_layout only for L1, L2
        self.assertEqual(building.total_floors, 3)
        self.assertIs(building.floors[0], first)
        self.assertEqual(call_count[0], 2, "build_floor_layout called only for floors 1 and 2")
