from __future__ import annotations

import uuid

from django.contrib.gis.db import models

from tp_ingestion.models import Plot


class PlanJob(models.Model):
    """
    Asynchronous plan-generation job for a given plot.

    The heavy optimisation pipeline runs in a background worker and writes
    its JSON result back into this model.
    """

    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    plot = models.ForeignKey(Plot, on_delete=models.CASCADE, related_name="plan_jobs")

    inputs_json = models.JSONField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    progress = models.IntegerField(default=0)

    result_json = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


__all__ = ["PlanJob"]
