from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tp_ingestion", "0005_road_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="plot",
            name="cached_feasibility_json",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="plot",
            name="cached_feasibility_storey_height_m",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="plot",
            name="cached_site_metrics_json",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="plot",
            name="cached_metrics_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
