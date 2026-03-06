from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.contrib.gis.geos import Polygon

from tp_ingestion.models import Plot


class PlotListAPITests(TestCase):
    def setUp(self) -> None:
        geom1 = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        geom2 = Polygon(((0, 0), (20, 0), (20, 20), (0, 20), (0, 0)))

        Plot.objects.create(
            city="X",
            tp_scheme="TP14",
            fp_number="1",
            area_excel=100.0,
            area_geometry=100.0,
            geom=geom1,
            validation_status=True,
            road_width_m=18.0,
        )
        Plot.objects.create(
            city="X",
            tp_scheme="TP15",
            fp_number="2",
            area_excel=400.0,
            area_geometry=400.0,
            geom=geom2,
            validation_status=True,
            road_width_m=None,
        )

        self.url = "/api/v1/plots/"

    def test_list_plots_geojson_default(self) -> None:
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body), 2)
        first = body[0]
        self.assertIn("tp", first)
        self.assertIn("fp", first)
        self.assertIn("area_sqft", first)
        self.assertIn("road_width_m", first)
        self.assertIn("geometry", first)
        geom = first["geometry"]
        # Default format is GeoJSON-like dict.
        if geom is not None:
            self.assertIn("type", geom)
            self.assertIn("coordinates", geom)

    def test_list_plots_wkt_format(self) -> None:
        resp = self.client.get(f"{self.url}?geometry_format=wkt")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(len(body), 1)
        first = body[0]
        self.assertIsInstance(first["geometry"], str)

