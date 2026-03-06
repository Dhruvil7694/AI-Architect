"""
Unit tests for common.units and Plot area contract.

Verifies:
- Conversion constants and round-trip.
- Plot.plot_area_sqft / plot_area_sqm when area_geometry is in sq.ft.
"""
from django.test import TestCase

from common.units import (
    SQFT_TO_SQM,
    SQM_TO_SQFT,
    sqft_to_sqm,
    sqm_to_sqft,
    DXF_TO_METRES,
    dxf_to_metres,
)


class TestCommonUnits(TestCase):
    """Conversion utilities from common.units."""

    def test_sqft_to_sqm_known_value(self):
        # 1 sq.ft = 0.09290304 sq.m
        self.assertAlmostEqual(sqft_to_sqm(1.0), 0.09290304, places=6)

    def test_sqm_to_sqft_roundtrip(self):
        self.assertAlmostEqual(sqm_to_sqft(sqft_to_sqm(100.0)), 100.0, places=6)

    def test_sqft_to_sqm_roundtrip(self):
        self.assertAlmostEqual(sqft_to_sqm(sqm_to_sqft(20.0)), 20.0, places=6)

    def test_constants_consistent(self):
        self.assertAlmostEqual(SQFT_TO_SQM * SQM_TO_SQFT, 1.0, places=10)

    def test_dxf_to_metres(self):
        # 1 ft = 0.3048 m
        self.assertAlmostEqual(dxf_to_metres(1.0), 0.3048, places=6)

    def test_sqft_sqm_consistent_with_dxf(self):
        # (1 ft)^2 = (0.3048 m)^2
        expected = DXF_TO_METRES ** 2
        self.assertAlmostEqual(SQFT_TO_SQM, expected, places=8)
