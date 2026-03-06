"""
Test Plot area contract: area_geometry is sq.ft, plot_area_sqft / plot_area_sqm.
"""
from django.test import TestCase

from common.units import sqft_to_sqm
from tp_ingestion.models import Plot


class TestPlotAreaContract(TestCase):
    """Plot stores area in sq.ft; properties expose sq.ft and sq.m explicitly."""

    def test_plot_area_sqft_equals_stored(self):
        # Create plot with area_geometry in sq.ft (e.g. 1000 sq.ft)
        plot = Plot(
            city="Test",
            tp_scheme="TP14",
            fp_number="999",
            area_excel=1000.0,
            area_geometry=1000.0,
        )
        self.assertEqual(plot.plot_area_sqft, 1000.0)
        self.assertEqual(plot.plot_area_sqft, plot.area_geometry)

    def test_plot_area_sqm_derived(self):
        plot = Plot(
            city="Test",
            tp_scheme="TP14",
            fp_number="998",
            area_excel=1000.0,
            area_geometry=1000.0,
        )
        expected_sqm = sqft_to_sqm(1000.0)
        self.assertAlmostEqual(plot.plot_area_sqm, expected_sqm, places=6)
        self.assertAlmostEqual(plot.plot_area_sqm, 92.90304, places=2)
