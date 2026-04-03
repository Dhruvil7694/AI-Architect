"""
Management command: compute_label_points
-----------------------------------------
Compute optimal label placement points for existing Plot records.

This is a one-time migration command to populate the label_point field
for plots that were ingested before the polylabel upgrade.

Usage:
    python manage.py compute_label_points --tp-scheme TP14 --city Ahmedabad
    python manage.py compute_label_points --all

Optional flags:
    --all        : Process all plots in database
    --dry-run    : Preview changes without saving
    --batch-size : Number of plots to process per batch (default: 100)
"""

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point as GEOSPoint

from tp_ingestion.models import Plot
from tp_ingestion.geometry_utils import get_label_point
from shapely.geometry import Polygon as ShapelyPolygon


class Command(BaseCommand):
    help = "Compute optimal label placement points for existing plots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--city",
            type=str,
            help="City name (e.g. Ahmedabad)",
        )
        parser.add_argument(
            "--tp-scheme",
            type=str,
            dest="tp_scheme",
            help="TP scheme identifier (e.g. TP14)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="process_all",
            help="Process all plots in database",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Preview changes without saving to database",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            dest="batch_size",
            help="Number of plots to process per batch (default: 100)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Recompute label points even if they already exist",
        )

    def handle(self, *args, **options):
        city = options.get("city")
        tp_scheme = options.get("tp_scheme")
        process_all = options["process_all"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        force = options["force"]

        if not process_all and not (city and tp_scheme):
            self.stdout.write(
                self.style.ERROR(
                    "Error: Either --all or both --city and --tp-scheme are required."
                )
            )
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode — no data will be written."))

        # Build queryset
        queryset = Plot.objects.all()
        
        if not process_all:
            queryset = queryset.filter(city=city, tp_scheme=tp_scheme)
            self.stdout.write(f"\nProcessing plots for {city} / {tp_scheme}...")
        else:
            self.stdout.write("\nProcessing all plots in database...")

        # Filter for plots without label_point (unless --force)
        if not force:
            queryset = queryset.filter(label_point__isnull=True)
            filter_msg = "without label_point"
        else:
            filter_msg = "(recomputing all)"

        total_count = queryset.count()
        
        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ No plots found {filter_msg}. All plots already have label points!"
                )
            )
            return

        self.stdout.write(f"Found {total_count} plots {filter_msg}")

        # Process in batches
        processed = 0
        updated = 0
        errors = 0

        plots_to_update = []

        for plot in queryset.iterator(chunk_size=batch_size):
            try:
                # Convert GEOS polygon to Shapely
                coords = [(pt[0], pt[1]) for pt in plot.geom.coords[0]]
                shapely_poly = ShapelyPolygon(coords)

                # Compute optimal label point
                label_pt = get_label_point(shapely_poly)
                
                # Convert to GEOS Point
                plot.label_point = GEOSPoint(label_pt.x, label_pt.y, srid=0)
                
                plots_to_update.append(plot)
                processed += 1

                # Batch update
                if len(plots_to_update) >= batch_size:
                    if not dry_run:
                        Plot.objects.bulk_update(plots_to_update, ["label_point"], batch_size=batch_size)
                        updated += len(plots_to_update)
                    
                    self.stdout.write(
                        f"  Processed {processed}/{total_count} plots...",
                        ending="\r"
                    )
                    plots_to_update = []

            except Exception as e:
                errors += 1
                self.stderr.write(
                    f"\nError processing plot {plot.id} ({plot.tp_scheme}-{plot.fp_number}): {e}"
                )

        # Update remaining plots
        if plots_to_update and not dry_run:
            Plot.objects.bulk_update(plots_to_update, ["label_point"], batch_size=batch_size)
            updated += len(plots_to_update)

        self.stdout.write("")  # New line after progress
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Dry-run complete. Would update {processed} plots."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully computed label points for {updated} plots."
                )
            )
        
        if errors > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠ {errors} plots had errors during processing.")
            )

        # Show sample results
        if not dry_run and updated > 0:
            sample = Plot.objects.filter(label_point__isnull=False).first()
            if sample:
                self.stdout.write(
                    f"\nSample: {sample.tp_scheme}-{sample.fp_number} → "
                    f"label_point: ({sample.label_point.x:.2f}, {sample.label_point.y:.2f})"
                )
