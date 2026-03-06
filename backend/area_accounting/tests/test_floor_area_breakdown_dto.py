"""
DTO-level tests for FloorAreaBreakdown.

Uses the 10m × 10m truth-table numbers from
`docs/area_accounting_truth_table.md` to verify that the derived ratios
on FloorAreaBreakdown are computed correctly from the base areas.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from area_accounting.floor_area import FloorAreaBreakdown


class TestFloorAreaBreakdownDTO(SimpleTestCase):
    def test_derived_ratios_match_truth_table(self) -> None:
        # Numbers lifted directly from docs/area_accounting_truth_table.md
        dto = FloorAreaBreakdown(
            gross_built_up_sqm=100.00,
            core_area_sqm=12.00,
            corridor_area_sqm=7.92,
            shaft_area_sqm=0.00,
            common_area_total_sqm=19.92,
            unit_envelope_area_sqm=55.44,
            internal_wall_area_sqm=0.66,
            external_wall_area_sqm=7.84,
            rera_carpet_area_total_sqm=55.44,
            carpet_per_unit=[55.44],
        )

        self.assertAlmostEqual(dto.common_area_percentage, 0.1992, places=4)
        self.assertAlmostEqual(dto.carpet_to_bua_ratio, 0.5544, places=4)
        self.assertAlmostEqual(dto.efficiency_ratio_recomputed, 0.5544, places=4)
        self.assertIsInstance(dto.carpet_per_unit, tuple)
        self.assertEqual(dto.carpet_per_unit, (55.44,))

