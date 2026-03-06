"""
placement_engine/models.py
---------------------------
Two models for persisting building placement results:

  BuildingPlacement — one record per compute_placement run.
    Stores the overall status, orientation angles tested, packing mode chosen,
    spacing requirements, and the full spacing audit log.

  FootprintRecord — one record per placed tower.
    Stores the geometry, dimensions in DXF feet and metres, orientation details,
    which MultiPolygon component the footprint came from, grid resolution used,
    and the per-tower spacing verdict.

All geometry is SRID=0 (DXF feet), consistent with Plot.geom and
PlotEnvelope.envelope_geom.
"""

from django.contrib.gis.db import models

from envelope_engine.models import PlotEnvelope


class BuildingPlacement(models.Model):

    STATUS_CHOICES = [
        ("VALID",         "Valid — all towers placed with spacing satisfied"),
        ("TOO_TIGHT",     "Too tight — fewer towers placed or spacing fail"),
        ("NO_FIT",        "No fit — not even one tower can fit"),
        ("NO_FIT_CORE",   "No core fit — footprint placed but building core cannot fit"),
        ("INVALID_INPUT", "Invalid input — bad parameters"),
        ("ERROR",         "Unexpected error during computation"),
    ]

    PACKING_MODE_CHOICES = [
        ("ROW_WISE", "Row-wise — along principal axis"),
        ("COL_WISE", "Col-wise — across principal axis (perpendicular)"),
    ]

    # ── Envelope link ──────────────────────────────────────────────────────────
    envelope = models.ForeignKey(
        PlotEnvelope,
        on_delete=models.CASCADE,
        related_name="placements",
    )

    # ── Overall status ─────────────────────────────────────────────────────────
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField(
        blank=True,
        help_text="Populated when status is ERROR.",
    )

    # ── Request parameters ─────────────────────────────────────────────────────
    n_towers_requested  = models.IntegerField()
    n_towers_placed     = models.IntegerField()
    building_height_m   = models.FloatField()

    # ── Spacing ────────────────────────────────────────────────────────────────
    spacing_required_m   = models.FloatField(
        help_text="max(H/3, minimum_spacing_m) in metres.",
    )
    spacing_required_dxf = models.FloatField(
        help_text="spacing_required_m converted to DXF feet.",
    )

    # ── Orientation audit ──────────────────────────────────────────────────────
    orientation_primary_deg   = models.FloatField(
        null=True, blank=True,
        help_text="Primary orientation angle (degrees) from MBR longest edge.",
    )
    orientation_secondary_deg = models.FloatField(
        null=True, blank=True,
        help_text="Secondary orientation angle = primary + 90°.",
    )

    # ── Packing strategy chosen ────────────────────────────────────────────────
    packing_mode = models.CharField(
        max_length=10,
        choices=PACKING_MODE_CHOICES,
        null=True,
        blank=True,
        help_text="Which packing strategy won: ROW_WISE or COL_WISE.",
    )

    # ── Grid resolution used ───────────────────────────────────────────────────
    grid_resolution_dxf = models.FloatField(
        null=True, blank=True,
        help_text="Adaptive grid resolution (DXF feet) used for the first tower.",
    )

    # ── Spacing audit log ──────────────────────────────────────────────────────
    placement_audit = models.JSONField(
        default=list,
        help_text=(
            "List of spacing check dicts, one per tower pair: "
            "{pair, gap_dxf, gap_m, required_m, status, gdcr_clause, formula}"
        ),
    )

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-computed_at"]

    def __str__(self) -> str:
        return (
            f"[{self.status}] Placement for Envelope #{self.envelope_id} "
            f"— {self.n_towers_placed}/{self.n_towers_requested} towers "
            f"@ H={self.building_height_m}m"
        )


class FootprintRecord(models.Model):

    ORIENTATION_LABEL_CHOICES = [
        ("PRIMARY",       "Primary — along MBR longer edge"),
        ("PERPENDICULAR", "Perpendicular — across MBR"),
        ("FORCED",        "Forced — override angle (COL_WISE mode)"),
    ]

    SPACING_STATUS_CHOICES = [
        ("PASS", "Pass — gap satisfies H/3"),
        ("FAIL", "Fail — gap is less than required"),
        ("NA",   "N/A — single tower, no pair to check"),
    ]

    # ── Parent link ────────────────────────────────────────────────────────────
    placement = models.ForeignKey(
        BuildingPlacement,
        on_delete=models.CASCADE,
        related_name="footprints",
    )
    tower_index = models.IntegerField(
        help_text="0-based placement sequence index.",
    )

    # ── Geometry ───────────────────────────────────────────────────────────────
    footprint_geom = models.PolygonField(
        srid=0,
        help_text="Placed building footprint rectangle (DXF feet, SRID=0).",
    )

    # ── Dimensions ────────────────────────────────────────────────────────────
    footprint_area_sqft  = models.FloatField()
    footprint_width_dxf  = models.FloatField(help_text="Width along orientation angle (DXF feet).")
    footprint_depth_dxf  = models.FloatField(help_text="Depth perpendicular to orientation (DXF feet).")
    footprint_width_m    = models.FloatField()
    footprint_depth_m    = models.FloatField()

    # ── Orientation details ────────────────────────────────────────────────────
    orientation_angle_deg = models.FloatField(
        help_text="Angle used for grid rotation (degrees from x-axis).",
    )
    orientation_label = models.CharField(
        max_length=15,
        choices=ORIENTATION_LABEL_CHOICES,
        help_text="PRIMARY | PERPENDICULAR | FORCED",
    )

    # ── Grid audit ────────────────────────────────────────────────────────────
    source_component_index = models.IntegerField(
        default=0,
        help_text="Which MultiPolygon component this footprint was found in (0-based).",
    )
    grid_resolution_dxf = models.FloatField(
        help_text="Adaptive grid resolution used for this footprint (DXF feet).",
    )

    # ── Spacing result ────────────────────────────────────────────────────────
    min_spacing_to_adjacent_dxf = models.FloatField(
        null=True, blank=True,
        help_text="Minimum gap to any other placed tower (DXF feet).",
    )
    min_spacing_to_adjacent_m = models.FloatField(
        null=True, blank=True,
        help_text="Minimum gap to any other placed tower (metres).",
    )
    spacing_status = models.CharField(
        max_length=10,
        choices=SPACING_STATUS_CHOICES,
        default="NA",
    )

    # ── Core fit validation ───────────────────────────────────────────────────
    core_validation = models.JSONField(
        default=dict,
        help_text=(
            "CoreValidationResult dict: core_fit_status, selected_pattern, "
            "core_area_estimate_sqm, remaining_usable_sqm, lift_required, "
            "n_staircases_required, core_pkg_width_m, core_pkg_depth_m, audit_log."
        ),
    )

    class Meta:
        ordering = ["placement", "tower_index"]

    def __str__(self) -> str:
        return (
            f"Tower {self.tower_index} | {self.footprint_area_sqft:.1f} sq.ft "
            f"| {self.orientation_label} {self.orientation_angle_deg:.1f}°"
        )
