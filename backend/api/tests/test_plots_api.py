from __future__ import annotations

from django.contrib.gis.geos import LineString, Point, Polygon
from django.test import TestCase

from tp_ingestion.models import BlockLabel, Plot, Road


class PlotAndTpBundleAPITests(TestCase):
    def setUp(self) -> None:
        geom_tp14 = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
        geom_tp15 = Polygon(((20, 20), (40, 20), (40, 40), (20, 40), (20, 20)))
        road_geom = Polygon(((0, 11), (10, 11), (10, 13), (0, 13), (0, 11)))

        self.plot_tp14 = Plot.objects.create(
            city="Surat",
            tp_scheme="TP14",
            fp_number="1",
            area_excel=100.0,
            area_geometry=100.0,
            geom=geom_tp14,
            label_point=Point(5, 5, srid=0),
            validation_status=True,
            designation="SALE FOR RESIDENTIAL",
            road_width_m=18.0,
        )
        Plot.objects.create(
            city="Surat",
            tp_scheme="TP15",
            fp_number="2",
            area_excel=400.0,
            area_geometry=400.0,
            geom=geom_tp15,
            label_point=Point(30, 30, srid=0),
            validation_status=True,
            road_width_m=None,
        )

        Road.objects.create(
            city="Surat",
            tp_scheme="TP14",
            geom=road_geom,
            centerline=LineString((0, 12), (10, 12), srid=0),
            width_m=18.0,
            name="18 m Road",
        )

        BlockLabel.objects.create(
            text="101",
            geom=Point(5, 5, srid=0),
            plot=self.plot_tp14,
        )

    def test_list_plots_returns_envelope_shape(self) -> None:
        resp = self.client.get("/api/v1/plots/")
        self.assertEqual(resp.status_code, 200)

        payload = resp.json()
        self.assertIn("results", payload)
        self.assertIn("count", payload)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(len(payload["results"]), 2)
        self.assertIn("id", payload["results"][0])
        self.assertIn("geometry", payload["results"][0])

    def test_list_plots_filters_by_tp_scheme_and_city(self) -> None:
        resp = self.client.get("/api/v1/plots/?tp_scheme=TP14&city=Surat")
        self.assertEqual(resp.status_code, 200)

        payload = resp.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["id"], "TP14-1")

    def test_list_plots_filter_is_case_insensitive(self) -> None:
        resp = self.client.get("/api/v1/plots/?tp_scheme=tp14&city=surat")
        self.assertEqual(resp.status_code, 200)

        payload = resp.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], "TP14-1")

    def test_tp_bundle_requires_tp_scheme(self) -> None:
        resp = self.client.get("/api/map/tp-bundle/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "tp_scheme query parameter is required")

    def test_tp_bundle_returns_scoped_layers(self) -> None:
        resp = self.client.get("/api/map/tp-bundle/?tp_scheme=TP14&city=Surat")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()

        self.assertEqual(payload["meta"]["tpScheme"], "TP14")
        self.assertEqual(payload["meta"]["city"], "Surat")
        self.assertEqual(payload["meta"]["coordSpace"], "LOCAL_DXF")
        self.assertEqual(payload["meta"]["srid"], 0)

        self.assertEqual(payload["stats"]["fpCount"], 1)
        self.assertEqual(payload["stats"]["roadCount"], 1)
        self.assertEqual(payload["stats"]["blockLabelCount"], 1)

        fp_features = payload["layers"]["fpPolygons"]["features"]
        fp_label_features = payload["layers"]["fpLabelPoints"]["features"]
        road_features = payload["layers"]["roads"]["features"]
        road_centerlines = payload["layers"]["roadCenterlines"]["features"]
        block_features = payload["layers"]["blockLabels"]["features"]

        self.assertEqual(len(fp_features), 1)
        self.assertEqual(len(fp_label_features), 1)
        self.assertEqual(len(road_features), 1)
        self.assertEqual(len(road_centerlines), 1)
        self.assertEqual(len(block_features), 1)

        self.assertEqual(fp_features[0]["properties"]["plotId"], "TP14-1")
        self.assertEqual(fp_label_features[0]["properties"]["plotId"], "TP14-1")
        self.assertEqual(block_features[0]["properties"]["plotId"], "TP14-1")

    def test_tp_bundle_also_available_under_v1_prefix(self) -> None:
        resp = self.client.get("/api/v1/map/tp-bundle/?tp_scheme=TP14")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["meta"]["tpScheme"], "TP14")

    def test_tp_bundle_accepts_hyphenated_tp_and_case_insensitive_city(self) -> None:
        resp = self.client.get("/api/map/tp-bundle/?tp_scheme=TP-14&city=surat")
        self.assertEqual(resp.status_code, 200)

        payload = resp.json()
        self.assertEqual(payload["stats"]["fpCount"], 1)
        self.assertEqual(payload["stats"]["roadCount"], 1)
        self.assertEqual(payload["stats"]["blockLabelCount"], 1)
