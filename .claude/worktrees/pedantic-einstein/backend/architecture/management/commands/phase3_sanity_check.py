"""
Phase 3 sanity check: real-world geometry verification before locking Phase 3.

Run ONE visual sanity run like Phase 2, with:
  - A DOUBLE_LOADED zone (ideally N >= 3; use --fp 126 104 for a quick run, or omit --fp to scan all TP plots for longer bands)
  - A SINGLE_LOADED zone with corridor clipping
  - (Optional) A case where corridor edge spans only part of band

Renders: slice polygons, living rooms, entry doors, corridor edges, wet wall lines.
Visually confirm: no slice overlap, no slice gap (except final residual), corridor
edges clipped correctly, entry doors align to corridor for every slice, wet walls
at depth=0 for each slice.

  python manage.py phase3_sanity_check --height 16.5 --out-dir ./phase3_sanity
  python manage.py phase3_sanity_check --height 16.5 --out-dir ./phase3_sanity --fp 126 104
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot
from architecture.management.commands.run_composer_tp14 import _get_skeleton_for_plot
from residential_layout.frames import derive_unit_local_frame
from residential_layout.repetition import (
    repeat_band,
    DEFAULT_MODULE_WIDTH_M,
    _build_slice_zone,
    _clip_corridor_edge_for_slice,
    _band_depth_to_world,
)


def _wet_wall_segment_for_slice(wet_wall_line, slice_polygon):
    """Return ((x1,y1), (x2,y2)) for drawing wet wall line across slice."""
    axis, k = wet_wall_line[0], wet_wall_line[1]
    bounds = slice_polygon.bounds
    if not bounds:
        return None
    if axis == "x":
        return ((k, bounds[1]), (k, bounds[3]))
    return ((bounds[0], k), (bounds[2], k))


def _find_phase3_cases(
    tp_scheme: str,
    height: float,
    road_width: float,
    module_width_m: float,
    fp_numbers: list[int] | None = None,
):
    """
    Find: (1) DOUBLE_LOADED band with N>=3, (2) SINGLE_LOADED with corridor,
    (3) optional: band where corridor spans only part (some slices have corridor, some don't).
    Returns list of (label, fp_number, zone_index, skeleton, zone, frame, contract, N).
    """
    candidates_double = []   # (N, fp, zi, sk, zone, frame, contract)
    candidates_single = []   # (N, fp, zi, sk, zone, frame, contract)
    candidates_partial_corr = []  # (N, fp, zi, sk, zone, frame, contract) where corridor clipped to subset of slices

    qs = Plot.objects.filter(tp_scheme=tp_scheme).order_by("fp_number")
    if fp_numbers is not None:
        qs = qs.filter(fp_number__in=fp_numbers)
    plots = list(qs)
    for plot in plots:
        skeleton, err = _get_skeleton_for_plot(plot, height, road_width)
        if err or skeleton is None:
            continue
        pattern = getattr(skeleton, "pattern_used", "") or ""
        for zi in range(len(skeleton.unit_zones)):
            zone = skeleton.unit_zones[zi]
            frame = derive_unit_local_frame(skeleton, zi)
            try:
                contract = repeat_band(zone, frame, module_width_m=module_width_m)
            except Exception:
                continue
            N = contract.n_units
            if N == 0:
                continue
            origin = frame.origin
            R, D = frame.repeat_axis, frame.depth_axis
            corr = frame.corridor_edge
            # Corridor span in band-axis space
            if corr is not None:
                p0, p1 = corr[0], corr[1]
                b0 = (p0[0] - origin[0]) * R[0] + (p0[1] - origin[1]) * R[1]
                b1 = (p1[0] - origin[0]) * R[0] + (p1[1] - origin[1]) * R[1]
                corr_lo, corr_hi = min(b0, b1), max(b0, b1)
                band_len = frame.band_length_m
                # Partial: corridor does not span full band
                partial = corr_hi - corr_lo < band_len * 0.9 and (corr_lo > 0.5 or corr_hi < band_len - 0.5)
            else:
                partial = False

            if pattern == "DOUBLE_LOADED":
                candidates_double.append((N, str(plot.fp_number), zi, skeleton, zone, frame, contract))
            elif pattern == "SINGLE_LOADED":
                candidates_single.append((N, str(plot.fp_number), zi, skeleton, zone, frame, contract))
                if partial:
                    candidates_partial_corr.append((N, str(plot.fp_number), zi, skeleton, zone, frame, contract))

    out = []
    # (1) DOUBLE_LOADED with N>=3 (or best available)
    if candidates_double:
        best = max(candidates_double, key=lambda x: (x[0], -int(x[1]) if str(x[1]).isdigit() else 0))  # max N, then prefer lower fp
        N, fp, zi, sk, zone, frame, contract = best
        out.append((f"DOUBLE_LOADED_N{N}", fp, zi, sk, zone, frame, contract, N))

    # (2) SINGLE_LOADED with corridor (prefer N>=2 when available)
    if candidates_single:
        best = max(candidates_single, key=lambda x: (x[0], -int(x[1]) if x[1].isdigit() else 0))
        N, fp, zi, sk, zone, frame, contract = best
        if frame.corridor_edge is not None:
            out.append((f"SINGLE_LOADED_N{N}_corridor", fp, zi, sk, zone, frame, contract, N))
        else:
            out.append((f"SINGLE_LOADED_N{N}", fp, zi, sk, zone, frame, contract, N))

    # (3) Partial corridor if we have one and different from (2)
    if candidates_partial_corr:
        best = candidates_partial_corr[0]
        N, fp, zi, sk, zone, frame, contract = best
        already = (fp, zi) in [(c[1], c[2]) for c in out]
        if not already:
            out.append((f"PARTIAL_CORRIDOR_N{N}", fp, zi, sk, zone, frame, contract, N))

    return out


def _plot_phase3_one(
    label: str,
    fp_number: str,
    zone_index: int,
    zone,
    frame,
    contract,
    N: int,
    module_width_m: float,
    out_path: str,
):
    """Render slice polygons, living rooms, entry doors, corridor edges, wet wall lines."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    origin = frame.origin
    R = frame.repeat_axis
    D = frame.depth_axis
    band_depth_m = frame.band_depth_m
    band_axis = frame.band_axis

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

    # Parent zone (light outline)
    if zone.polygon and not zone.polygon.is_empty:
        x, y = zone.polygon.exterior.xy
        ax.fill(x, y, color="lightgray", alpha=0.2, label="parent zone")
        ax.plot(x, y, color="gray", linewidth=1, linestyle=":")

    # Slice polygons and per-slice corridor + wet wall
    for i in range(N):
        slice_zone = _build_slice_zone(zone, frame, i, module_width_m)
        poly = slice_zone.polygon
        if poly and not poly.is_empty:
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, facecolor="none", edgecolor="black", linewidth=1.2, zorder=2)
            ax.plot(xs, ys, color="black", linewidth=1.2)
            # Slice label
            cx, cy = poly.centroid.x, poly.centroid.y
            ax.annotate(f"slice {i}", (cx, cy), ha="center", va="center", fontsize=8)

        slice_start = i * module_width_m
        slice_end = slice_start + module_width_m
        corridor_clipped = _clip_corridor_edge_for_slice(
            origin, R, D, frame.corridor_edge, slice_start, slice_end
        )
        if corridor_clipped is not None:
            ax.plot(
                [corridor_clipped[0][0], corridor_clipped[1][0]],
                [corridor_clipped[0][1], corridor_clipped[1][1]],
                color="blue", linewidth=3, label="corridor (clip)" if i == 0 else None, zorder=4,
            )

        # Wet wall line for this slice
        origin_slice = _band_depth_to_world(origin, R, D, slice_start, 0)
        if band_axis == "X":
            wet_wall_line = ("y", origin_slice[1])
        else:
            wet_wall_line = ("x", origin_slice[0])
        seg = _wet_wall_segment_for_slice(wet_wall_line, poly)
        if seg:
            ax.plot(
                [seg[0][0], seg[1][0]], [seg[0][1], seg[1][1]],
                color="magenta", linewidth=1.5, linestyle="--", label="wet wall" if i == 0 else None, zorder=3,
            )

    # Living rooms (all units)
    colors = {"LIVING": "#2ecc71", "BEDROOM": "#3498db", "TOILET": "#e67e22", "KITCHEN": "#f1c40f"}
    for u in contract.units:
        for ri in u.rooms:
            c = colors.get(ri.room_type, "#95a5a6")
            xs, ys = ri.polygon.exterior.xy
            ax.fill(xs, ys, color=c, alpha=0.6, edgecolor="black", linewidth=0.8)
            cx, cy = ri.polygon.centroid.x, ri.polygon.centroid.y
            ax.annotate(ri.room_type, (cx, cy), ha="center", va="center", fontsize=7)

    # Entry doors (all units)
    for u in contract.units:
        door = u.entry_door_segment
        if door and len(door.coords) >= 2:
            ax.plot(
                [door.coords[0][0], door.coords[-1][0]],
                [door.coords[0][1], door.coords[-1][1]],
                color="red", linewidth=4, label="entry door" if u == contract.units[0] else None, zorder=5,
            )

    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=7)
    ax.set_title(
        f"Phase 3 sanity — {label} (FP {fp_number} zone[{zone_index}], N={N})\n"
        "Slices | Living | Doors | Corridor edges (clipped) | Wet walls (depth=0)"
    )
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


class Command(BaseCommand):
    help = (
        "Phase 3 sanity: render DOUBLE_LOADED (N>=3), SINGLE_LOADED with corridor, "
        "and optional partial-corridor. Verify slice geometry and corridor clipping visually."
    )

    def add_arguments(self, parser):
        parser.add_argument("--height", type=float, default=16.5)
        parser.add_argument("--tp", type=int, default=14)
        parser.add_argument("--road-width", type=float, default=12.0)
        parser.add_argument("--out-dir", type=str, default="phase3_sanity")
        parser.add_argument("--module-width", type=float, default=None, help="Module width (m); default 3.6")
        parser.add_argument(
            "--fp",
            type=int,
            nargs="+",
            default=None,
            help="Limit to these FP numbers (e.g. 126 104). If omitted, scan all TP plots.",
        )

    def handle(self, *args, **options):
        tp_scheme = f"TP{options['tp']}"
        height = options["height"]
        road_width = options["road_width"]
        out_dir = options["out_dir"]
        module_width_m = options.get("module_width") or DEFAULT_MODULE_WIDTH_M
        fp_numbers = options.get("fp")

        self.stdout.write(f"Finding Phase 3 cases (DOUBLE_LOADED N>=3, SINGLE_LOADED corridor) at {height} m...")
        cases = _find_phase3_cases(tp_scheme, height, road_width, module_width_m, fp_numbers=fp_numbers)
        if not cases:
            raise CommandError(
                "No bands found. Ensure TP14 has DOUBLE_LOADED and SINGLE_LOADED skeletons with N>=1."
            )

        os.makedirs(out_dir, exist_ok=True)
        self.stdout.write(f"Rendering {len(cases)} case(s) to {out_dir}/")

        for label, fp_number, zi, skeleton, zone, frame, contract, N in cases:
            safe_label = label.replace(" ", "_").replace("(", "").replace(")", "")
            path = os.path.join(out_dir, f"phase3_sanity_{safe_label}.png")
            _plot_phase3_one(label, fp_number, zi, zone, frame, contract, N, module_width_m, path)
            self.stdout.write(self.style.SUCCESS(f"  {label}: FP {fp_number} zone[{zi}] N={N} -> {path}"))

        self.stdout.write("")
        self.stdout.write(
            "Visually confirm: no slice overlap, no slice gap (except residual), "
            "corridor edges clipped correctly, entry doors on corridor/frontage, wet walls at depth=0."
        )
        self.stdout.write("If geometry looks correct -> lock Phase 3. This is the last geometry risk.")
