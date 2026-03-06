"""
Management command: setup_road_data
-----------------------------------
Set road_width_m and road_edges on Plot records so the pipeline uses correct
foundation data. Use after verify_plot_data to ensure areas are correct.

Modes:
  1. --from-csv <path>   Load correct values from a CSV (tp_scheme, fp_number, road_width_m, road_edges).
  2. --heuristic         Fill missing road data using longest-edge fallback and a default road width.

CSV format (header required):
  tp_scheme,fp_number,road_width_m,road_edges
  TP14,126,15,0
  TP14,127,15,0

Usage:
    python manage.py setup_road_data --from-csv road_data.csv
    python manage.py setup_road_data --heuristic --tp-scheme TP14 --default-road-width 15
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tp_ingestion.models import Plot

# Lazy import to avoid circular deps; detector lives in architecture app
def _detect_road_edges(plot: Plot):
    # Suppress per-plot INFO/WARNING during bulk heuristic run
    log = logging.getLogger("architecture.spatial.road_edge_detector")
    old_level = log.level
    log.setLevel(logging.ERROR)
    try:
        from architecture.spatial.road_edge_detector import detect_road_edges
        return detect_road_edges(plot.geom, None)
    finally:
        log.setLevel(old_level)


class Command(BaseCommand):
    help = "Set road_width_m and road_edges for plots (from CSV or heuristic)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-csv",
            type=str,
            default=None,
            dest="csv_path",
            help="Path to CSV with columns: tp_scheme, fp_number, road_width_m, road_edges.",
        )
        parser.add_argument(
            "--heuristic",
            action="store_true",
            help="Fill missing road data using longest-edge heuristic and default road width.",
        )
        parser.add_argument(
            "--city",
            type=str,
            default=None,
            help="When using --heuristic, limit to this city.",
        )
        parser.add_argument(
            "--tp-scheme",
            type=str,
            default=None,
            dest="tp_scheme",
            help="When using --heuristic, limit to this TP scheme (e.g. TP14).",
        )
        parser.add_argument(
            "--default-road-width",
            type=float,
            default=15.0,
            dest="default_road_width",
            help="Default road width in metres when using --heuristic (default: 15).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Show what would be updated without writing to the database.",
        )

    def handle(self, *args, **options):
        csv_path = options.get("csv_path")
        heuristic = options.get("heuristic")
        dry_run = options.get("dry_run", False)

        if csv_path and heuristic:
            raise CommandError("Use either --from-csv or --heuristic, not both.")
        if not csv_path and not heuristic:
            raise CommandError("Provide either --from-csv <path> or --heuristic.")

        if csv_path:
            self._apply_csv(Path(csv_path), dry_run)
        else:
            self._apply_heuristic(
                city=options.get("city"),
                tp_scheme=options.get("tp_scheme"),
                default_road_width=options.get("default_road_width", 15.0),
                dry_run=dry_run,
            )

    def _apply_csv(self, path: Path, dry_run: bool) -> None:
        if not path.exists():
            raise CommandError(f"CSV file not found: {path}")

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise CommandError("CSV has no header.")
            required = {"tp_scheme", "fp_number", "road_width_m", "road_edges"}
            key_map = {c.strip().lower(): c.strip() for c in reader.fieldnames}
            if not required.issubset(key_map.keys()):
                raise CommandError(f"CSV must have columns: {required}. Found: {list(key_map.keys())}")
            rows = list(reader)

        def get(r, k):
            col = key_map.get(k, k)
            return (r.get(col) or "").strip()

        updated = 0
        not_found = []
        with transaction.atomic():
            for r in rows:
                tp_scheme = get(r, "tp_scheme")
                fp_number = str(get(r, "fp_number"))
                rw_raw = get(r, "road_width_m")
                re_raw = str(get(r, "road_edges"))

                if not tp_scheme or not fp_number:
                    continue

                try:
                    road_width_m = float(rw_raw) if rw_raw else None
                except (TypeError, ValueError):
                    road_width_m = None

                plot = Plot.objects.filter(tp_scheme=tp_scheme, fp_number=fp_number).first()
                if not plot:
                    not_found.append(f"{tp_scheme}/{fp_number}")
                    continue

                plot.road_width_m = road_width_m
                plot.road_edges = re_raw
                if not dry_run:
                    plot.save(update_fields=["road_width_m", "road_edges"])
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(f"Updated {updated} plot(s) from CSV.")
        if not_found:
            self.stdout.write(self.style.WARNING(f"Not found in DB (no update): {not_found[:20]}{'...' if len(not_found) > 20 else ''}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes saved."))

    def _apply_heuristic(
        self,
        city: str | None,
        tp_scheme: str | None,
        default_road_width: float,
        dry_run: bool,
    ) -> None:
        qs = Plot.objects.all()
        if city:
            qs = qs.filter(city=city)
        if tp_scheme:
            qs = qs.filter(tp_scheme=tp_scheme)

        # Only fill plots that have no road data (both null/empty)
        to_fill = [
            p for p in qs
            if (p.road_width_m is None or p.road_edges is None or
                (p.road_edges or "").strip() == "")
        ]
        if not to_fill:
            self.stdout.write("No plots with missing road data found.")
            return

        updated = 0
        with transaction.atomic():
            for plot in to_fill:
                edges = _detect_road_edges(plot)
                plot.road_edges = ",".join(map(str, edges)) if edges else ""
                plot.road_width_m = default_road_width
                if not dry_run:
                    plot.save(update_fields=["road_width_m", "road_edges"])
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(f"Heuristic applied to {updated} plot(s) (default road width: {default_road_width} m).")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes saved."))
