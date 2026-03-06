"""
Phase 2 sanity check: pick one zone each for STANDARD, COMPACT, STUDIO.
Render zone + rooms + entry door + frontage edge + wet wall. Verify:
  - Living at frontage
  - Wet wall at core
  - Door at corridor/frontage
  - No inverted layouts

  python manage.py phase2_sanity_check --height 16.5 --out-dir ./phase2_sanity
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot
from architecture.management.commands.run_composer_tp14 import _get_skeleton_for_plot
from residential_layout.frames import derive_unit_local_frame
from residential_layout.orchestrator import resolve_unit_layout


def _find_one_per_template(tp_scheme: str, height: float, road_width: float):
    """Return [(fp_number, zone_index, template_name), ...] for STANDARD, COMPACT, STUDIO."""
    found = {}  # template_name -> (fp_number, zone_index)
    plots = list(Plot.objects.filter(tp_scheme=tp_scheme).order_by("fp_number"))
    for plot in plots:
        if len(found) >= 3:
            break
        skeleton, err = _get_skeleton_for_plot(plot, height, road_width)
        if err or skeleton is None:
            continue
        for zi in range(len(skeleton.unit_zones)):
            zone = skeleton.unit_zones[zi]
            frame = derive_unit_local_frame(skeleton, zi)
            try:
                contract = resolve_unit_layout(zone, frame)
                name = getattr(contract, "resolved_template_name", None)
                if name and name not in found:
                    found[name] = (str(plot.fp_number), zi, name, skeleton, zone, frame, contract)
            except Exception:
                pass
    return [found[k] for k in ["STANDARD_1BHK", "COMPACT_1BHK", "STUDIO"] if k in found]


def _wet_wall_segment(wet_wall_line, zone_polygon):
    """Return ((x1,y1), (x2,y2)) for drawing wet wall line across zone."""
    axis, k = wet_wall_line[0], wet_wall_line[1]
    bounds = zone_polygon.bounds
    if not bounds:
        return None
    if axis == "x":
        return ((k, bounds[1]), (k, bounds[3]))
    return ((bounds[0], k), (bounds[2], k))


def _verify_orientation(zone, frame, contract) -> list[str]:
    """Return list of failure messages; empty if all checks pass."""
    from shapely.geometry import LineString, Point
    failures = []
    # Frontage edge as line
    fe = frame.frontage_edge
    frontage_line = LineString([fe[0], fe[1]])
    # LIVING must touch frontage (entry side): at least one LIVING edge/vertex on frontage line
    living_poly = next((r.polygon for r in contract.rooms if r.room_type == "LIVING"), None)
    if living_poly:
        inter = living_poly.boundary.intersection(frontage_line)
        shared_len = getattr(inter, "length", 0.0) or 0.0
        if shared_len < 0.01:
            # Fallback: min distance of any LIVING vertex to frontage line
            min_dist = min(frontage_line.distance(Point(c[0], c[1])) for c in living_poly.exterior.coords[:4])
            if min_dist > 0.05:
                failures.append("LIVING does not touch frontage edge")
    # TOILET must have edge on wet wall (depth=0 line)
    axis, k = frame.wet_wall_line[0], frame.wet_wall_line[1]
    toilet_poly = next((r.polygon for r in contract.rooms if r.room_type == "TOILET"), None)
    if toilet_poly:
        on_line = 0
        for i in range(len(toilet_poly.exterior.coords) - 1):
            p = toilet_poly.exterior.coords[i]
            if axis == "x" and abs(p[0] - k) < 1e-4:
                on_line += 1
            elif axis == "y" and abs(p[1] - k) < 1e-4:
                on_line += 1
        if on_line < 2:
            failures.append("TOILET does not have edge on wet wall line")
    # Entry door must be on frontage
    door = contract.entry_door_segment
    if door and len(door.coords) >= 2:
        mid = Point((door.coords[0][0] + door.coords[-1][0]) / 2, (door.coords[0][1] + door.coords[-1][1]) / 2)
        dist_to_frontage = frontage_line.distance(mid)
        if dist_to_frontage > 0.1:
            failures.append("Entry door not on frontage edge")
    return failures


def _plot_one(fp_number: str, zi: int, template_name: str, skeleton, zone, frame, contract, out_path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 1, figsize=(8, 6))

    # Zone
    x, y = zone.polygon.exterior.xy
    ax.fill(x, y, color="lightgray", alpha=0.3, label="zone")
    ax.plot(x, y, color="gray", linewidth=1.5)

    # Rooms
    colors = {"LIVING": "#2ecc71", "BEDROOM": "#3498db", "TOILET": "#e67e22", "KITCHEN": "#f1c40f"}
    for ri in contract.rooms:
        c = colors.get(ri.room_type, "#95a5a6")
        xs, ys = ri.polygon.exterior.xy
        ax.fill(xs, ys, color=c, alpha=0.6, edgecolor="black", linewidth=0.8)
        cx, cy = ri.polygon.centroid.x, ri.polygon.centroid.y
        ax.annotate(ri.room_type, (cx, cy), ha="center", va="center", fontsize=9, fontweight="bold")

    # Entry door
    door = contract.entry_door_segment
    if door and len(door.coords) >= 2:
        ax.plot([door.coords[0][0], door.coords[-1][0]], [door.coords[0][1], door.coords[-1][1]],
                color="red", linewidth=4, label="entry door", zorder=5)

    # Frontage edge (entry side)
    fe = frame.frontage_edge
    ax.plot([fe[0][0], fe[1][0]], [fe[0][1], fe[1][1]], color="cyan", linewidth=3, linestyle="-", label="frontage (entry)", zorder=4)

    # Wet wall line (core side)
    seg = _wet_wall_segment(frame.wet_wall_line, zone.polygon)
    if seg:
        ax.plot([seg[0][0], seg[1][0]], [seg[0][1], seg[1][1]], color="magenta", linewidth=2, linestyle="--", label="wet wall (core)", zorder=4)

    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=7)
    ax.set_title(f"FP {fp_number} zone[{zi}] — {template_name}\nLiving at frontage, wet wall at core, door on entry edge")
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


class Command(BaseCommand):
    help = "Phase 2 sanity check: render one STANDARD, one COMPACT, one STUDIO; verify layout orientation."

    def add_arguments(self, parser):
        parser.add_argument("--height", type=float, default=16.5)
        parser.add_argument("--tp", type=int, default=14)
        parser.add_argument("--road-width", type=float, default=12.0)
        parser.add_argument("--out-dir", type=str, default="phase2_sanity")

    def handle(self, *args, **options):
        tp_scheme = f"TP{options['tp']}"
        height = options["height"]
        road_width = options["road_width"]
        out_dir = options["out_dir"]

        self.stdout.write(f"Finding one zone per template at {height} m...")
        triple = _find_one_per_template(tp_scheme, height, road_width)
        if len(triple) < 3:
            raise CommandError(
                f"Found only {len(triple)} template(s): {[t[2] for t in triple]}. Need STANDARD, COMPACT, STUDIO."
            )

        os.makedirs(out_dir, exist_ok=True)
        self.stdout.write(f"Writing plots to {out_dir}/")

        all_ok = True
        for fp_number, zi, template_name, skeleton, zone, frame, contract in triple:
            short = template_name.replace("_1BHK", "").lower()
            path = os.path.join(out_dir, f"phase2_sanity_{short}.png")
            fails = _verify_orientation(zone, frame, contract)
            if fails:
                all_ok = False
                self.stdout.write(self.style.ERROR(f"  {template_name} FP {fp_number} zone[{zi}] FAIL: {fails}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  {template_name}: FP {fp_number} zone[{zi}] PASS -> {path}"))
            _plot_one(fp_number, zi, template_name, skeleton, zone, frame, contract, path)

        self.stdout.write("")
        if all_ok:
            self.stdout.write(self.style.SUCCESS("Programmatic check: Living at frontage, wet wall at core, door on entry. No inverted layouts."))
            self.stdout.write("Visually confirm the 3 PNGs in " + out_dir + ", then lock Phase 2.")
        else:
            self.stdout.write(self.style.ERROR("Some checks failed. Fix frame/composer before locking Phase 2."))
