"""
Test Plot area contract: area_geometry is DXF plane area (m²); properties convert.
"""
from django.test import TestCase

from common.units import sqm_to_sqft
from tp_ingestion.models import Plot


class TestPlotAreaContract(TestCase):
    """area_geometry is polygon area in DXF units² (metres for current TP ingestion)."""

    def test_plot_area_sqm_equals_stored_geometry_when_dxf_is_metres(self):
        plot = Plot(
            city="Test",
            tp_scheme="TP14",
            fp_number="999",
            area_excel=1000.0,
            area_geometry=1000.0,
        )
        self.assertEqual(plot.plot_area_sqm, 1000.0)
        self.assertAlmostEqual(plot.plot_area_sqft, sqm_to_sqft(1000.0), places=3)
