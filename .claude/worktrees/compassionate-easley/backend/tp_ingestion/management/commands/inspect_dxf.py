"""
Management command: inspect_dxf
--------------------------------
Prints a diagnostic summary of a DXF file without writing anything to
the database.  Useful for understanding layer structure and entity counts
before running a full ingestion.

Usage:
    python manage.py inspect_dxf <path_to_dxf>

Example:
    python manage.py inspect_dxf ../../tp_data/pal/tp14/tp14_plan.dxf
"""

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.services.dxf_reader import read_dxf


class Command(BaseCommand):
    help = "Inspect a DXF file: print layers, entity counts, and closed polyline count."

    def add_arguments(self, parser):
        parser.add_argument(
            "dxf_path",
            type=str,
            help="Path to the .dxf file to inspect.",
        )

    def handle(self, *args, **options):
        dxf_path = options["dxf_path"]

        try:
            result = read_dxf(dxf_path)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("\n=== DXF Inspection Report ===\n"))

        # ── Layers ───────────────────────────────────────────────────────────
        self.stdout.write(f"Layers ({len(result.layer_names)} total):")
        for name in sorted(result.layer_names):
            self.stdout.write(f"  • {name}")

        # ── Entity type counts ───────────────────────────────────────────────
        self.stdout.write(f"\nEntity type counts:")
        for etype, count in sorted(result.entity_type_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {etype:<20} {count:>6}")

        # ── Closed polylines (= candidate plot polygons) ─────────────────────
        self.stdout.write(
            f"\nClosed LWPOLYLINE (plot polygons extracted) : "
            f"{self.style.WARNING(str(len(result.polygons)))}"
        )

        # ── Text labels ──────────────────────────────────────────────────────
        self.stdout.write(
            f"TEXT / MTEXT labels found                  : "
            f"{self.style.WARNING(str(len(result.labels)))}"
        )

        if result.labels:
            self.stdout.write("\nSample labels (first 10):")
            for text, point in result.labels[:10]:
                self.stdout.write(f"  '{text}'  @ ({point.x:.2f}, {point.y:.2f})")

        self.stdout.write(self.style.SUCCESS("\nInspection complete.\n"))
