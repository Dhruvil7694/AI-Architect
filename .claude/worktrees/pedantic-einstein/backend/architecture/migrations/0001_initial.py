from __future__ import annotations

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tp_ingestion", "0003_add_plot_designation"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("inputs_json", models.JSONField()),
                (
                    "status",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("PENDING", "Pending"),
                            ("RUNNING", "Running"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                    ),
                ),
                ("progress", models.IntegerField(default=0)),
                ("result_json", models.JSONField(null=True, blank=True)),
                ("error_message", models.TextField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                (
                    "plot",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="plan_jobs",
                        to="tp_ingestion.plot",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]

