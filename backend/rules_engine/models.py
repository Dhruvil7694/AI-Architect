"""
rules_engine/models.py
----------------------
Two models:

BuildingProposal  — captures all parameters for a proposed building on a Plot.
ComplianceResult  — one row per evaluated rule, linked to a BuildingProposal.

Area fields (total_bua, ground_coverage, etc.) are stored in sq.ft to match
the units in tp_ingestion.Plot (DXF native unit).
Height, width, and margin fields are stored in metres.
"""

from django.db import models

from tp_ingestion.models import Plot


class BuildingProposal(models.Model):
    """
    Represents an architect's proposed design for a specific FP plot.
    """

    # ── Plot reference ────────────────────────────────────────────────────────
    plot = models.ForeignKey(
        Plot, on_delete=models.CASCADE, related_name="proposals"
    )

    # ── Mandatory proposal parameters ─────────────────────────────────────────
    road_width      = models.FloatField(help_text="Adjacent road width in metres.")
    building_height = models.FloatField(help_text="Proposed building height in metres.")
    total_bua       = models.FloatField(help_text="Total built-up area (all floors) in sq.ft.")
    num_floors      = models.IntegerField(help_text="Number of floors above ground.")
    ground_coverage = models.FloatField(help_text="Ground floor footprint in sq.ft.")

    # ── Boolean flags ─────────────────────────────────────────────────────────
    has_basement   = models.BooleanField(default=False)
    is_sprinklered = models.BooleanField(default=False)
    has_lift       = models.BooleanField(
        null=True, blank=True,
        help_text="None = not declared; True = provided; False = not provided."
    )

    # ── Optional margin parameters (metres) ───────────────────────────────────
    side_margin = models.FloatField(null=True, blank=True,
                                    help_text="Minimum proposed side margin in metres.")
    rear_margin = models.FloatField(null=True, blank=True,
                                    help_text="Minimum proposed rear margin in metres.")

    # ── Optional staircase parameters ─────────────────────────────────────────
    stair_width    = models.FloatField(null=True, blank=True,
                                       help_text="Staircase clear width in metres.")
    tread_mm       = models.FloatField(null=True, blank=True,
                                       help_text="Staircase tread depth in mm.")
    riser_mm       = models.FloatField(null=True, blank=True,
                                       help_text="Staircase riser height in mm.")
    stair_headroom = models.FloatField(null=True, blank=True,
                                       help_text="Headroom on staircase in metres.")

    # ── Optional ventilation / clearance parameters ────────────────────────────
    window_area    = models.FloatField(null=True, blank=True,
                                       help_text="Total window area of habitable room in sq.m.")
    floor_area     = models.FloatField(null=True, blank=True,
                                       help_text="Floor area of habitable room in sq.m.")
    room_height    = models.FloatField(null=True, blank=True,
                                       help_text="Floor-to-ceiling height (habitable) in metres.")
    bathroom_height = models.FloatField(null=True, blank=True,
                                        help_text="Floor-to-ceiling height (bathroom) in metres.")
    basement_height = models.FloatField(null=True, blank=True,
                                        help_text="Basement clear height in metres.")

    # ── Optional boundary wall parameters ─────────────────────────────────────
    wall_height_road_side  = models.FloatField(null=True, blank=True,
                                               help_text="Road-side boundary wall height in metres.")
    wall_height_other_side = models.FloatField(null=True, blank=True,
                                               help_text="Non-road boundary wall height in metres.")

    # ── Optional NBC egress parameters ────────────────────────────────────────
    num_exits               = models.IntegerField(null=True, blank=True)
    corridor_width          = models.FloatField(null=True, blank=True, help_text="m")
    door_width              = models.FloatField(null=True, blank=True, help_text="m")
    travel_distance         = models.FloatField(null=True, blank=True, help_text="m")

    # ── Optional NBC fire / high-rise parameters ───────────────────────────────
    fire_separation_distance = models.FloatField(null=True, blank=True, help_text="m")
    fire_door_rating         = models.FloatField(null=True, blank=True, help_text="minutes")
    has_fire_lift            = models.BooleanField(null=True, blank=True)
    has_firefighting_shaft   = models.BooleanField(null=True, blank=True)
    refuge_area_pct          = models.FloatField(null=True, blank=True,
                                                 help_text="Refuge area as % of floor area.")

    # ── Optional FSI incentive parameter ──────────────────────────────────────
    distance_to_wide_road = models.FloatField(
        null=True, blank=True,
        help_text="Distance in metres to nearest 36 m or 45 m road (for incentive FSI check)."
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    notes      = models.TextField(blank=True, help_text="Free-form notes from architect.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"Proposal for [{self.plot.tp_scheme}] FP {self.plot.fp_number} "
            f"— H={self.building_height}m, BUA={self.total_bua}sq.ft"
        )


class ComplianceResult(models.Model):
    """
    One compliance check result row per rule per BuildingProposal.
    """

    STATUS_CHOICES = [
        ("PASS",         "Pass"),
        ("FAIL",         "Fail"),
        ("INFO",         "Info / Declaration required"),
        ("NA",           "Not applicable"),
        ("MISSING_DATA", "Missing data"),
    ]

    proposal       = models.ForeignKey(
        BuildingProposal, on_delete=models.CASCADE, related_name="compliance_results"
    )
    rule_id        = models.CharField(max_length=100)
    rule_source    = models.CharField(max_length=10,
                                      help_text='"GDCR" or "NBC"')
    category       = models.CharField(max_length=50)
    description    = models.TextField()
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES)
    required_value = models.FloatField(null=True, blank=True)
    actual_value   = models.FloatField(null=True, blank=True)
    unit           = models.CharField(max_length=20, blank=True)
    note           = models.TextField(blank=True)
    evaluated_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rule_source", "category", "rule_id"]
        unique_together = ("proposal", "rule_id")

    def __str__(self) -> str:
        return f"[{self.status}] {self.rule_id} — Proposal #{self.proposal_id}"
