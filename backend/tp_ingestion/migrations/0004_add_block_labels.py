from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
import django.contrib.gis.db.models.fields


class Migration(migrations.Migration):
    dependencies = [
        ("tp_ingestion", "0003_add_plot_designation"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlockLabel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text", models.CharField(max_length=50)),
                (
                    "geom",
                    django.contrib.gis.db.models.fields.PointField(srid=0),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "plot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="block_labels",
                        to="tp_ingestion.plot",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["text"], name="tp_ingestion_blocklabel_text_9f2f3a_idx"),
                    models.Index(fields=["plot", "text"], name="tp_ingestion_blocklabel_plot_t_4b6b0b_idx"),
                ],
            },
        ),
    ]

