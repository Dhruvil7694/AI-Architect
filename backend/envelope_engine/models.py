"""
envelope_engine/models.py
--------------------------
PlotEnvelope — persists the computed buildable envelope for a BuildingProposal.

Stores four geometry layers (all SRID=0, DXF feet) for full auditability:
    margin_geom      — polygon after all per-edge margin offsets
    gc_geom          — polygon after ground coverage enforcement (may equal margin_geom)
    envelope_geom    — final buildable footprint (= gc_geom in current flow)
    common_plot_geom — the carved 10% common open-space strip

The `edge_margin_audit` JSON field stores the complete per-edge margin
decision so every setback can be traced to its GDCR clause without
querying the GDCR.yaml at read time.
"""

from django.contrib.gis.db import models

from rules_engine.models import BuildingProposal


class PlotEnvelope(models.Model):

    STATUS_CHOICES = [
        ("VALID",               "Valid — envelope computed successfully"),
        ("COLLAPSED",           "Collapsed — margins exceed plot dimensions"),
        ("TOO_SMALL",           "Too small — envelope below minimum buildable area"),
        ("INVALID_GEOM",        "Invalid geometry — plot polygon is degenerate"),
        ("INSUFFICIENT_INPUT",  "Insufficient input — road_facing_edges not declared"),
        ("ERROR",               "Unexpected error during computation"),
    ]

    GC_STATUS_CHOICES = [
        ("OK",           "Within GC limit"),
        ("CLIPPED",      "Clipped to satisfy GC limit"),
        ("MEASURE_ONLY", "GDCR GC limit not yet defined — measured only"),
        ("NO_LIMIT",     "GC enforcement disabled"),
        ("NA",           "Not applicable"),
    ]

    COMMON_PLOT_STATUS_CHOICES = [
        ("CARVED",          "Common plot carved from rear"),
        ("NO_CARVE_NEEDED", "Rear margin zone satisfies 10% requirement"),
        ("NO_REAR_EDGE",    "No rear edge identified — carving skipped"),
        ("NA",              "Not applicable"),
    ]

    # ── Proposal link ─────────────────────────────────────────────────────────
    proposal = models.ForeignKey(
        BuildingProposal,
        on_delete=models.CASCADE,
        related_name="envelopes",
    )

    # ── Status ─────────────────────────────────────────────────────────────────
    status = models.CharField(max_length=30, choices=STATUS_CHOICES)
    error_message = models.TextField(
        blank=True,
        help_text="Populated when status is COLLAPSED / INVALID_GEOM / ERROR.",
    )

    # ── Geometry layers (SRID=0 — DXF feet, matching Plot.geom) ───────────────
    margin_geom = models.PolygonField(
        srid=0, null=True, blank=True,
        help_text="Polygon after per-edge margin offsets only.",
    )
    gc_geom = models.PolygonField(
        srid=0, null=True, blank=True,
        help_text="Polygon after ground coverage enforcement.",
    )
    envelope_geom = models.PolygonField(
        srid=0, null=True, blank=True,
        help_text="Final buildable footprint (legal envelope).",
    )
    common_plot_geom = models.PolygonField(
        srid=0, null=True, blank=True,
        help_text="Carved 10% common open-space strip.",
    )

    # ── Scalar audit metrics ───────────────────────────────────────────────────
    envelope_area_sqft = models.FloatField(
        null=True, blank=True,
        help_text="Area of the final buildable envelope in sq.ft.",
    )
    ground_coverage_pct = models.FloatField(
        null=True, blank=True,
        help_text="Ground coverage percentage: envelope_area / plot_area × 100.",
    )
    gc_status = models.CharField(
        max_length=20, choices=GC_STATUS_CHOICES, default="NA",
    )
    common_plot_area_sqft = models.FloatField(
        null=True, blank=True,
        help_text="Area of the carved common plot in sq.ft.",
    )
    common_plot_status = models.CharField(
        max_length=20, choices=COMMON_PLOT_STATUS_CHOICES, default="NA",
    )

    # ── Per-edge audit log ────────────────────────────────────────────────────
    edge_margin_audit = models.JSONField(
        default=list,
        help_text=(
            "List of dicts, one per plot edge: "
            "{edge_index, edge_type, margin_m, margin_dxf, gdcr_clause, ...}"
        ),
    )

    # ── Input snapshot (for replay / debugging) ───────────────────────────────
    road_facing_edges = models.JSONField(
        default=list,
        help_text="Edge indices declared as road-facing at computation time.",
    )
    building_height_used = models.FloatField(
        null=True, blank=True,
        help_text="Building height (m) used for margin table lookups.",
    )
    road_width_used = models.FloatField(
        null=True, blank=True,
        help_text="Road width (m) used for road-side margin lookup.",
    )

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-computed_at"]

    def __str__(self) -> str:
        area = f"{self.envelope_area_sqft:.1f} sq.ft" if self.envelope_area_sqft else "—"
        return (
            f"[{self.status}] Envelope for Proposal #{self.proposal_id} "
            f"— {area}"
        )
