"""
Management command: ingest_tp
------------------------------
Runs the full TP/FP spatial ingestion pipeline for a single TP scheme.

Usage:
    python manage.py ingest_tp <dxf_path> <excel_path> --city <city> --tp-scheme <scheme>

Example:
    python manage.py ingest_tp \\
        ../../tp_data/pal/tp14/tp14_plan.dxf \\
        ../../tp_data/pal/tp14/tp14_scheme.xlsx \\
        --city Ahmedabad \\
        --tp-scheme TP14

Optional flags:
    --area-tolerance   float   Relative area error threshold (default: 0.05 = 5%)
    --snap-tolerance   float   Max label-to-polygon snap distance in DXF units (default: 1.0)
    --save-invalid             Also save records that fail area validation
    --dry-run                  Parse and validate without writing to the database
    --include-block-labels    Extract + store CAD BLOCK_NO overlay labels
"""

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.services.ingestion_service import run_ingestion


class Command(BaseCommand):
    help = "Ingest a TP scheme DXF + Excel pair into the database."

    def add_arguments(self, parser):
        parser.add_argument("dxf_path", type=str, help="Path to the TP scheme .dxf file.")
        parser.add_argument("excel_path", type=str, help="Path to the corresponding .xlsx metadata file.")

        parser.add_argument(
            "--city",
            type=str,
            required=True,
            help="City name (e.g. Ahmedabad, Surat).",
        )
        parser.add_argument(
            "--tp-scheme",
            type=str,
            required=True,
            dest="tp_scheme",
            help="TP scheme identifier (e.g. TP14, TP27).",
        )
        parser.add_argument(
            "--area-tolerance",
            type=float,
            default=0.10,
            dest="area_tolerance",
            help="Max relative area error allowed (default: 0.10 = 10%%).",
        )
        parser.add_argument(
            "--snap-tolerance",
            type=float,
            default=1.0,
            dest="snap_tolerance",
            help="Max label–polygon snap distance in DXF units (default: 1.0).",
        )
        parser.add_argument(
            "--save-invalid",
            action="store_true",
            dest="save_invalid",
            help="Save records that fail area validation (marked invalid).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Run the full pipeline but do NOT write to the database.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            dest="update_existing",
            help="Update geometry and area for existing plots (same city/tp_scheme/fp).",
        )
        parser.add_argument(
            "--polygon-layers",
            nargs="+",
            dest="polygon_layers",
            default=None,
            metavar="LAYER",
            help=(
                "DXF layer name(s) to extract FP polygons from. "
                "Example: --polygon-layers \"F.P.\". Default: all layers."
            ),
        )
        parser.add_argument(
            "--label-layers",
            nargs="+",
            dest="label_layers",
            default=None,
            metavar="LAYER",
            help=(
                "DXF layer name(s) to extract FP number labels from. "
                "Example: --label-layers \"FINAL F.P.\". Default: all layers."
            ),
        )
        parser.add_argument(
            "--debug-geojson-dir",
            type=str,
            default=None,
            dest="debug_geojson_dir",
            help=(
                "When set, exports intermediate GeoJSON for debugging: "
                "`raw_segments.geojson`, `polygonized.geojson`, `final_plots.geojson`."
            ),
        )
        parser.add_argument(
            "--snap-decimals",
            type=int,
            default=2,
            dest="snap_decimals",
            help="Coordinate snapping decimals before polygonization (default: 2).",
        )
        parser.add_argument(
            "--polygonize-buffer",
            type=float,
            default=0.0,
            dest="polygonize_buffer",
            help="Optional small buffer used as a backup polygonization attempt (default: 0).",
        )
        parser.add_argument(
            "--include-block-labels",
            action="store_true",
            dest="include_block_labels",
            help="Extract + store overlay labels from DXF layer BLOCK_NO.",
        )

    def handle(self, *args, **options):
        dxf_path = options["dxf_path"]
        excel_path = options["excel_path"]
        city = options["city"]
        tp_scheme = options["tp_scheme"]
        area_tolerance = options["area_tolerance"]
        snap_tolerance = options["snap_tolerance"]
        save_invalid = options["save_invalid"]
        dry_run = options["dry_run"]
        update_existing = options["update_existing"]
        polygon_layers = options["polygon_layers"]
        label_layers = options["label_layers"]
        debug_geojson_dir = options["debug_geojson_dir"]
        snap_decimals = options["snap_decimals"]
        polygonize_buffer = options["polygonize_buffer"]
        include_block_labels = options["include_block_labels"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode — no data will be written to the database."))

        self.stdout.write(
            f"\nStarting ingestion for {self.style.SUCCESS(city)} / "
            f"{self.style.SUCCESS(tp_scheme)} …\n"
        )

        try:
            report = run_ingestion(
                dxf_path=dxf_path,
                excel_path=excel_path,
                city=city,
                tp_scheme=tp_scheme,
                area_tolerance=area_tolerance,
                snap_tolerance=snap_tolerance,
                save_invalid=save_invalid,
                dry_run=dry_run,
                update_existing=update_existing,
                polygon_layers=polygon_layers,
                label_layers=label_layers,
                debug_geojson_dir=debug_geojson_dir,
                snap_decimals=snap_decimals,
                polygonize_buffer=polygonize_buffer,
                include_block_labels=include_block_labels,
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        # ── Print human-readable summary to stdout ───────────────────────────
        self.stdout.write(self.style.SUCCESS("\n=== Ingestion Summary ==="))
        self.stdout.write(f"  Polygons extracted   : {report.total_polygons}")
        self.stdout.write(f"  Labels found         : {report.total_labels}")
        self.stdout.write(f"  Matched              : {report.matched}")
        self.stdout.write(f"  Unmatched labels     : {len(report.unmatched_labels)}")
        self.stdout.write(f"  Not in Excel         : {len(report.fp_numbers_not_in_excel)}")
        self.stdout.write(f"  Area OK              : {report.validated_ok}")
        self.stdout.write(f"  Area FAIL            : {report.validated_fail}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"  Records (dry-run)    : {report.validated_ok}"))
        else:
            self.stdout.write(f"  Records saved        : {report.saved}")
            self.stdout.write(f"  Records updated      : {report.updated}")
            self.stdout.write(f"  Duplicates skipped   : {report.skipped_duplicates}")

        if report.unmatched_labels:
            self.stdout.write(self.style.WARNING(f"\nUnmatched labels: {report.unmatched_labels}"))

        if report.fp_numbers_not_in_excel:
            self.stdout.write(
                self.style.WARNING(f"\nFP numbers not found in Excel: {report.fp_numbers_not_in_excel}")
            )

        self.stdout.write(self.style.SUCCESS("\nIngestion complete.\n"))
