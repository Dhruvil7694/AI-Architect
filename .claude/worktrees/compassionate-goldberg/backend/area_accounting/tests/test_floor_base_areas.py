"""
Base-area tests for compute_floor_base_areas / compute_floor_area_breakdown_basic.

These tests verify that:
  - Footprint, core, corridor, and unit_envelope areas are derived correctly
    from FloorLayoutContract geometry.
  - The invariant
        unit_envelope + core + corridor <= gross_built_up + tol
    holds for a simple synthetic floor.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from shapely.geometry import box as shapely_box

from residential_layout.floor_aggregation import FloorLayoutContract
from area_accounting.floor_area import (
    compute_floor_base_areas,
    compute_floor_area_breakdown_basic,
)


class TestFloorBaseAreas(SimpleTestCase):
    def _make_simple_floor(self) -> FloorLayoutContract:
        """
        Synthetic FloorLayoutContract with:
          - footprint: 10 x 10
          - core:      0..2 x 0..10
          - corridor:  2..10 x 0..2
          - unit slab: remaining (not explicitly modelled; only unit_area_sum used)
        """
        footprint = shapely_box(0.0, 0.0, 10.0, 10.0)
        core = shapely_box(0.0, 0.0, 2.0, 10.0)
        corridor = shapely_box(2.0, 0.0, 10.0, 2.0)

        gross = footprint.area          # 100
        core_area = core.area           # 20
        corridor_area = corridor.area   # 16

        # Unit envelope = interior minus core and corridor
        unit_envelope = gross - core_area - corridor_area  # 64

        return FloorLayoutContract(
            floor_id="L0",
            band_layouts=[],
            all_units=[],
            core_polygon=core,
            corridor_polygon=corridor,
            footprint_polygon=footprint,
            total_units=0,
            total_residual_area=0.0,
            unit_area_sum=unit_envelope,
            average_unit_area=0.0,
            corridor_area=corridor_area,
            efficiency_ratio_floor=unit_envelope / gross,
        )

    def test_compute_floor_base_areas(self) -> None:
        floor = self._make_simple_floor()
        base = compute_floor_base_areas(floor)

        self.assertAlmostEqual(base["gross_built_up_sqm"], 100.0, places=4)
        self.assertAlmostEqual(base["core_area_sqm"], 20.0, places=4)
        self.assertAlmostEqual(base["corridor_area_sqm"], 16.0, places=4)
        self.assertAlmostEqual(base["shaft_area_sqm"], 0.0, places=4)
        self.assertAlmostEqual(base["unit_envelope_area_sqm"], 64.0, places=4)
        self.assertAlmostEqual(
            base["common_area_total_sqm"],
            base["core_area_sqm"] + base["corridor_area_sqm"],
            places=4,
        )

        # Invariant: unit envelope + core + corridor <= gross.
        combined = (
            base["unit_envelope_area_sqm"]
            + base["core_area_sqm"]
            + base["corridor_area_sqm"]
        )
        self.assertLessEqual(
            combined,
            base["gross_built_up_sqm"] + 1e-6,
            msg="unit_envelope + core + corridor must be <= gross_built_up",
        )

    def test_compute_floor_area_breakdown_basic(self) -> None:
        floor = self._make_simple_floor()
        breakdown = compute_floor_area_breakdown_basic(floor)

        self.assertAlmostEqual(breakdown.gross_built_up_sqm, 100.0, places=4)
        self.assertAlmostEqual(breakdown.core_area_sqm, 20.0, places=4)
        self.assertAlmostEqual(breakdown.corridor_area_sqm, 16.0, places=4)
        self.assertAlmostEqual(breakdown.shaft_area_sqm, 0.0, places=4)
        self.assertAlmostEqual(breakdown.unit_envelope_area_sqm, 64.0, places=4)

        # No walls / RERA at this level.
        self.assertAlmostEqual(breakdown.internal_wall_area_sqm, 0.0, places=4)
        self.assertAlmostEqual(breakdown.external_wall_area_sqm, 0.0, places=4)
        self.assertAlmostEqual(breakdown.rera_carpet_area_total_sqm, 0.0, places=4)
        self.assertEqual(breakdown.carpet_per_unit, ())

        # Derived ratios from DTO should still be coherent.
        self.assertAlmostEqual(
            breakdown.efficiency_ratio_recomputed,
            64.0 / 100.0,
            places=4,
        )

