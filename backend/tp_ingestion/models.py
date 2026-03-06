from django.contrib.gis.db import models


class Plot(models.Model):
    """
    Represents a single FP (Final Plot) extracted from a TP scheme DXF file,
    matched against Excel metadata, and spatially validated.

    Area contract: area_geometry and area_excel are stored in sq.ft (DXF native).
    Use plot_area_sqft / plot_area_sqm for explicit unit access.
    """

    city = models.CharField(max_length=100)
    tp_scheme = models.CharField(max_length=100)
    fp_number = models.CharField(max_length=50)

    # Area in sq.ft as reported in the Excel metadata sheet (same unit as DXF).
    area_excel = models.FloatField()

    # Area in sq.ft computed from the polygon geometry (DXF unit).
    area_geometry = models.FloatField()

    # SRID=0 (unitless/local coordinate space) until a CRS is confirmed for
    # Gujarat TP drawings. Swap to SRID=32643 (UTM Zone 43N) once confirmed.
    geom = models.PolygonField(srid=0)

    # True when |area_geometry - area_excel| / area_excel <= configured tolerance
    validation_status = models.BooleanField(default=False)

    # Optional: land-use designation from plan (e.g. "SALE FOR RESIDENTIAL", "S.E.W.S.H.", "PUBLIC PURPOSE").
    designation = models.CharField(max_length=200, blank=True, default="")

    # Optional: from cadastral/plan data (PostGIS dataset). When set, pipeline uses these instead of CLI.
    # road_width_m: width in metres of road(s) fronting this plot (e.g. 15.0 for "15.00 MT" on plan).
    road_width_m = models.FloatField(null=True, blank=True)
    # road_edges: comma-separated 0-based edge indices facing road (e.g. "0" or "0,1"). Same semantics as --road-edges.
    road_edges = models.CharField(max_length=50, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def plot_area_sqft(self) -> float:
        """Plot area in sq.ft (canonical stored unit)."""
        return self.area_geometry

    @property
    def plot_area_sqm(self) -> float:
        """Plot area in sq.m (derived from area_geometry via common.units)."""
        from common.units import sqft_to_sqm
        return sqft_to_sqm(self.area_geometry)

    class Meta:
        unique_together = ("city", "tp_scheme", "fp_number")
        ordering = ["tp_scheme", "fp_number"]

    def __str__(self):
        status = "VALID" if self.validation_status else "INVALID"
        return f"[{self.tp_scheme}] FP {self.fp_number} — {status}"
