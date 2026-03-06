"""
Phase 2.3 — Full TP14 batch resolution distribution.

Run resolver at 10 m, 16.5 m, 25 m. Record per height:
  % STANDARD, % COMPACT, % STUDIO, % UNRESOLVED
  Avg band_depth_m of unresolved (template strictness)
  Avg band_length_m of width failures (width stress)

  python manage.py run_phase2_batch_validation
  python manage.py run_phase2_batch_validation --heights 10 16.5 25 --csv out.csv
"""

from __future__ import annotations

import csv
from collections import defaultdict
from typing import Optional

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot

# Reuse skeleton pipeline from run_composer_tp14
from architecture.management.commands.run_composer_tp14 import _get_skeleton_for_plot
from residential_layout.frames import derive_unit_local_frame
from residential_layout.orchestrator import resolve_unit_layout
from residential_layout.errors import UnresolvedLayoutError

DEFAULT_HEIGHTS = [10.0, 16.5, 25.0]
TP = 14
ROAD_WIDTH = 12.0


def _run_height(tp_scheme: str, height: float, road_width: float, plot_limit: Optional[int] = None):
    """
    Run resolution on every buildable TP14 plot at one height.
    Returns dict with:
      total_zones, by_template (STANDARD_1BHK, COMPACT_1BHK, STUDIO, UNRESOLVED),
      unresolved_depths (list), unresolved_lengths (list),
      width_fail_lengths (list of band_length_m when any failure was width_budget_fail)
    """
    plots = list(Plot.objects.filter(tp_scheme=tp_scheme).order_by("fp_number"))
    if not plots:
        return None
    if plot_limit is not None:
        plots = plots[:plot_limit]

    by_template = defaultdict(int)
    unresolved_depths = []
    unresolved_lengths = []
    width_fail_lengths = []

    for plot in plots:
        skeleton, err = _get_skeleton_for_plot(plot, height, road_width)
        if err or skeleton is None:
            continue
        for zi in range(len(skeleton.unit_zones)):
            zone = skeleton.unit_zones[zi]
            frame = derive_unit_local_frame(skeleton, zi)
            try:
                contract = resolve_unit_layout(zone, frame)
                name = getattr(contract, "resolved_template_name", None) or "UNKNOWN"
                by_template[name] += 1
            except UnresolvedLayoutError as e:
                by_template["UNRESOLVED"] += 1
                unresolved_depths.append(frame.band_depth_m)
                unresolved_lengths.append(frame.band_length_m)
                for fr in e.failure_reasons:
                    if fr.get("reason_code") == "width_budget_fail":
                        width_fail_lengths.append(frame.band_length_m)
                        break

    total_zones = sum(by_template.values())
    return {
        "total_zones": total_zones,
        "by_template": dict(by_template),
        "unresolved_depths": unresolved_depths,
        "unresolved_lengths": unresolved_lengths,
        "width_fail_lengths": width_fail_lengths,
    }


class Command(BaseCommand):
    help = (
        "Phase 2.3: Full TP14 batch resolution at 10 m, 16.5 m, 25 m. "
        "Outputs %% STANDARD/COMPACT/STUDIO/UNRESOLVED and diagnostic averages."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--heights",
            type=float,
            nargs="+",
            default=DEFAULT_HEIGHTS,
            help=f"Heights in metres (default: {DEFAULT_HEIGHTS})",
        )
        parser.add_argument(
            "--tp",
            type=int,
            default=TP,
            help=f"TP scheme (default: {TP})",
        )
        parser.add_argument(
            "--road-width",
            type=float,
            default=ROAD_WIDTH,
            help="Road width (m)",
        )
        parser.add_argument(
            "--csv",
            type=str,
            default=None,
            help="Write summary to CSV path",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of plots per height (for quick runs)",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        tp_scheme = f"TP{tp}"
        heights = options["heights"]
        road_width = options["road_width"]
        csv_path = options.get("csv")
        limit = options.get("limit")

        plots_count = Plot.objects.filter(tp_scheme=tp_scheme).count()
        if plots_count == 0:
            raise CommandError(f"No plots for {tp_scheme}. Run ingest first.")

        if limit is not None:
            self.stdout.write(self.style.WARNING(f"Limit: first {limit} plots per height"))

        self.stdout.write("=" * 72)
        self.stdout.write(f"Phase 2.3 — Batch resolution: {tp_scheme}, heights={heights}, road_width={road_width}m")
        self.stdout.write(f"Total plots in DB: {plots_count}")
        self.stdout.write("=" * 72)

        rows_for_csv = []
        for height in heights:
            self.stdout.write("")
            result = _run_height(tp_scheme, height, road_width, plot_limit=limit)
            if result is None or result["total_zones"] == 0:
                self.stdout.write(self.style.WARNING(f"Height {height} m — no buildable zones"))
                rows_for_csv.append({
                    "height_m": height,
                    "total_zones": 0,
                    "pct_standard": None,
                    "pct_compact": None,
                    "pct_studio": None,
                    "pct_unresolved": None,
                    "avg_band_depth_m_unresolved": None,
                    "avg_band_length_m_width_fail": None,
                })
                continue

            total = result["total_zones"]
            by_t = result["by_template"]
            n_std = by_t.get("STANDARD_1BHK", 0)
            n_compact = by_t.get("COMPACT_1BHK", 0)
            n_studio = by_t.get("STUDIO", 0)
            n_unres = by_t.get("UNRESOLVED", 0)

            pct_std = 100.0 * n_std / total if total else 0
            pct_compact = 100.0 * n_compact / total if total else 0
            pct_studio = 100.0 * n_studio / total if total else 0
            pct_unres = 100.0 * n_unres / total if total else 0

            ud = result["unresolved_depths"]
            avg_depth_unres = sum(ud) / len(ud) if ud else None
            wf = result["width_fail_lengths"]
            avg_len_width_fail = sum(wf) / len(wf) if wf else None

            self.stdout.write(self.style.SUCCESS(f"Height {height} m  (total zones = {total})"))
            self.stdout.write(
                f"  % STANDARD   = {pct_std:5.1f}%  ({n_std})  - market baseline viability"
            )
            self.stdout.write(
                f"  % COMPACT    = {pct_compact:5.1f}%  ({n_compact})  - tight band stress"
            )
            self.stdout.write(
                f"  % STUDIO     = {pct_studio:5.1f}%  ({n_studio})  - depth stress indicator"
            )
            self.stdout.write(
                f"  % UNRESOLVED = {pct_unres:5.1f}%  ({n_unres})  - fatal geometry rate"
            )
            self.stdout.write(
                f"  Avg band_depth_m (unresolved)   = {avg_depth_unres:.2f}" if avg_depth_unres is not None
                else "  Avg band_depth_m (unresolved)   = n/a"
            )
            self.stdout.write(
                f"  Avg band_length_m (width fail)   = {avg_len_width_fail:.2f}" if avg_len_width_fail is not None
                else "  Avg band_length_m (width fail)   = n/a"
            )

            rows_for_csv.append({
                "height_m": height,
                "total_zones": total,
                "pct_standard": round(pct_std, 1),
                "pct_compact": round(pct_compact, 1),
                "pct_studio": round(pct_studio, 1),
                "pct_unresolved": round(pct_unres, 1),
                "avg_band_depth_m_unresolved": round(avg_depth_unres, 2) if avg_depth_unres is not None else None,
                "avg_band_length_m_width_fail": round(avg_len_width_fail, 2) if avg_len_width_fail is not None else None,
            })

        self.stdout.write("")
        self.stdout.write("=" * 72)
        self.stdout.write(
            "If UNRESOLVED > 15% on buildable plots -> template problem. "
            "If STUDIO > 40% -> depth equation too aggressive. COMPACT rarely used -> STANDARD too permissive."
        )
        self.stdout.write("=" * 72)

        if csv_path:
            with open(csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "height_m", "total_zones", "pct_standard", "pct_compact", "pct_studio", "pct_unresolved",
                    "avg_band_depth_m_unresolved", "avg_band_length_m_width_fail",
                ])
                w.writeheader()
                w.writerows(rows_for_csv)
            self.stdout.write(f"Wrote: {csv_path}")
