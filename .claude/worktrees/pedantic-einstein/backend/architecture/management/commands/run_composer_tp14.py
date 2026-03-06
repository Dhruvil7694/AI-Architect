"""
Run Phase 2 resolution on TP14 FP101 (END_CORE), FP126 (DOUBLE_LOADED),
and one minimal edge case. Uses resolve_unit_layout_from_skeleton (orchestrator)
by default for real resolution distribution. Set --no-resolve to force single template.

  python manage.py run_composer_tp14
  python manage.py run_composer_tp14 --fp 101 126
  python manage.py run_composer_tp14 --no-resolve --template COMPACT_1BHK
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from tp_ingestion.models import Plot
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta


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


class Command(BaseCommand):
    help = (
        "Run Phase 2 resolution on TP14 FP101, FP126, and minimal edge case. "
        "Uses orchestrator (STANDARD→COMPACT→STUDIO) by default; --no-resolve for single template."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fp",
            type=int,
            nargs="+",
            default=[101, 126],
            help="FP numbers (default: 101, 126)",
        )
        parser.add_argument(
            "--template",
            type=str,
            default="STANDARD_1BHK",
            choices=["STANDARD_1BHK", "COMPACT_1BHK", "STUDIO"],
            help="Template when --no-resolve (default: STANDARD_1BHK)",
        )
        parser.add_argument(
            "--no-resolve",
            action="store_true",
            help="Disable orchestrator; use single template only (legacy compose_unit).",
        )
        parser.add_argument("--tp", type=int, default=14)
        parser.add_argument("--height", type=float, default=16.5)
        parser.add_argument("--road-width", type=float, default=12.0)
        parser.add_argument(
            "--log-transitions",
            action="store_true",
            help="Enable INFO logging for orchestrator transitions.",
        )

    def handle(self, *args, **options):
        from residential_layout.frames import derive_unit_local_frame
        from residential_layout.composer import compose_unit
        from residential_layout.orchestrator import resolve_unit_layout_from_skeleton
        from residential_layout.templates import get_unit_template
        from residential_layout.errors import UnresolvedLayoutError

        if options.get("log_transitions"):
            logging.getLogger("residential_layout.orchestrator").setLevel(logging.INFO)
            if not logging.getLogger("residential_layout.orchestrator").handlers:
                h = logging.StreamHandler(self.stdout)
                h.setFormatter(logging.Formatter("%(message)s"))
                logging.getLogger("residential_layout.orchestrator").addHandler(h)

        tp = options["tp"]
        fp_list = options["fp"]
        use_resolve = not options["no_resolve"]
        template_name = options["template"]
        height = options["height"]
        road_width = options["road_width"]

        tp_scheme = f"TP{tp}"
        self.stdout.write("=" * 60)
        self.stdout.write(
            f"Run Phase 2: {tp_scheme}, FP={fp_list}, resolve={use_resolve}"
            + (f", template={template_name}" if not use_resolve else "")
        )
        self.stdout.write("=" * 60)

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
            self.stdout.write(
                self.style.SUCCESS(f"FP {fp_number}: pattern={pattern} zones={len(skeleton.unit_zones)}")
            )

            for zi in range(len(skeleton.unit_zones)):
                try:
                    if use_resolve:
                        contract = resolve_unit_layout_from_skeleton(skeleton, zi)
                    else:
                        zone = skeleton.unit_zones[zi]
                        frame = derive_unit_local_frame(skeleton, zi)
                        contract = compose_unit(zone, frame, get_unit_template(template_name))
                    room_types = [r.room_type for r in contract.rooms]
                    self.stdout.write(f"  zone[{zi}] OK: rooms={room_types}")
                except UnresolvedLayoutError as e:
                    self.stdout.write(
                        self.style.ERROR(f"  zone[{zi}] UNRESOLVED: {len(e.failure_reasons)} failures")
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  zone[{zi}] FAIL: {e}"))

        # Minimal edge case: synthetic zone at COMPACT min dimensions
        self.stdout.write("")
        self.stdout.write("Minimal edge case: zone at COMPACT_1BHK min (3.0 x 6.8)")
        from shapely.geometry import box
        from floor_skeleton.models import FloorSkeleton, UnitZone, AXIS_WIDTH_DOMINANT

        unit_poly = box(0, 0, 3.0, 6.8)
        zone = UnitZone(
            band_id=0,
            polygon=unit_poly,
            orientation_axis=AXIS_WIDTH_DOMINANT,
            zone_width_m=3.0,
            zone_depth_m=6.8,
        )
        fp = box(-1, -1, 4, 8)
        core = box(-1, -1, 0, 8)
        sk = FloorSkeleton(
            footprint_polygon=fp,
            core_polygon=core,
            corridor_polygon=None,
            unit_zones=[zone],
            pattern_used="END_CORE",
            placement_label="END_CORE_LEFT",
            area_summary={},
            efficiency_ratio=0.0,
            is_geometry_valid=True,
            passes_min_unit_guard=True,
            is_architecturally_viable=True,
            audit_log=[],
        )
        try:
            contract = resolve_unit_layout_from_skeleton(sk, 0)
            self.stdout.write(
                self.style.SUCCESS(f"  OK: rooms={[r.room_type for r in contract.rooms]}")
            )
        except UnresolvedLayoutError as e:
            self.stdout.write(self.style.ERROR(f"  UNRESOLVED: {len(e.failure_reasons)} failures"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  FAIL: {e}"))

        self.stdout.write("=" * 60)
