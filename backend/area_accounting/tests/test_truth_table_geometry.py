"""
10m × 10m area-accounting truth-table geometry test.

This test reproduces the explicit geometry defined in
`docs/area_accounting_truth_table.md` and asserts that the manually
computed numeric areas are consistent with the polygons.

At this stage it does NOT call any area-accounting engine functions;
its purpose is to freeze:

  - footprint / wall / core / corridor / unit slab geometry
  - internal room and internal wall geometry
  - derived numeric areas and ratios

Future Phase 1 accounting code must match these values.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from shapely.geometry import box as shapely_box


class TestTruthTableGeometry(SimpleTestCase):
    def test_truth_table_numbers_match_geometry(self) -> None:
        # --- 1. Base rectangles -------------------------------------------------
        footprint = shapely_box(0.0, 0.0, 10.0, 10.0)
        inner_slab = shapely_box(0.20, 0.20, 9.80, 9.80)

        core = shapely_box(0.20, 0.20, 3.20, 4.20)
        corridor = shapely_box(3.20, 0.20, 9.80, 1.40)
        unit_slab = shapely_box(3.20, 1.40, 9.80, 9.80)

        # --- 2. Internal rooms and partition wall ------------------------------
        bedroom = shapely_box(3.20, 1.40, 9.80, 5.55)
        living = shapely_box(3.20, 5.65, 9.80, 9.80)
        partition_wall = shapely_box(3.20, 5.55, 9.80, 5.65)

        # --- 3. Expected numeric values from the truth table -------------------
        gross_built_up = 100.00
        internal_slab_area = 92.16
        external_wall_area = 7.84

        core_area = 12.00
        corridor_area = 7.92
        unit_envelope_area = 55.44

        bedroom_area = 27.39
        living_area = 27.39
        room_internal_area_total = 54.78
        internal_wall_area = 0.66

        rera_carpet = 55.44
        common_area_total = 19.92

        efficiency_ratio = 0.5544
        common_area_percentage = 0.1992
        carpet_to_bua_ratio = 0.5544
        room_to_envelope_ratio = 0.9881

        # --- 4. Geometry → numeric checks --------------------------------------
        self.assertAlmostEqual(footprint.area, gross_built_up, places=4)
        self.assertAlmostEqual(inner_slab.area, internal_slab_area, places=4)
        self.assertAlmostEqual(
            footprint.area - inner_slab.area,
            external_wall_area,
            places=4,
        )

        self.assertAlmostEqual(core.area, core_area, places=4)
        self.assertAlmostEqual(corridor.area, corridor_area, places=4)
        self.assertAlmostEqual(unit_slab.area, unit_envelope_area, places=4)

        # Base invariant: unit envelope + core + corridor must not exceed gross.
        combined = unit_envelope_area + core_area + corridor_area
        self.assertLessEqual(
            combined,
            gross_built_up + 1e-6,
            msg="unit_envelope + core + corridor must be <= gross_built_up",
        )

        self.assertAlmostEqual(bedroom.area, bedroom_area, places=4)
        self.assertAlmostEqual(living.area, living_area, places=4)
        self.assertAlmostEqual(
            bedroom.area + living.area,
            room_internal_area_total,
            places=4,
        )
        self.assertAlmostEqual(partition_wall.area, internal_wall_area, places=4)

        # --- 5. RERA carpet and ratios -----------------------------------------
        computed_rera = room_internal_area_total + internal_wall_area
        self.assertAlmostEqual(computed_rera, rera_carpet, places=4)

        computed_common = core_area + corridor_area  # shaft_area = 0
        self.assertAlmostEqual(computed_common, common_area_total, places=4)

        self.assertAlmostEqual(
            unit_envelope_area / gross_built_up,
            efficiency_ratio,
            places=4,
        )
        self.assertAlmostEqual(
            common_area_total / gross_built_up,
            common_area_percentage,
            places=4,
        )
        self.assertAlmostEqual(
            rera_carpet / gross_built_up,
            carpet_to_bua_ratio,
            places=4,
        )
        self.assertAlmostEqual(
            room_internal_area_total / unit_envelope_area,
            room_to_envelope_ratio,
            places=4,
        )

