from django.contrib.gis.db import models


class Plot(models.Model):
    """
    Represents a single FP (Final Plot) extracted from a TP scheme DXF file,
    matched against Excel metadata, and spatially validated.

    Area contract: area_geometry is the polygon area in DXF plane units² (m² for
    metre-based TP drawings). area_excel is the authority sheet value in the
    same drawing unit as the CAD file. Use plot_area_sqft / plot_area_sqm for SI/imperial.
    """

    city = models.CharField(max_length=100)
    tp_scheme = models.CharField(max_length=100)
    fp_number = models.CharField(max_length=50)

    # Area as reported in the Excel metadata sheet (same plane unit as DXF geometry).
    area_excel = models.FloatField()

    # Polygon area from geometry in DXF plane units² (m² when 1 DXF unit = 1 m).
    area_geometry = models.FloatField()

    # SRID=0 (unitless/local coordinate space) until a CRS is confirmed for
    # Gujarat TP drawings. Swap to SRID=32643 (UTM Zone 43N) once confirmed.
    geom = models.PolygonField(srid=0)
    
    # Optimal label placement point (computed using representative_point/polylabel)
    # This is superior to centroid for irregular/L-shaped plots
    label_point = models.PointField(srid=0, null=True, blank=True)

    # True when |area_geometry - area_excel| / area_excel <= configured tolerance
    validation_status = models.BooleanField(default=False)

    # Optional: land-use designation from plan (e.g. "SALE FOR RESIDENTIAL", "S.E.W.S.H.", "PUBLIC PURPOSE").
    designation = models.CharField(max_length=200, blank=True, default="")

    # Optional: from cadastral/plan data (PostGIS dataset). When set, pipeline uses these instead of CLI.
    # road_width_m: width in metres of road(s) fronting this plot (e.g. 15.0 for "15.00 MT" on plan).
    road_width_m = models.FloatField(null=True, blank=True)
    # road_edges: comma-separated 0-based edge indices facing road (e.g. "0" or "0,1"). Same semantics as --road-edges.
    road_edges = models.CharField(max_length=50, blank=True, default="")
    # Cached feasibility payload for default storey height (3.0m).
    cached_feasibility_json = models.JSONField(null=True, blank=True)
    cached_feasibility_storey_height_m = models.FloatField(null=True, blank=True)
    # Cached site metrics payload used by planner sidebar.
    cached_site_metrics_json = models.JSONField(null=True, blank=True)
    cached_metrics_updated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def plot_area_sqm(self) -> float:
        """Plot area in square metres."""
        from common.units import dxf_plane_area_to_sqm

        return dxf_plane_area_to_sqm(float(self.area_geometry))

    @property
    def plot_area_sqft(self) -> float:
        """Plot area in international square feet."""
        from common.units import sqm_to_sqft

        return sqm_to_sqft(self.plot_area_sqm)

    class Meta:
        unique_together = ("city", "tp_scheme", "fp_number")
        ordering = ["tp_scheme", "fp_number"]

    def __str__(self):
        status = "VALID" if self.validation_status else "INVALID"
        return f"[{self.tp_scheme}] FP {self.fp_number} — {status}"


class BlockLabel(models.Model):
    """
    Overlay labels from CAD (e.g. BLOCK_NO like "306", "360").

    These are not FP plot identifiers; they are rendered as an additional
    MapLibre layer on top of existing Plot polygons.
    """

    text = models.CharField(max_length=50)
    # Store in the same local coordinate space as Plot.geom (SRID=0).
    geom = models.PointField(srid=0)

    # Best-effort spatial mapping to a Plot polygon; may be null if the
    # label couldn't be assigned robustly.
    plot = models.ForeignKey(
        "Plot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="block_labels",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["text"]),
            models.Index(fields=["plot", "text"]),
        ]

    def __str__(self) -> str:
        return f"BlockLabel {self.text}"


class Road(models.Model):
    """
    Road geometry extracted from TP scheme DXF.
    
    Stores both the original polygon and computed centerline for
    cartographic rendering. Roads are rendered as centerlines with
    width styling in MapLibre.
    """
    
    city = models.CharField(max_length=100)
    tp_scheme = models.CharField(max_length=100)
    
    # Original road polygon from DXF
    geom = models.PolygonField(srid=0)
    
    # Computed centerline for line-based rendering
    centerline = models.LineStringField(srid=0, null=True, blank=True)
    
    # Road width in metres (from designation text or computed from geometry)
    width_m = models.FloatField(null=True, blank=True)
    
    # Optional: road name/designation
    name = models.CharField(max_length=200, blank=True, default="")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=["city", "tp_scheme"]),
        ]
    
    def __str__(self) -> str:
        width_str = f"{self.width_m}m" if self.width_m else "unknown width"
        name_str = self.name if self.name else "Road"
        return f"[{self.tp_scheme}] {name_str} ({width_str})"
