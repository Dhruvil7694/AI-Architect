"""
architecture/management/commands/generate_floorplan.py
-------------------------------------------------------
End-to-end floor plan pipeline for a single TP plot.

Loads a plot from the DB, runs all six modules in sequence, and writes a
layered DXF file.  No data is written to the database — pure read + export.

Usage
-----
    python manage.py generate_floorplan \\
        --tp 14 --fp 101 --height 16.5 --export-dir ./outputs

    python manage.py generate_floorplan \\
        --tp 14 --fp 101 --height 16.5 \\
        --road-width 12.0 --road-edges 0,1 --n-towers 1 \\
        --export-dir ./outputs

    # With professional presentation layer (double-line walls, title block):
    python manage.py generate_floorplan \\
        --tp 14 --fp 101 --height 16.5 --export-dir ./outputs --presentation

Demo plots (known-good for floor layout + DXF):
    TP14 FP101 — END_CORE, single band.
    TP14 FP126 — DOUBLE_LOADED, two bands; plan shows 15 m road fronting the plot,
                 so use --road-width 15 for validation against the cadastral map.
"""

from __future__ import annotations

import os
import sys

from django.core.management.base import BaseCommand, CommandError

from envelope_engine.geometry import METRES_TO_DXF, DXF_TO_METRES
from tp_ingestion.models import Plot
from common.units import sqft_to_sqm

from residential_layout import (
    build_floor_layout,
    build_building_layout,
    FloorAggregationError,
    FloorAggregationValidationError,
    BuildingAggregationError,
)

# Storey height for Phase 5 building aggregation (explicit; not inferred).
DEFAULT_STOREY_HEIGHT_M = 3.0


class Command(BaseCommand):
    help = (
        "Run the full Architecture AI pipeline and export a DXF floor plan. "
        "Includes Phase 4 floor layout (units, bands, metrics). "
        "Use --multi-variant to run 4 presets (SPACIOUS, DENSE, BALANCED, BUDGET) and rank results. "
        "In multi-variant mode, layout-level DXF is exported for the best-ranked successful preset; if all fail, skeleton only. "
        "Demo plots: TP14 FP101 (END_CORE), TP14 FP126 (DOUBLE_LOADED)."
    )

    # ── Argument definition ────────────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument("--tp",         type=int,   required=True,
                            help="TP scheme number (e.g. 14)")
        parser.add_argument("--fp",         type=int,   required=True,
                            help="FP number (e.g. 101)")
        parser.add_argument("--height",     type=float, required=True,
                            help="Building height in metres (e.g. 16.5)")
        parser.add_argument("--road-width", type=float, default=9.0,
                            help="Adjacent road width in metres (default: 9.0). "
                                 "Overridden by Plot.road_width_m in PostGIS when set.")
        parser.add_argument("--road-edges", type=str,   default="0",
                            help="Comma-separated 0-based edge indices facing road "
                                 '(default: "0"). Overridden by Plot.road_edges in PostGIS when set.')
        parser.add_argument("--n-towers",   type=int,   default=1,
                            help="Number of towers requested (default: 1)")
        parser.add_argument("--min-width",  type=float, default=5.0,
                            help="Minimum footprint width in metres (default: 5.0)")
        parser.add_argument("--min-depth",  type=float, default=3.5,
                            help="Minimum footprint depth in metres (default: 3.5)")
        parser.add_argument("--export-dir", type=str,   required=True,
                            help="Directory where the DXF file will be written")
        parser.add_argument("--presentation", action="store_true", default=False,
                            help="Export a professional presentation-quality DXF "
                                 "(double-line walls, room labels, door symbols). "
                                 "Falls back to skeleton DXF automatically on error.")
        parser.add_argument(
            "--ai-evaluate",
            action="store_true",
            dest="ai_evaluate",
            default=False,
            help="After building layout, call AI Evaluator for explanation and suggestions. "
                 "Requires AI_EVALUATOR_ENABLED=1 and OPENAI_API_KEY (e.g. in backend/.env).",
        )
        parser.add_argument(
            "--multi-variant",
            action="store_true",
            dest="multi_variant",
            default=False,
            help="Run pipeline with presets (default: all 4 — SPACIOUS, DENSE, BALANCED, BUDGET). "
                 "Use --preset or --presets to run a subset; order is always canonical for determinism. "
                 "Steps 1–5 run once; 5b/5c run per preset. Output: [MULTI] lines + ranking.",
        )
        parser.add_argument(
            "--ai-compare",
            action="store_true",
            dest="ai_compare",
            default=False,
            help="When --multi-variant: call AI Evaluator for comparative explanation of variants (advisory only). "
                 "Meaningful only with --multi-variant.",
        )
        parser.add_argument(
            "--preset",
            type=str,
            dest="preset",
            default=None,
            metavar="PRESET_NAME",
            help="With --multi-variant only: run a single preset (e.g. SPACIOUS). "
                 "Cannot be used with --presets. Valid names: SPACIOUS, DENSE, BALANCED, BUDGET. "
                 "Execution order is always canonical (PRESET_ORDER) for determinism.",
        )
        parser.add_argument(
            "--presets",
            type=str,
            dest="presets",
            default=None,
            metavar="PRESET1,PRESET2,...",
            help="With --multi-variant only: run a subset of presets (e.g. SPACIOUS,DENSE). "
                 "Cannot be used with --preset. Valid names: SPACIOUS, DENSE, BALANCED, BUDGET. "
                 "Execution order is always canonical (PRESET_ORDER), not the order given.",
        )

    # ── Main handler ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        tp              = options["tp"]
        fp              = options["fp"]
        height          = options["height"]
        n_towers        = options["n_towers"]
        min_width       = options["min_width"]
        min_depth       = options["min_depth"]
        export_dir      = options["export_dir"]
        use_presentation = options["presentation"]

        # ── Preset selection (Phase B): only with --multi-variant ──────────────
        preset_arg = options.get("preset")
        presets_arg = options.get("presets")
        multi_variant = options.get("multi_variant")
        if preset_arg is not None or presets_arg is not None:
            if not multi_variant:
                raise CommandError("--preset and --presets require --multi-variant.")
            if preset_arg is not None and presets_arg is not None:
                raise CommandError("Cannot use both --preset and --presets.")
            from architecture.multi_variant.presets import PRESET_ORDER
            if preset_arg is not None:
                selected_set = {preset_arg.strip()}
            else:
                selected_set = {p.strip() for p in presets_arg.split(",") if p.strip()}
            if not selected_set:
                raise CommandError("No preset names provided (--preset or --presets).")
            invalid = selected_set - set(PRESET_ORDER)
            if invalid:
                raise CommandError(
                    f"Invalid preset name(s): {sorted(invalid)!r}. Valid: {', '.join(PRESET_ORDER)}."
                )
            options["selected_presets"] = [p for p in PRESET_ORDER if p in selected_set]
        else:
            options["selected_presets"] = None

        # ── Step 1 — Load Plot ─────────────────────────────────────────────────
        plot, plot_wkt = self._step1(tp, fp)

        # Use road width/edges from dataset (PostGIS) when present; else CLI args
        road_width, road_edges = _resolve_road_params(plot, options)
        self._print_header(tp, fp, height, road_width, road_edges, n_towers,
                           use_presentation)

        # ── Step 2 — Compute Envelope ──────────────────────────────────────────
        result, envelope_wkt = self._step2(plot_wkt, height, road_width, road_edges)

        # ── Step 3 — Compute Placement (Core Fit embedded) ────────────────────
        pr = self._step3(envelope_wkt, height, n_towers, min_width, min_depth)

        # ── Step 4 — Verify Core Fit ───────────────────────────────────────────
        cv = self._step4(pr, fp)

        # ── Step 5 — Generate Floor Skeleton ──────────────────────────────────
        skeleton = self._step5(pr, cv)

        # ── Feasibility summary (aggregate from pipeline) ──────────────────────
        self._print_feasibility(plot, result, pr, skeleton, height, road_width, tp, fp)

        multi_result = None
        if options.get("multi_variant"):
            # ── Multi-variant path (Phase 6.2): 5b/5c per preset, rank, optional AI compare ──
            multi_result = self._run_multi_variant_and_print(skeleton, height, tp, fp, options)
        else:
            # ── Single-run path: 5b, 5c, optional AI evaluate, then export ──
            try:
                floor_contract = self._step5b_build_floor_layout(skeleton)
                self._print_floor_layout_summary(floor_contract)
            except (FloorAggregationError, FloorAggregationValidationError) as exc:
                msg = str(exc)
                if hasattr(exc, "reason") and exc.reason:
                    msg = f"{exc.reason}: {msg}"
                if hasattr(exc, "band_id") and hasattr(exc, "slice_index"):
                    msg = f"Band {exc.band_id} slice {exc.slice_index} — {msg}"
                self._fatal(5, f"Floor layout (Phase 4) failed: {msg}")

            try:
                building_contract = build_building_layout(
                    skeleton,
                    height_limit_m=height,
                    storey_height_m=DEFAULT_STOREY_HEIGHT_M,
                    building_id="B0",
                    module_width_m=None,
                    first_floor_contract=floor_contract,
                )
                self._print_building_summary(building_contract)
            except BuildingAggregationError as exc:
                self._fatal(
                    5,
                    f"Building layout (Phase 5) failed: floor {exc.floor_index}: {exc}",
                )

            if options.get("ai_evaluate"):
                self._optional_ai_evaluate(building_contract, plot, tp, fp)

        # ── Step 6 — Export DXF ───────────────────────────────────────────────
        # Single-run: export skeleton (or presentation). Multi-variant: export layout for best
        # preset if any succeeded, else skeleton only (Phase A).
        self._step6(skeleton, tp, fp, height, export_dir, use_presentation, multi_result)

        self.stdout.write("\nDone.")

    # ── Step implementations ──────────────────────────────────────────────────

    def _step1(self, tp: int, fp: int):
        """Load Plot from DB and return (plot, wkt)."""
        try:
            plot = Plot.objects.get(
                tp_scheme=f"TP{tp}",
                fp_number=str(fp),
            )
        except Plot.DoesNotExist:
            self._fatal(1, f"Plot TP{tp} FP{fp} not found in DB.")

        plot_wkt = plot.geom.wkt
        area_sqft = plot.plot_area_sqft
        area_sqm  = plot.plot_area_sqm

        self.stdout.write(
            f"[1] Plot Loaded         "
            f"-- Area: {area_sqft:,.1f} sq.ft ({area_sqm:.1f} sq.m)"
            f"  (TP{tp}, FP{fp})"
        )
        return plot, plot_wkt

    def _step2(self, plot_wkt: str, height: float, road_width: float,
               road_edges: list[int]):
        """Compute buildable envelope."""
        from envelope_engine.services.envelope_service import compute_envelope

        try:
            result = compute_envelope(
                plot_wkt=plot_wkt,
                building_height=height,
                road_width=road_width,
                road_facing_edges=road_edges,
            )
        except Exception as exc:
            self._fatal(2, f"Unexpected error in envelope engine: {exc}")

        if result.status != "VALID":
            self._fatal(2, f"Envelope failed ({result.status}): {result.error_message}")

        area_sqft = result.envelope_area_sqft
        area_sqm  = sqft_to_sqm(area_sqft)
        envelope_wkt = result.envelope_polygon.wkt

        self.stdout.write(
            f"[2] Envelope Computed   "
            f"-- Buildable: {area_sqft:,.1f} sq.ft ({area_sqm:.1f} sq.m)"
        )
        return result, envelope_wkt

    def _step3(self, envelope_wkt: str, height: float, n_towers: int,
               min_width: float, min_depth: float):
        """Compute building placement (includes core fit internally)."""
        from placement_engine.services.placement_service import compute_placement

        _VALID_STATUSES = {"VALID", "TOO_TIGHT"}

        try:
            pr = compute_placement(
                envelope_wkt=envelope_wkt,
                building_height_m=height,
                n_towers=n_towers,
                min_width_m=min_width,
                min_depth_m=min_depth,
            )
        except Exception as exc:
            self._fatal(3, f"Unexpected error in placement engine: {exc}")

        if pr.status not in _VALID_STATUSES or pr.n_towers_placed == 0:
            self._fatal(
                3,
                f"Placement failed: {pr.status} -- {pr.error_message}"
            )

        fp_candidate = pr.footprints[0]
        self.stdout.write(
            f"[3] Placement           "
            f"-- Towers: {pr.n_towers_placed}, "
            f"Mode: {pr.packing_mode}, "
            f"Footprint: {fp_candidate.width_m:.2f}m x {fp_candidate.depth_m:.2f}m"
        )
        return pr

    def _step4(self, pr, fp_number: int):
        """Verify the core fit result for the first tower."""
        from placement_engine.geometry.core_fit import NO_CORE_FIT

        if not pr.per_tower_core_validation:
            self._fatal(4, "No core validation result available.")

        cv = pr.per_tower_core_validation[0]

        if cv.core_fit_status == NO_CORE_FIT:
            self._fatal(
                4,
                f"No architectural core can fit in the placed footprint (FP {fp_number})."
            )

        extras = []
        if cv.n_staircases_required:
            extras.append(f"{cv.n_staircases_required} stairs")
        if cv.lift_required:
            extras.append("lift required")
        extra_str = f" ({', '.join(extras)})" if extras else ""

        self.stdout.write(
            f"[4] Core Validation     "
            f"-- {cv.core_fit_status}, Pattern: {cv.selected_pattern}{extra_str}"
        )
        return cv

    def _step5(self, pr, cv):
        """Generate the floor skeleton."""
        from floor_skeleton.services import generate_floor_skeleton
        from floor_skeleton.models import NO_SKELETON_PATTERN

        try:
            skeleton = generate_floor_skeleton(
                footprint=pr.footprints[0],
                core_validation=cv,
            )
        except Exception as exc:
            self._fatal(5, f"Unexpected error in floor skeleton generator: {exc}")

        if skeleton.pattern_used == NO_SKELETON_PATTERN:
            self._fatal(5, "Floor skeleton could not be generated (NO_SKELETON).")

        self.stdout.write(
            f"[5] Floor Skeleton      "
            f"-- Pattern: {skeleton.pattern_used}, "
            f"Label: {skeleton.placement_label}, "
            f"Efficiency: {skeleton.efficiency_ratio * 100:.1f}%"
        )
        return skeleton

    def _step5b_build_floor_layout(self, skeleton):
        """Build FloorLayoutContract from skeleton (Phase 4). Returns contract or raises."""
        return build_floor_layout(skeleton, floor_id="L0", module_width_m=None)

    def _print_floor_layout_summary(self, contract):
        """Print [5b] Floor Layout line and optional band breakdown."""
        n = contract.total_units
        b = len(contract.band_layouts)
        area = contract.unit_area_sum
        eff_pct = contract.efficiency_ratio_floor * 100.0
        self.stdout.write(
            f"[5b] Floor Layout       "
            f"-- Units: {n}, Bands: {b}, Unit area: {area:.1f} sq.m, Efficiency: {eff_pct:.1f}%"
        )
        if b > 1:
            parts = [f"Band {bl.band_id}: {bl.n_units} units" for bl in contract.band_layouts]
            self.stdout.write(f"       {', '.join(parts)}")

    def _print_building_summary(self, contract):
        """Print [5c] Building Layout line: floors, total units, total area, efficiency."""
        n_floors = contract.total_floors
        n_units = contract.total_units
        area = contract.total_unit_area
        eff_pct = contract.building_efficiency * 100.0
        self.stdout.write(
            f"[5c] Building Layout    "
            f"-- Floors: {n_floors}, Total Units: {n_units}, "
            f"Total Unit Area: {area:.1f} sq.m, Efficiency: {eff_pct:.1f}%"
        )

    def _optional_ai_evaluate(self, building_contract, plot, tp: int, fp: int):
        """Call AI Evaluator (Phase 6 AFTER layer). Never raises; AI failure is non-fatal."""
        try:
            from ai_layer import (
                get_ai_config,
                evaluate_building,
                build_contract_summary,
            )
        except ImportError:
            self.stdout.write(self.style.WARNING("[AI] ai_layer not available; skipping evaluation."))
            return
        config = get_ai_config()
        if not config.evaluator_enabled:
            self.stdout.write(self.style.WARNING("[AI] Evaluator disabled (AI_EVALUATOR_ENABLED=0)."))
            return
        if not config.has_api_key():
            self.stdout.write(self.style.WARNING("[AI] OPENAI_API_KEY not set (set in .env); skipping evaluation."))
            return
        floors_data = [
            (f.floor_id, f.total_units, f.unit_area_sum, f.efficiency_ratio_floor)
            for f in building_contract.floors
        ]
        summary = build_contract_summary(
            building_id=building_contract.building_id,
            total_floors=building_contract.total_floors,
            total_units=building_contract.total_units,
            total_unit_area=building_contract.total_unit_area,
            total_residual_area=building_contract.total_residual_area,
            building_efficiency=building_contract.building_efficiency,
            building_height_m=building_contract.building_height_m,
            floors=floors_data,
        )
        plot_area_sqm = getattr(plot, "plot_area_sqm", None)
        try:
            result = evaluate_building(summary, plot_area_sqm=plot_area_sqm)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"[AI] Evaluator failed: {exc}"))
            return
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("[AI Evaluator]"))
        self.stdout.write(f"  {result.explanation}")
        for s in result.suggestions:
            self.stdout.write(f"  - {s.suggestion_type}: {s.reason}")
        self.stdout.write("")

    def _run_multi_variant_and_print(self, skeleton, height: float, tp: int, fp: int, options: dict):
        """Phase 6.2: run 5b/5c per preset, rank, print [MULTI] lines. Returns MultiVariantResult."""
        from architecture.multi_variant import run_multi_variant

        plot_id = f"TP{tp}_FP{fp}"
        ai_compare = options.get("ai_compare", False)
        selected_presets = options.get("selected_presets")
        result = run_multi_variant(
            skeleton=skeleton,
            height_limit_m=height,
            plot_id=plot_id,
            storey_height_default=DEFAULT_STOREY_HEIGHT_M,
            building_id="B0",
            ai_compare=ai_compare,
            selected_presets=selected_presets,
        )
        self.stdout.write("")
        self.stdout.write("[MULTI] Variants")
        for v in result.variants:
            if v.success_flag and v.building_contract_summary:
                s = v.building_contract_summary
                self.stdout.write(
                    f"[MULTI] Preset: {v.preset_name} — "
                    f"Units: {s.total_units} | Floors: {s.total_floors} | Efficiency: {s.building_efficiency * 100:.1f}%"
                )
            else:
                reason = (v.failure_reason or "unknown")[:80]
                self.stdout.write(f"[MULTI] Preset: {v.preset_name} — FAILED: {reason}")
        self.stdout.write("[MULTI] Ranking:")
        for i, preset in enumerate(result.ranking, start=1):
            self.stdout.write(f"[MULTI] {i}. {preset}")
        if result.best_preset_name is not None:
            self.stdout.write(f"[MULTI] Best preset selected: {result.best_preset_name}")
        if result.comparison_note:
            self.stdout.write(f"[MULTI] AI comparison: {result.comparison_note}")
        self.stdout.write("")
        return result

    def _step6(
        self, skeleton, tp: int, fp: int, height: float,
        export_dir: str, use_presentation: bool,
        multi_result=None,
    ):
        """
        Export DXF file (skeleton, presentation, or layout from best preset).
        When multi_result is set and best_preset_name is not None, export layout-level DXF
        using that preset's building contract (no recomputation). If all presets failed,
        export skeleton only.
        """
        from dxf_export.exporter import export_floor_skeleton_to_dxf, export_layout_to_dxf

        filename    = f"TP{tp}_FP{fp}_H{_fmt_height(height)}.dxf"
        output_path = os.path.join(export_dir, filename)

        try:
            os.makedirs(export_dir, exist_ok=True)
        except OSError as exc:
            self._fatal(6, f"Cannot create export directory: {exc}")

        if multi_result is not None:
            # Phase A: multi-variant path — use best preset's contract or fallback to skeleton
            if multi_result.best_preset_name is not None and multi_result.best_variant_index is not None:
                variant = multi_result.variants[multi_result.best_variant_index]
                if variant.building_contract and variant.building_contract.floors:
                    self.stdout.write(
                        f"[MULTI] Exporting layout for best preset: {multi_result.best_preset_name}"
                    )
                    try:
                        export_layout_to_dxf(
                            variant.building_contract.floors[0],
                            output_path,
                            multi_result.best_preset_name,
                        )
                    except (OSError, ValueError) as exc:
                        self._fatal(6, f"DXF write failed: {exc}")
                    except Exception as exc:
                        self._fatal(6, f"Unexpected error during layout DXF export: {exc}")
                    self.stdout.write(f"[6] DXF Exported        -- {output_path}")
                    return
            self.stdout.write("[MULTI] All presets failed. Exporting skeleton only.")
            try:
                export_floor_skeleton_to_dxf(skeleton, output_path)
            except (OSError, ValueError) as exc:
                self._fatal(6, f"DXF write failed: {exc}")
            except Exception as exc:
                self._fatal(6, f"Unexpected error during DXF export: {exc}")
            self.stdout.write(f"[6] DXF Exported        -- {output_path}")
            return

        if use_presentation:
            self._step6_presentation(skeleton, tp, fp, height,
                                     output_path, export_floor_skeleton_to_dxf)
        else:
            try:
                export_floor_skeleton_to_dxf(skeleton, output_path)
            except (OSError, ValueError) as exc:
                self._fatal(6, f"DXF write failed: {exc}")
            except Exception as exc:
                self._fatal(6, f"Unexpected error during DXF export: {exc}")
            self.stdout.write(f"[6] DXF Exported        -- {output_path}")

    def _step6_presentation(
        self, skeleton, tp: int, fp: int, height: float,
        output_path: str, fallback_exporter,
    ):
        """
        Export with presentation layer.

        Top-level guard: if the entire presentation pipeline fails, fall back
        silently to export_floor_skeleton_to_dxf.  The command never exits
        with error due to a presentation failure.
        """
        try:
            from presentation_engine.drawing_composer import compose
            from dxf_export.presentation_exporter import export_presentation_to_dxf

            pm = compose(skeleton, tp_num=tp, fp_num=fp, height_m=height)
            export_presentation_to_dxf(pm, output_path)

            flags = []
            if pm.used_fallback_walls:
                flags.append("walls-fallback")
            if pm.used_fallback_rooms:
                flags.append("rooms-fallback")
            if pm.used_fallback_doors:
                flags.append("doors-skipped")

            mode_note = " [PRESENTATION]"
            if flags:
                mode_note += f" [{', '.join(flags)}]"
            self.stdout.write(
                f"[6] DXF Exported        -- {output_path}{mode_note}"
            )

        except Exception as exc:
            self.stdout.write(
                f"[WARN] Presentation layer failed ({type(exc).__name__}: {exc}) "
                f"— falling back to skeleton export."
            )
            try:
                fallback_exporter(skeleton, output_path)
            except (OSError, ValueError) as exc2:
                self._fatal(6, f"DXF write failed (fallback): {exc2}")
            except Exception as exc2:
                self._fatal(6, f"Unexpected error during DXF fallback: {exc2}")

    def _print_feasibility(self, plot, result, pr, skeleton, height, road_width, tp, fp):
        """Build FeasibilityAggregate from pipeline and print a short summary."""
        try:
            from architecture.feasibility.service import build_feasibility_from_pipeline

            agg = build_feasibility_from_pipeline(
                plot_geom_wkt=plot.geom.wkt,
                plot_area_sqft=plot.plot_area_sqft,
                plot_area_sqm=plot.plot_area_sqm,
                envelope_result=result,
                placement_result=pr,
                building_height_m=height,
                road_width_m=road_width,
                tp_scheme=f"TP{tp}",
                fp_number=str(fp),
                skeleton=skeleton,
                rule_results=None,
            )
            pm = agg.plot_metrics
            rm = agg.regulatory_metrics
            bm = agg.buildability_metrics
            self.stdout.write("")
            self.stdout.write("Feasibility Summary")
            self.stdout.write("-" * 40)
            depth_str = f"{pm.plot_depth_m:.1f}m" if pm.plot_depth_m is not None else "—"
            self.stdout.write(
                f"  Plot: {pm.plot_area_sqft:,.0f} sq.ft ({pm.plot_area_sqm:.1f} sq.m)  "
                f"Frontage: {pm.frontage_length_m:.1f}m  Depth: {depth_str}  "
                f"Road edges: {pm.n_road_edges}  {pm.shape_class}  {pm.height_band_label}"
            )
            self.stdout.write(
                f"  FSI: achieved {rm.achieved_fsi:.2f} (max {rm.max_fsi})  "
                f"GC: {rm.achieved_gc_pct:.1f}% (max {rm.permissible_gc_pct}%)  "
                f"COP: {rm.cop_provided_sqft:.0f} / {rm.cop_required_sqft:.0f} sq.ft"
            )
            self.stdout.write(
                f"  Buildable: {bm.envelope_area_sqft:,.0f} sq.ft  "
                f"Footprint: {bm.footprint_width_m:.2f}m x {bm.footprint_depth_m:.2f}m  "
                f"Efficiency: {bm.efficiency_ratio * 100:.1f}%"
            )
            self.stdout.write("-" * 40)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Feasibility summary skipped: {exc}"))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _print_header(self, tp: int, fp: int, height: float,
                      road_width: float, road_edges: list[int],
                      n_towers: int, presentation: bool = False) -> None:
        self.stdout.write("Architecture AI -- Floor Plan Generator")
        self.stdout.write("=" * 40)
        mode = "PRESENTATION" if presentation else "SKELETON"
        self.stdout.write(
            f"TP: {tp}  FP: {fp}  H: {height}m  "
            f"Road: {road_width}m  Edges: {road_edges}  Towers: {n_towers}  "
            f"Mode: {mode}"
        )
        self.stdout.write("")

    def _fatal(self, step: int, message: str) -> None:
        """Print a fatal error and exit."""
        self.stdout.write(f"\nERROR at step {step}: {message}")
        sys.exit(1)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _resolve_road_params(plot, options: dict) -> tuple[float, list]:
    """
    Use road width and road edges from the Plot (PostGIS) when set; else from CLI.
    So real TP/FP data in the dataset drives envelope when available.
    """
    road_width = (
        float(plot.road_width_m)
        if getattr(plot, "road_width_m", None) is not None and plot.road_width_m > 0
        else float(options.get("road_width", 9.0))
    )
    road_edges_raw = (
        (plot.road_edges or "").strip()
        if getattr(plot, "road_edges", None)
        else ""
    )
    road_edges = (
        _parse_road_edges(road_edges_raw)
        if road_edges_raw
        else _parse_road_edges(options.get("road_edges", "0"))
    )
    return road_width, road_edges


def _parse_road_edges(raw: str) -> list[int]:
    """Parse "0" or "0,1" into [0] or [0, 1]."""
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        return [0]


def _fmt_height(height: float) -> str:
    """Format height removing trailing .0  — 16.5 → "16.5",  10.0 → "10"."""
    s = f"{height:.10f}".rstrip("0").rstrip(".")
    return s
