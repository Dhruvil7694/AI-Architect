"""
Inspect 3 real TP14 skeletons: print band_id, origin, repeat_axis,
core_facing_edge, corridor_facing_edge for visual confirmation before Phase 2.

Use this to confirm:
  - DOUBLE_LOADED: one band core-facing, one corridor-facing
  - SINGLE_LOADED: corridor-facing only
  - END_CORE: core-facing only

Run from backend:
  python manage.py inspect_tp14_skeletons
  python manage.py inspect_tp14_skeletons --fp 126 104 101
  python manage.py inspect_tp14_skeletons --plot-dir ./skeleton_plots
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot

from architecture.spatial.road_edge_detector import detect_road_edges_with_meta


# Default FP numbers from tp14_mixed_batch.csv: one per pattern
DEFAULT_FPS = {
    "DOUBLE_LOADED": 126,
    "SINGLE_LOADED": 104,
    "END_CORE": 101,
}


def _get_skeleton_for_plot(plot, height: float, road_width: float):
    """Run envelope → placement → skeleton; return (skeleton, error_message)."""
    from envelope_engine.services.envelope_service import compute_envelope
    from placement_engine.services.placement_service import compute_placement
    from placement_engine.geometry.core_fit import NO_CORE_FIT
    from floor_skeleton.services import generate_floor_skeleton
    from floor_skeleton.models import NO_SKELETON_PATTERN

    try:
        road_edges, _ = detect_road_edges_with_meta(plot.geom, None)
    except Exception as e:
        return None, f"Road edges: {e}"

    if not road_edges:
        return None, "No road edge detected"

    try:
        envelope_result = compute_envelope(
            plot_wkt=plot.geom.wkt,
            building_height=height,
            road_width=road_width,
            road_facing_edges=road_edges,
        )
    except Exception as e:
        return None, f"Envelope: {e}"

    if envelope_result.status != "VALID":
        return None, f"Envelope {envelope_result.status}: {envelope_result.error_message or ''}"

    envelope_wkt = envelope_result.envelope_polygon.wkt if envelope_result.envelope_polygon else ""

    try:
        placement_result = compute_placement(
            envelope_wkt=envelope_wkt,
            building_height_m=height,
            n_towers=1,
            min_width_m=5.0,
            min_depth_m=3.5,
        )
    except Exception as e:
        return None, f"Placement: {e}"

    if placement_result.status not in ("VALID", "TOO_TIGHT") or placement_result.n_towers_placed == 0:
        return None, f"Placement {placement_result.status}"

    cv_list = placement_result.per_tower_core_validation or []
    if not cv_list:
        return None, "No core validation"
    cv = cv_list[0]
    if cv.core_fit_status == NO_CORE_FIT:
        return None, "Core fit failed"

    try:
        skeleton = generate_floor_skeleton(
            footprint=placement_result.footprints[0],
            core_validation=cv,
        )
    except Exception as e:
        return None, f"Skeleton: {e}"

    if skeleton.pattern_used == NO_SKELETON_PATTERN:
        return None, "NO_SKELETON"

    return skeleton, None


def _print_skeleton_frames(stdout, style, fp_number: str, pattern: str, skeleton):
    """Print band_id, origin, repeat_axis, core_facing_edge, corridor_facing_edge for each zone."""
    stdout.write("")
    stdout.write(style.SUCCESS(f"  FP {fp_number}  pattern = {pattern}  zones = {len(skeleton.unit_zones)}"))
    for i, zone in enumerate(skeleton.unit_zones):
        frame = zone.local_frame
        if frame is None:
            stdout.write(style.WARNING(f"    zone[{i}]  (no local_frame)"))
            continue
        stdout.write(f"    --- band_id = {frame.band_id} ---")
        stdout.write(f"      origin         = {frame.origin}")
        stdout.write(f"      repeat_axis    = {frame.repeat_axis}")
        stdout.write(f"      core_facing_edge    = {frame.core_facing_edge}")
        stdout.write(f"      corridor_facing_edge = {frame.corridor_facing_edge}")
    stdout.write("")


def _draw_skeleton(plot_dir: str, fp_number: str, pattern: str, skeleton, out_path: str):
    """Draw footprint, core, corridor, unit zones and highlight core/corridor facing edges."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "matplotlib not available"

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

    def plot_poly(geom, color, label, alpha=0.3, linewidth=1):
        if geom is None or geom.is_empty:
            return
        x, y = geom.exterior.xy
        ax.fill(x, y, color=color, alpha=alpha, label=label)
        ax.plot(x, y, color=color, linewidth=linewidth)

    # Footprint
    plot_poly(skeleton.footprint_polygon, "gray", "footprint", alpha=0.15, linewidth=1.5)
    # Core
    plot_poly(skeleton.core_polygon, "brown", "core", alpha=0.4)
    # Corridor
    if skeleton.corridor_polygon:
        plot_poly(skeleton.corridor_polygon, "orange", "corridor", alpha=0.4)
    # Unit zones
    colors = ["green", "teal"]
    for i, zone in enumerate(skeleton.unit_zones):
        c = colors[i % len(colors)]
        plot_poly(zone.polygon, c, f"zone band_id={zone.band_id}", alpha=0.25)

    # Overlay core_facing_edge (thick red) and corridor_facing_edge (thick blue)
    core_label, corr_label = "core_facing_edge", "corridor_facing_edge"
    for zone in skeleton.unit_zones:
        frame = zone.local_frame
        if frame is None:
            continue
        if frame.core_facing_edge:
            (s, e) = frame.core_facing_edge
            ax.plot([s[0], e[0]], [s[1], e[1]], color="red", linewidth=4, label=core_label, zorder=10)
            core_label = None  # avoid duplicate legend
        if frame.corridor_facing_edge:
            (s, e) = frame.corridor_facing_edge
            ax.plot([s[0], e[0]], [s[1], e[1]], color="blue", linewidth=4, label=corr_label, zorder=10)
            corr_label = None

    ax.set_aspect("equal")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title(f"FP {fp_number} — {pattern}\nRed = core-facing edge, Blue = corridor-facing edge")
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return None


class Command(BaseCommand):
    help = (
        "Print and optionally plot 3 real TP14 skeletons with band_id, origin, repeat_axis, "
        "core_facing_edge, corridor_facing_edge for visual confirmation before Phase 2."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fp",
            type=int,
            nargs="+",
            default=[DEFAULT_FPS["DOUBLE_LOADED"], DEFAULT_FPS["SINGLE_LOADED"], DEFAULT_FPS["END_CORE"]],
            help="FP numbers to inspect (default: 126, 104, 101 for DOUBLE, SINGLE, END_CORE)",
        )
        parser.add_argument("--tp", type=int, default=14, help="TP scheme number (default 14)")
        parser.add_argument("--height", type=float, default=16.5, help="Building height (m)")
        parser.add_argument("--road-width", type=float, default=12.0, help="Road width (m)")
        parser.add_argument(
            "--plot-dir",
            type=str,
            default=None,
            help="If set, save a diagram per skeleton (footprint, core, corridor, zones, facing edges)",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        height = options["height"]
        road_width = options["road_width"]
        fp_list = options["fp"]
        plot_dir = options.get("plot_dir")

        tp_scheme = f"TP{tp}"
        self.stdout.write("=" * 70)
        self.stdout.write(f"Inspect TP14 skeletons: {tp_scheme}, height={height}m, road_width={road_width}m")
        self.stdout.write(f"FP numbers: {fp_list}")
        self.stdout.write("=" * 70)

        if plot_dir:
            os.makedirs(plot_dir, exist_ok=True)
            self.stdout.write(f"Plots will be saved to: {plot_dir}")

        for fp_number in fp_list:
            try:
                plot = Plot.objects.get(tp_scheme=tp_scheme, fp_number=str(fp_number))
            except Plot.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"FP {fp_number}: Plot not found"))
                continue

            skeleton, err = _get_skeleton_for_plot(plot, height, road_width)
            if err:
                self.stdout.write(self.style.ERROR(f"FP {fp_number}: {err}"))
                continue

            pattern = skeleton.pattern_used
            _print_skeleton_frames(self.stdout, self.style, str(fp_number), pattern, skeleton)

            if plot_dir:
                out_path = os.path.join(plot_dir, f"fp{fp_number}_{pattern.lower()}.png")
                draw_err = _draw_skeleton(plot_dir, str(fp_number), pattern, skeleton, out_path)
                if draw_err:
                    self.stdout.write(self.style.WARNING(f"FP {fp_number}: {draw_err}"))
                else:
                    self.stdout.write(f"  Saved: {out_path}")

        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write(
            "Check: DOUBLE_LOADED -> one band core-facing, one corridor-facing; "
            "SINGLE_LOADED -> corridor-facing only; END_CORE -> core-facing only."
        )
        self.stdout.write("If edges align with actual core/corridor geometry -> ready for Phase 2.")
        self.stdout.write("=" * 70)
