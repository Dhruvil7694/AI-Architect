"""
architecture/management/commands/simulate_project_proposal.py
-------------------------------------------------------------
End-to-end regulatory simulation: Plot → GDCR → Placement → Floor plan →
Compliance → Feasibility summary → optional expected-value validation.

Mirrors real-world architect workflow. No mocks; runs full pipeline.

Usage
-----
    python manage.py simulate_project_proposal \\
        --tp 14 --fp 127 --height 16.5 --road-width 12.0 \\
        --zone R1 --authority SUDA --strict

    python manage.py simulate_project_proposal \\
        --tp 14 --fp 101 --height 16.5 --road-width 12.0 \\
        --zone R1 --authority SUDA --expected-json expected.json \\
        --export-dir ./out --strict
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot
from common.units import sqft_to_sqm

from architecture.proposal_inputs import ProposalInput
from architecture.feasibility.service import build_feasibility_from_pipeline
from architecture.feasibility.validation import (
    validate_aggregate_against_expected_json,
    ValidationCheck,
)
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta


def _margin_from_audit(edge_margin_audit: list, edge_type: str) -> float | None:
    """First margin_m for given edge_type (SIDE or REAR)."""
    for e in edge_margin_audit:
        if e.get("edge_type") == edge_type:
            m = e.get("margin_m")
            if m is not None:
                return float(m)
    return None


class Command(BaseCommand):
    help = (
        "Run full regulatory simulation: plot → envelope → placement → "
        "skeleton → rules → feasibility aggregate; optional validation and export."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, required=True, help="TP scheme number (e.g. 14)")
        parser.add_argument("--fp", type=int, required=True, help="FP number (e.g. 127)")
        parser.add_argument("--height", type=float, required=True, help="Building height (m)")
        parser.add_argument("--road-width", type=float, required=True, help="Road width (m)")
        parser.add_argument("--zone", type=str, required=True, help="Zone code (e.g. R1)")
        parser.add_argument("--authority", type=str, required=True, help="Authority (e.g. SUDA)")
        parser.add_argument(
            "--storey-height",
            type=float,
            default=None,
            help="Preferred storey height (m) for BUA estimate; omit to use default",
        )
        parser.add_argument("--rah", action="store_true", default=False, help="RAH scheme")
        parser.add_argument("--jantri-rate", type=float, default=None, help="Jantri rate")
        parser.add_argument(
            "--unit-mix",
            type=str,
            default=None,
            dest="unit_mix_preference",
            help="Unit mix preference",
        )
        parser.add_argument(
            "--expected-json",
            type=str,
            default=None,
            help="Path to JSON file with expected fsi_achieved, gc_achieved_pct, height_band, etc.",
        )
        parser.add_argument(
            "--export-dir",
            type=str,
            default=None,
            help="Directory to write feasibility_summary.json, compliance_summary.json, validation_result.json",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            default=False,
            help="Exit(1) if envelope/placement fails, non-compliant, or validation fails",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            default=False,
            help="Verbose debug output",
        )
        parser.add_argument(
            "--mixed-strategy",
            action="store_true",
            default=False,
            dest="mixed_strategy",
            help="Compute and print Phase 1 mixed unit strategy (e.g. 2x2BHK+1x3BHK).",
        )
        parser.add_argument(
            "--export-mixed-strategies-json",
            type=str,
            default=None,
            dest="export_mixed_strategies_json",
            help="When --mixed-strategy is set, write top 10 ranked strategies to this JSON path.",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        fp = options["fp"]
        height = options["height"]
        road_width = options["road_width"]
        zone = (options["zone"] or "").strip()
        authority = (options["authority"] or "").strip()
        storey_height = options.get("storey_height")
        rah = options.get("rah", False)
        jantri_rate = options.get("jantri_rate")
        unit_mix = options.get("unit_mix_preference")
        expected_json_path = options.get("expected_json")
        export_dir = options.get("export_dir")
        strict = options.get("strict", False)
        verbose = options.get("verbose", False)
        mixed_strategy = options.get("mixed_strategy", False)
        export_mixed_json = options.get("export_mixed_strategies_json")

        proposal = ProposalInput(
            tp_scheme=tp,
            fp_number=fp,
            building_height_m=height,
            road_width_m=road_width,
            zone_code=zone,
            authority=authority,
            unit_mix_preference=unit_mix,
            rah_scheme=rah,
            preferred_storey_height_m=storey_height,
            jantri_rate=jantri_rate,
        )
        errors = proposal.validate()
        if errors:
            raise CommandError("Proposal validation failed: " + "; ".join(errors))

        # Step A — Plot retrieval
        try:
            plot = Plot.objects.get(tp_scheme=f"TP{tp}", fp_number=str(fp))
        except Plot.DoesNotExist:
            raise CommandError(f"Plot not found: TP{tp} FP{fp}")

        plot_wkt = plot.geom.wkt
        plot_area_sqft = plot.plot_area_sqft
        plot_area_sqm = plot.plot_area_sqm

        if verbose:
            self.stdout.write(f"[A] Plot: {plot_area_sqft:.1f} sq.ft ({plot_area_sqm:.1f} sq.m)")

        # Step B — Envelope
        from envelope_engine.services.envelope_service import compute_envelope

        # Detect road-facing edges from spatial road layer if available; fall back
        # to longest edge when no intersection found. Fallback is logged.
        road_edges, road_fallback_used = detect_road_edges_with_meta(plot.geom, None)
        if verbose and road_fallback_used:
            self.stdout.write(self.style.WARNING("Road edge detection used fallback (longest edge)."))
        try:
            envelope_result = compute_envelope(
                plot_wkt=plot_wkt,
                building_height=height,
                road_width=road_width,
                road_facing_edges=road_edges,
            )
        except Exception as exc:
            if strict:
                raise CommandError(f"Envelope engine error: {exc}")
            self.stdout.write(self.style.ERROR(f"Envelope error: {exc}"))
            sys.exit(1)

        if envelope_result.status != "VALID":
            msg = f"Envelope failed ({envelope_result.status}): {envelope_result.error_message}"
            if strict:
                raise CommandError(msg)
            self.stdout.write(self.style.ERROR(msg))
            sys.exit(1)

        envelope_wkt = envelope_result.envelope_polygon.wkt if envelope_result.envelope_polygon else ""

        # Step C — Placement
        from placement_engine.services.placement_service import compute_placement
        from placement_engine.geometry.core_fit import NO_CORE_FIT

        try:
            placement_result = compute_placement(
                envelope_wkt=envelope_wkt,
                building_height_m=height,
                n_towers=1,
                min_width_m=5.0,
                min_depth_m=3.5,
            )
        except Exception as exc:
            if strict:
                raise CommandError(f"Placement engine error: {exc}")
            self.stdout.write(self.style.ERROR(f"Placement error: {exc}"))
            sys.exit(1)

        if placement_result.status not in ("VALID", "TOO_TIGHT") or placement_result.n_towers_placed == 0:
            msg = f"Placement failed: {placement_result.status} — {getattr(placement_result, 'error_message', '')}"
            if strict:
                raise CommandError(msg)
            self.stdout.write(self.style.ERROR(msg))
            sys.exit(1)

        cv_list = placement_result.per_tower_core_validation or []
        if not cv_list or cv_list[0].core_fit_status == NO_CORE_FIT:
            if strict:
                raise CommandError("Core fit failed: no architectural core fits placed footprint")
            self.stdout.write(self.style.ERROR("Core fit failed"))
            sys.exit(1)

        core_validation = cv_list[0]

        # Step D — Floor skeleton
        from floor_skeleton.services import generate_floor_skeleton
        from floor_skeleton.models import NO_SKELETON_PATTERN

        try:
            skeleton = generate_floor_skeleton(
                footprint=placement_result.footprints[0],
                core_validation=core_validation,
            )
        except Exception as exc:
            if strict:
                raise CommandError(f"Floor skeleton error: {exc}")
            self.stdout.write(self.style.ERROR(f"Skeleton error: {exc}"))
            sys.exit(1)

        if skeleton.pattern_used == NO_SKELETON_PATTERN:
            if strict:
                raise CommandError("Floor skeleton could not be generated")
            self.stdout.write(self.style.ERROR("Skeleton: NO_SKELETON"))
            sys.exit(1)

        # Step E — Rules engine
        from architecture.feasibility.constants import DEFAULT_STOREY_HEIGHT_M
        from rules_engine.services.evaluator import build_inputs_from_dict, evaluate_all

        storey_m = storey_height if storey_height is not None else DEFAULT_STOREY_HEIGHT_M
        num_floors_est = max(1, int(height / storey_m)) if storey_m > 0 else 1
        footprint_sqft = placement_result.footprints[0].area_sqft

        rule_params = {
            "road_width": road_width,
            "building_height": height,
            "total_bua": footprint_sqft * num_floors_est,
            "num_floors": num_floors_est,
            "ground_coverage": footprint_sqft,
            "has_basement": False,
            "is_sprinklered": False,
            "has_lift": core_validation.lift_required,
        }
        side_m = _margin_from_audit(envelope_result.edge_margin_audit, "SIDE")
        rear_m = _margin_from_audit(envelope_result.edge_margin_audit, "REAR")
        if side_m is not None:
            rule_params["side_margin"] = side_m
        if rear_m is not None:
            rule_params["rear_margin"] = rear_m

        rule_inputs = build_inputs_from_dict(plot_area_sqft, rule_params)
        rule_results = evaluate_all(rule_inputs)

        # Step F — Feasibility aggregate
        agg = build_feasibility_from_pipeline(
            plot_geom_wkt=plot_wkt,
            plot_area_sqft=plot_area_sqft,
            plot_area_sqm=plot_area_sqm,
            envelope_result=envelope_result,
            placement_result=placement_result,
            building_height_m=height,
            road_width_m=road_width,
            tp_scheme=f"TP{tp}",
            fp_number=str(fp),
            skeleton=skeleton,
            rule_results=rule_results,
            storey_height_m=storey_height,
        )

        # Strict: compliance
        if strict and agg.compliance_summary is not None and not agg.compliance_summary.compliant:
            raise CommandError(
                "Strict mode: compliance summary is not compliant "
                f"(fail={agg.compliance_summary.fail_count})"
            )

        # Expected JSON validation
        validation_checks: list[ValidationCheck] = []
        expected_dict = None
        if expected_json_path:
            if not os.path.isfile(expected_json_path):
                raise CommandError(f"Expected JSON file not found: {expected_json_path}")
            with open(expected_json_path, encoding="utf-8") as f:
                expected_dict = json.load(f)
            validation_checks = validate_aggregate_against_expected_json(agg, expected_dict)
            if strict and not all(c.passed for c in validation_checks):
                failed = [c.metric for c in validation_checks if not c.passed]
                raise CommandError(f"Strict mode: validation failed for: {failed}")

        # Export
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)
            full_dict = agg.to_dict()
            with open(os.path.join(export_dir, "feasibility_summary.json"), "w", encoding="utf-8") as f:
                json.dump(full_dict, f, indent=2)
            comp = agg.compliance_summary
            with open(os.path.join(export_dir, "compliance_summary.json"), "w", encoding="utf-8") as f:
                json.dump(
                    asdict(comp) if comp else {},
                    f,
                    indent=2,
                )
            if expected_dict is not None and validation_checks:
                val_result = {
                    "expected_file": expected_json_path,
                    "all_passed": all(c.passed for c in validation_checks),
                    "checks": [asdict(c) for c in validation_checks],
                }
                with open(os.path.join(export_dir, "validation_result.json"), "w", encoding="utf-8") as f:
                    json.dump(val_result, f, indent=2)

        # Development strategy (skeleton from same run; FeasibilityAggregate does not store it)
        from architecture.feasibility.constants import DEFAULT_STOREY_HEIGHT_M
        from development_strategy.service import resolve_development_strategy
        storey_m = agg.storey_height_used_m if agg.storey_height_used_m is not None else DEFAULT_STOREY_HEIGHT_M
        strategy_eval = resolve_development_strategy(
            skeleton, agg, height, agg.regulatory_metrics.max_fsi, storey_m
        )

        mixed_eval = None
        mixed_top = []
        if mixed_strategy:
            from development_strategy.service import resolve_mixed_development_strategy
            top_k = 10 if export_mixed_json else None
            mixed_eval, mixed_top = resolve_mixed_development_strategy(
                skeleton, agg, height, agg.regulatory_metrics.max_fsi, storey_m, top_k=top_k
            )
            if export_mixed_json and mixed_top:
                os.makedirs(os.path.dirname(export_mixed_json) or ".", exist_ok=True)
                strategies_payload = []
                for ev in mixed_top:
                    s = ev.strategy
                    from development_strategy.mixed_resolver import _mix_signature_from_counts
                    sig = _mix_signature_from_counts(s.mix)
                    strategies_payload.append({
                        "mix_signature": sig,
                        "total_units": s.total_units,
                        "bua_per_floor_sqm": round(s.total_bua_sqm / s.floors, 4),
                        "fsi_utilization": round(s.fsi_utilization, 4),
                        "efficiency_ratio": round(s.efficiency_ratio, 4),
                        "score": round(ev.score, 4),
                        "rank": ev.rank,
                    })
                with open(export_mixed_json, "w", encoding="utf-8") as f:
                    json.dump({
                        "tp": tp,
                        "fp": fp,
                        "height": height,
                        "strategies": strategies_payload,
                    }, f, indent=2)
                self.stdout.write(f"Exported top {len(mixed_top)} mixed strategies to {export_mixed_json}")

        # Console summary
        self._print_summary(agg, validation_checks, expected_dict, strategy_eval, mixed_eval, mixed_strategy)

    def _print_summary(
        self,
        agg,
        validation_checks: list[ValidationCheck],
        expected_dict: dict | None,
        strategy_eval=None,
        mixed_eval=None,
        mixed_strategy=False,
    ):
        pm = agg.plot_metrics
        rm = agg.regulatory_metrics
        bm = agg.buildability_metrics
        comp = agg.compliance_summary

        depth_str = f"{pm.plot_depth_m:.1f}" if pm.plot_depth_m is not None else "—"
        eff_pct = (bm.efficiency_ratio * 100.0) if bm.efficiency_ratio is not None else 0.0
        comp_str = "COMPLIANT" if (comp and comp.compliant) else "NON-COMPLIANT"
        val_str = "PASS" if (not validation_checks or all(c.passed for c in validation_checks)) else "FAIL"
        storey_h = agg.storey_height_used_m
        floors = agg.num_floors_estimated or 0

        self.stdout.write("")
        self.stdout.write("==============================")
        self.stdout.write("PROJECT SIMULATION SUMMARY")
        self.stdout.write("==============================")
        self.stdout.write(f"TP / FP:           {agg.audit_metadata.tp_scheme} / {agg.audit_metadata.fp_number}")
        self.stdout.write(f"Plot Area:         {pm.plot_area_sqft:,.0f} sq.ft ({pm.plot_area_sqm:.1f} sq.m)")
        self.stdout.write(f"Frontage:          {pm.frontage_length_m:.1f} m")
        self.stdout.write(f"Plot Depth:        {depth_str} m")
        self.stdout.write(f"Height Band:       {pm.height_band_label}")
        if storey_h is not None:
            self.stdout.write(f"Storey height used: {storey_h:.2f} m")
        self.stdout.write(f"Estimated floors:   {floors}")
        self.stdout.write(f"FSI (achieved/max): {rm.achieved_fsi:.2f} / {rm.max_fsi:.2f}")
        self.stdout.write(f"GC (achieved/perm): {rm.achieved_gc_pct:.1f}% / {rm.permissible_gc_pct:.1f}%")
        self.stdout.write(f"COP (prov/req):    {rm.cop_provided_sqft:.0f} / {rm.cop_required_sqft:.0f} sq.ft")
        self.stdout.write(f"Footprint (W×D):   {bm.footprint_width_m:.2f} × {bm.footprint_depth_m:.2f} m")
        self.stdout.write(f"Efficiency:        {eff_pct:.1f}%")
        self.stdout.write(f"Compliance:       {comp_str}")
        self.stdout.write(f"Validation:        {val_str}")
        self.stdout.write("==============================")

        self.stdout.write("")
        self.stdout.write("==============================")
        self.stdout.write("DEVELOPMENT STRATEGY")
        self.stdout.write("==============================")
        if strategy_eval is None:
            self.stdout.write("Recommended: — (no feasible strategy)")
        else:
            s = strategy_eval.strategy
            self.stdout.write(f"Recommended: {s.unit_type.value}")
            self.stdout.write(f"Units per floor: {s.units_per_floor}")
            self.stdout.write(f"Floors: {s.floors}")
            self.stdout.write(f"Total units: {s.total_units}")
            self.stdout.write(f"FSI usage: {s.fsi_utilization * 100.0:.0f}%")
            self.stdout.write(f"Efficiency: {s.efficiency_ratio * 100.0:.0f}%")
        self.stdout.write("==============================")

        if mixed_eval is not None:
            self.stdout.write("")
            self.stdout.write("==============================")
            self.stdout.write("DEVELOPMENT STRATEGY (MIXED)")
            self.stdout.write("==============================")
            ms = mixed_eval.strategy
            from development_strategy.mixed_resolver import _mix_signature_from_counts
            mix_sig = _mix_signature_from_counts(ms.mix)
            self.stdout.write(f"Mix: {mix_sig}")
            self.stdout.write(f"Units/Floor: {sum(ms.mix.values())}")
            self.stdout.write(f"Floors: {ms.floors}")
            self.stdout.write(f"Total Units: {ms.total_units}")
            self.stdout.write(f"FSI Utilization: {ms.fsi_utilization:.2f}")
            self.stdout.write(f"Efficiency: {ms.efficiency_ratio:.2f}")
            self.stdout.write("==============================")
        elif mixed_strategy and mixed_eval is None:
            self.stdout.write("")
            self.stdout.write("==============================")
            self.stdout.write("DEVELOPMENT STRATEGY (MIXED)")
            self.stdout.write("==============================")
            self.stdout.write("— (no feasible mixed strategy)")
            self.stdout.write("==============================")
