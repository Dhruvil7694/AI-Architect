"""
Run simulate_project_proposal pipeline on all plots for a TP scheme.
Outputs one CSV row per plot with all parameters (or status/error when pipeline fails).
"""

from __future__ import annotations

import csv
import os

from django.core.management.base import BaseCommand, CommandError

from tp_ingestion.models import Plot

from architecture.spatial.road_edge_detector import (
    detect_road_edges_with_meta,
    select_governing_road_edges,
)
from architecture.feasibility.constants import DEFAULT_STOREY_HEIGHT_M


FIDELITY_PROFILE_TP14_V1 = "tp14_fidelity_v1"


def _parse_road_edges(road_edges_raw: str) -> list[int]:
    if not road_edges_raw:
        return []
    out: list[int] = []
    for part in str(road_edges_raw).split(","):
        p = part.strip()
        if not p:
            continue
        try:
            idx = int(p)
        except ValueError:
            continue
        if idx >= 0:
            out.append(idx)
    return sorted(set(out))


def _load_benchmark_fp_numbers(path: str) -> set[str]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "fp_number" not in (reader.fieldnames or []):
            raise CommandError("Benchmark CSV must contain `fp_number` column.")
        return {str(r.get("fp_number", "")).strip() for r in reader if str(r.get("fp_number", "")).strip()}


def _fp_sort_key(fp_number: str) -> tuple[int, int, str]:
    s = str(fp_number)
    try:
        return (0, int(s.split("/")[0]), s)
    except ValueError:
        return (1, 0, s)


def _classify_winner_mix(mix_str: str) -> str:
    """Classify mix as STUDIO-only, 1BHK-only, 2BHK-only, 3BHK-only, or Mixed."""
    if not mix_str or not mix_str.strip():
        return "—"
    parts = [p.strip() for p in mix_str.split("+") if p.strip()]
    if len(parts) > 1:
        return "Mixed"
    if not parts:
        return "—"
    # e.g. "3x2BHK" -> 2BHK-only
    part = parts[0]
    if "STUDIO" in part:
        return "STUDIO-only"
    if "1BHK" in part:
        return "1BHK-only"
    if "2BHK" in part:
        return "2BHK-only"
    if "3BHK" in part:
        return "3BHK-only"
    return "Mixed"


def _print_mixed_analysis_summary(stdout, style, rows: list[dict]) -> None:
    """Compute and print Phase 1 mixed strategy analysis (required before Phase 2)."""
    with_mixed = [r for r in rows if (r.get("mixed_mix") or "").strip()]
    n_with_mixed = len(with_mixed)
    if n_with_mixed == 0:
        stdout.write("")
        stdout.write("Mixed strategy summary: no plots with feasible mixed result.")
        return

    mixed_beats = sum(1 for r in with_mixed if r.get("mixed_is_mixed") == "Y")
    pct_mixed_beats = 100.0 * mixed_beats / n_with_mixed if n_with_mixed else 0.0

    diversity_scores = []
    fsi_utils = []
    units_per_floor_vals = []
    distribution = {"STUDIO-only": 0, "1BHK-only": 0, "2BHK-only": 0, "3BHK-only": 0, "Mixed": 0}

    for r in with_mixed:
        mix_str = (r.get("mixed_mix") or "").strip()
        if not mix_str:
            continue
        dist_key = _classify_winner_mix(mix_str)
        if dist_key != "—":
            distribution[dist_key] = distribution.get(dist_key, 0) + 1
        d = r.get("mixed_diversity_score")
        if d != "" and d is not None:
            try:
                diversity_scores.append(float(d))
            except (TypeError, ValueError):
                pass
        f = r.get("mixed_fsi_usage_pct")
        if f != "" and f is not None:
            try:
                fsi_utils.append(float(f))
            except (TypeError, ValueError):
                pass
        u = r.get("mixed_units_per_floor")
        if u != "" and u is not None:
            try:
                units_per_floor_vals.append(int(u))
            except (TypeError, ValueError):
                pass

    avg_diversity = sum(diversity_scores) / len(diversity_scores) if diversity_scores else 0.0
    avg_fsi = sum(fsi_utils) / len(fsi_utils) if fsi_utils else 0.0
    maxed_cap_count = sum(1 for u in units_per_floor_vals if u >= 6)

    stdout.write("")
    stdout.write("==================================================")
    stdout.write("MIXED STRATEGY ANALYSIS (Phase 1)")
    stdout.write("==================================================")
    stdout.write(f"Plots with mixed result:     {n_with_mixed} (of {len(rows)} total)")
    stdout.write(f"% where mixed beats homogeneous: {pct_mixed_beats:.1f}%  ({mixed_beats} / {n_with_mixed})")
    stdout.write(f"Average diversity score (winners): {avg_diversity:.4f}")
    stdout.write(f"Average FSI utilization (winners): {avg_fsi:.1f}%")
    stdout.write(f"Cases maxing unit cap (>=6/floor): {maxed_cap_count}  (of {n_with_mixed})")
    stdout.write("")
    stdout.write("Distribution of chosen unit types:")
    for k in ["STUDIO-only", "1BHK-only", "2BHK-only", "3BHK-only", "Mixed"]:
        count = distribution.get(k, 0)
        pct = 100.0 * count / n_with_mixed if n_with_mixed else 0
        stdout.write(f"  {k}: {count} ({pct:.1f}%)")
    stdout.write("==================================================")
    stdout.write("")
    # Interpretation hints
    if maxed_cap_count >= 0.95 * n_with_mixed:
        stdout.write(style.WARNING("> Strong density bias: >=95% of winners max out units per floor."))
    if distribution.get("3BHK-only", 0) <= 1 and n_with_mixed > 10:
        stdout.write(style.WARNING("> Very few 3BHK-only winners: luxury bias may be too weak."))
    if pct_mixed_beats < 10 and n_with_mixed > 10:
        stdout.write(style.WARNING("> Almost no mixed winners: diversity weight may be too low."))
    stdout.write("")


def _run_one_plot(
    plot,
    height: float,
    road_width: float,
    storey_height_m: float | None,
    mixed_strategy: bool = False,
    fidelity_profile: str = "",
    strict_missing_road_width: bool = True,
    maximize_fsi: bool = False,
) -> dict:
    """Run full pipeline for one plot. Return dict of all parameters; use empty/status for failures."""
    fp_number = plot.fp_number
    plot_area_sqft = plot.plot_area_sqft
    plot_area_sqm = plot.plot_area_sqm

    row = {
        "fp_number": fp_number,
        "plot_area_sqft": round(plot_area_sqft, 2),
        "plot_area_sqm": round(plot_area_sqm, 2),
        "shape_class": "",
        "frontage_m": "",
        "depth_m": "",
        "height_band": "",
        "envelope_status": "",
        "placement_status": "",
        "core_status": "",
        "skeleton_status": "",
        "skeleton_valid": "",
        "compliance_status": "",
        "fsi_achieved": "",
        "fsi_max": "",
        "gc_achieved_pct": "",
        "gc_permissible_pct": "",
        "cop_provided_sqft": "",
        "cop_required_sqft": "",
        "cop_pct": "",
        "storey_height_used_m": "",
        "num_floors_estimated": "",
        "footprint_width_m": "",
        "footprint_depth_m": "",
        "efficiency_pct": "",
        "core_failed": "",
        "fallback_road_used": "",
        "error": "",
        # Development strategy (when skeleton valid)
        "strategy_unit_type": "",
        "strategy_units_per_floor": "",
        "strategy_floors": "",
        "strategy_total_units": "",
        "strategy_fsi_usage_pct": "",
        "strategy_efficiency_pct": "",
        "mixed_mix": "",
        "mixed_is_mixed": "",
        "mixed_diversity_score": "",
        "mixed_fsi_usage_pct": "",
        "mixed_units_per_floor": "",
        "mixed_total_units": "",
        # Fidelity metadata (blank outside fidelity profile runs)
        "fidelity_profile_id": "",
        "road_width_source": "",
        "road_edge_source": "",
        "road_edge_count": "",
        "governing_road_edge_count": "",
        "governing_road_edges": "",
        "corridor_eligible": "",
        "corridor_distance_m": "",
        "fsi_zone": "",
        "fsi_authority": "",
        "counted_bua_sqft": "",
        "premium_additional_fsi_used": "",
        "fidelity_flag": "",
        "compliance_pass": "N",
    }

    storey_m = storey_height_m if storey_height_m is not None else DEFAULT_STOREY_HEIGHT_M

    road_width_used = road_width
    road_width_source = "CLI_FIXED"
    road_edge_source = ""
    road_edges: list[int] = []
    fallback_used = False

    if fidelity_profile == FIDELITY_PROFILE_TP14_V1:
        row["fidelity_profile_id"] = fidelity_profile
        pw = float(getattr(plot, "road_width_m", 0.0) or 0.0)
        if pw > 0.0:
            road_width_used = pw
            road_width_source = "PLOT_FIELD"
        else:
            road_width_source = "MISSING"
            row["road_width_source"] = road_width_source
            row["fidelity_flag"] = "ROAD_WIDTH_MISSING"
            row["envelope_status"] = "SKIPPED"
            row["error"] = "Road width missing in Plot.road_width_m under fidelity profile."
            if strict_missing_road_width:
                return row
            road_width_used = road_width
            row["fidelity_flag"] = "ROAD_WIDTH_MISSING_FALLBACK_CLI"

    # Road edges
    try:
        edges_from_field = _parse_road_edges(getattr(plot, "road_edges", ""))
        if fidelity_profile == FIDELITY_PROFILE_TP14_V1 and edges_from_field:
            road_edges = edges_from_field
            fallback_used = False
            road_edge_source = "ROAD_EDGES_FIELD"
        else:
            road_edges, fallback_used = detect_road_edges_with_meta(plot.geom, None)
            road_edge_source = "FALLBACK_LONGEST_EDGE" if fallback_used else "DETECTED_GEOMETRY"
        row["fallback_road_used"] = "Y" if fallback_used else "N"
        selected_road_edges, road_meta = select_governing_road_edges(plot.geom, road_edges)
        road_edges = selected_road_edges or road_edges
        row["road_edge_source"] = road_edge_source
        row["road_edge_count"] = int(road_meta.get("total_road_edges_detected", len(road_edges)))
        row["governing_road_edge_count"] = len(road_edges)
        row["governing_road_edges"] = ",".join(str(i) for i in road_edges)
        row["road_width_source"] = road_width_source
    except Exception as e:
        row["envelope_status"] = "ERROR"
        row["error"] = str(e)[:200]
        return row

    if not road_edges:
        row["envelope_status"] = "NO_ROAD_EDGE"
        row["error"] = "No road edge detected"
        return row

    if maximize_fsi:
        from architecture.regulatory.development_optimizer import evaluate_development_configuration
        from architecture.regulatory_accessors import get_dynamic_max_fsi, get_max_fsi, get_max_ground_coverage_pct

        solution = evaluate_development_configuration(
            plot=plot,
            storey_height_m=storey_m,
            min_width_m=5.0,
            min_depth_m=3.5,
            mode="development",
            debug=False,
        )
        if solution.n_towers <= 0 or solution.floors <= 0:
            row["envelope_status"] = "INFEASIBLE"
            row["placement_status"] = "INFEASIBLE"
            row["compliance_status"] = "NON-COMPLIANT"
            row["compliance_pass"] = "N"
            row["error"] = "No feasible max-FSI development configuration found."
            return row

        try:
            fsi_max = get_dynamic_max_fsi(
                float(plot_area_sqft),
                road_width_used,
                plot=plot,
                authority=None,
                zone=None,
            )
        except Exception:
            fsi_max = get_max_fsi()

        row["envelope_status"] = "VALID"
        row["placement_status"] = "VALID"
        row["core_status"] = "OPTIMIZED"
        row["skeleton_status"] = "OPTIMIZED"
        row["skeleton_valid"] = "Y"
        row["compliance_status"] = "COMPLIANT"
        row["compliance_pass"] = "Y"
        row["fsi_achieved"] = round(float(solution.achieved_fsi), 4)
        row["fsi_max"] = round(float(fsi_max), 2)
        row["gc_achieved_pct"] = round(float(solution.gc_utilization_pct), 2)
        row["gc_permissible_pct"] = round(float(get_max_ground_coverage_pct()), 2)
        row["cop_provided_sqft"] = round(float(solution.cop_area_sqft or 0.0), 2)
        row["cop_required_sqft"] = round(float(plot_area_sqft) * 0.10, 2)
        if row["cop_required_sqft"]:
            row["cop_pct"] = round(100.0 * float(row["cop_provided_sqft"]) / float(row["cop_required_sqft"]), 2)
        row["storey_height_used_m"] = round(storey_m, 2)
        row["num_floors_estimated"] = int(solution.floors)
        row["counted_bua_sqft"] = round(float(getattr(solution, "exclusion_adjusted_bua_sqft", 0.0) or 0.0), 2)
        pb = getattr(solution, "premium_breakdown", None) or {}
        row["premium_additional_fsi_used"] = pb.get("additional_fsi_used", "")
        try:
            from architecture.regulatory.fsi_policy import resolve_fsi_policy
            d = resolve_fsi_policy(
                plot=plot,
                road_width_m=road_width_used,
                authority_override=None,
                zone_override=None,
                distance_to_wide_road_m=None,
            )
            row["corridor_eligible"] = "Y" if d.corridor_eligible else "N"
            row["corridor_distance_m"] = round(float(d.corridor_distance_m), 3) if d.corridor_distance_m is not None else ""
            row["fsi_zone"] = d.zone
            row["fsi_authority"] = d.authority
        except Exception:
            pass
        if solution.per_tower_footprint_sqft:
            footprint_sqft = float(solution.per_tower_footprint_sqft[0])
            row["efficiency_pct"] = ""
            row["footprint_width_m"] = ""
            row["footprint_depth_m"] = ""
        row["core_failed"] = "N"
        row["error"] = ""
        return row

    # Envelope
    from envelope_engine.services.envelope_service import compute_envelope

    try:
        envelope_result = compute_envelope(
            plot_wkt=plot.geom.wkt,
            building_height=height,
            road_width=road_width_used,
            road_facing_edges=road_edges,
        )
    except Exception as e:
        row["envelope_status"] = "ERROR"
        row["error"] = str(e)[:200]
        return row

    row["envelope_status"] = envelope_result.status or "UNKNOWN"

    # Plot metrics (need envelope edge_margin_audit) — compute even if envelope fails
    from architecture.feasibility.plot_metrics import compute_plot_metrics

    try:
        pm = compute_plot_metrics(
            plot_geom_wkt=plot.geom.wkt,
            plot_area_sqft=plot_area_sqft,
            plot_area_sqm=plot_area_sqm,
            edge_margin_audit=envelope_result.edge_margin_audit,
            building_height_m=height,
        )
        row["shape_class"] = pm.shape_class or ""
        row["frontage_m"] = round(pm.frontage_length_m, 3) if pm.frontage_length_m is not None else ""
        row["depth_m"] = round(pm.plot_depth_m, 3) if pm.plot_depth_m is not None else ""
        row["height_band"] = pm.height_band_label or ""
    except Exception:
        # If margin audit or geometry is not available, plot metrics remain blank.
        pass

    if envelope_result.status != "VALID":
        row["error"] = (envelope_result.error_message or "")[:200]
        return row

    envelope_wkt = envelope_result.envelope_polygon.wkt if envelope_result.envelope_polygon else ""

    # Placement
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
    except Exception as e:
        row["placement_status"] = "ERROR"
        row["error"] = str(e)[:200]
        return row

    row["placement_status"] = placement_result.status or "UNKNOWN"
    # Allow NO_FIT_CORE to proceed so we can record core failure / footprint metrics.
    if placement_result.status in ("NO_FIT", "INVALID_INPUT", "ERROR") or placement_result.n_towers_placed == 0:
        row["error"] = getattr(placement_result, "error_message", "")[:200] or "Placement failed"
        return row

    cv_list = placement_result.per_tower_core_validation or []
    if not cv_list:
        row["core_status"] = "NO_RESULT"
        row["error"] = "No core validation"
        return row
    cv = cv_list[0]
    row["core_status"] = cv.core_fit_status or ""
    if cv.core_fit_status == NO_CORE_FIT:
        row["core_failed"] = "Y"
        # For NO_FIT_CORE we still want footprint dimensions.
        if placement_result.footprints:
            fp0 = placement_result.footprints[0]
            row["footprint_width_m"] = round(fp0.width_m, 3)
            row["footprint_depth_m"] = round(fp0.depth_m, 3)
        row["error"] = "Core fit failed"
        return row

    # Skeleton
    from floor_skeleton.services import generate_floor_skeleton
    from floor_skeleton.models import NO_SKELETON_PATTERN

    try:
        skeleton = generate_floor_skeleton(
            footprint=placement_result.footprints[0],
            core_validation=cv,
        )
        row["skeleton_status"] = skeleton.pattern_used or "UNKNOWN"
        if skeleton.pattern_used == NO_SKELETON_PATTERN:
            row["error"] = "NO_SKELETON"
            return row
    except Exception as e:
        row["skeleton_status"] = "ERROR"
        row["error"] = str(e)[:200]
        return row

    # Rules + Feasibility
    from rules_engine.services.evaluator import build_inputs_from_dict, evaluate_all
    from architecture.feasibility.service import build_feasibility_from_pipeline
    from architecture.management.commands.simulate_project_proposal import _margin_from_audit

    num_floors_est = max(1, int(height / storey_m)) if storey_m > 0 else 1
    footprint_sqft = placement_result.footprints[0].area_sqft
    rule_params = {
        "road_width": road_width_used,
        "building_height": height,
        "total_bua": footprint_sqft * num_floors_est,
        "num_floors": num_floors_est,
        "ground_coverage": footprint_sqft,
        "has_basement": False,
        "is_sprinklered": False,
        "has_lift": cv.lift_required,
    }
    side_m = _margin_from_audit(envelope_result.edge_margin_audit, "SIDE")
    rear_m = _margin_from_audit(envelope_result.edge_margin_audit, "REAR")
    if side_m is not None:
        rule_params["side_margin"] = side_m
    if rear_m is not None:
        rule_params["rear_margin"] = rear_m
    rule_inputs = build_inputs_from_dict(plot_area_sqft, rule_params)
    rule_results = evaluate_all(rule_inputs)

    agg = build_feasibility_from_pipeline(
        plot_geom_wkt=plot.geom.wkt,
        plot_area_sqft=plot_area_sqft,
        plot_area_sqm=plot_area_sqm,
        envelope_result=envelope_result,
        placement_result=placement_result,
        building_height_m=height,
        road_width_m=road_width_used,
        tp_scheme=plot.tp_scheme,
        fp_number=fp_number,
        skeleton=skeleton,
        rule_results=rule_results,
        storey_height_m=storey_height_m,
    )

    rm = agg.regulatory_metrics
    bm = agg.buildability_metrics
    comp = agg.compliance_summary

    row["compliance_status"] = "COMPLIANT" if (comp and comp.compliant) else "NON-COMPLIANT"
    row["compliance_pass"] = "Y" if row["compliance_status"] == "COMPLIANT" else "N"
    row["fsi_achieved"] = round(rm.achieved_fsi, 4)
    row["fsi_max"] = round(rm.max_fsi, 2)
    row["gc_achieved_pct"] = round(rm.achieved_gc_pct, 2)
    row["gc_permissible_pct"] = round(rm.permissible_gc_pct, 2)
    row["cop_provided_sqft"] = round(rm.cop_provided_sqft, 2)
    row["cop_required_sqft"] = round(rm.cop_required_sqft, 2)
    row["cop_pct"] = round(100.0 * rm.cop_provided_sqft / rm.cop_required_sqft, 2) if rm.cop_required_sqft else ""
    row["storey_height_used_m"] = round(agg.storey_height_used_m, 2) if agg.storey_height_used_m is not None else ""
    row["num_floors_estimated"] = agg.num_floors_estimated or ""
    row["footprint_width_m"] = round(bm.footprint_width_m, 3)
    row["footprint_depth_m"] = round(bm.footprint_depth_m, 3)
    row["efficiency_pct"] = round(bm.efficiency_ratio * 100.0, 2) if bm.efficiency_ratio is not None else ""
    row["skeleton_valid"] = "Y" if row["skeleton_status"] not in ("", "NO_SKELETON", "ERROR") else "N"
    if row["core_failed"] == "":
        row["core_failed"] = "Y" if row.get("placement_status") == "NO_FIT_CORE" else "N"

    # Development strategy (only when we have valid skeleton + agg)
    from development_strategy.service import resolve_development_strategy

    strategy_eval = resolve_development_strategy(
        skeleton, agg, height, rm.max_fsi, agg.storey_height_used_m or storey_m
    )
    if strategy_eval is not None:
        s = strategy_eval.strategy
        row["strategy_unit_type"] = s.unit_type.value
        row["strategy_units_per_floor"] = s.units_per_floor
        row["strategy_floors"] = s.floors
        row["strategy_total_units"] = s.total_units
        row["strategy_fsi_usage_pct"] = round(s.fsi_utilization * 100.0, 2) if s.fsi_utilization is not None else ""
        row["strategy_efficiency_pct"] = round(s.efficiency_ratio * 100.0, 2) if s.efficiency_ratio is not None else ""

    # Mixed strategy (Phase 1), when requested
    if mixed_strategy:
        from development_strategy.service import resolve_mixed_development_strategy
        from development_strategy.mixed_resolver import _mix_signature_from_counts

        mixed_eval, _ = resolve_mixed_development_strategy(
            skeleton, agg, height, rm.max_fsi, agg.storey_height_used_m or storey_m, top_k=None
        )
        if mixed_eval is not None:
            ms = mixed_eval.strategy
            row["mixed_mix"] = _mix_signature_from_counts(ms.mix)
            n_types = sum(1 for c in ms.mix.values() if c > 0)
            row["mixed_is_mixed"] = "Y" if n_types > 1 else "N"
            row["mixed_diversity_score"] = round(ms.mix_diversity_score, 4)
            row["mixed_fsi_usage_pct"] = round(ms.fsi_utilization * 100.0, 2)
            row["mixed_units_per_floor"] = sum(ms.mix.values())
            row["mixed_total_units"] = ms.total_units

    return row


class Command(BaseCommand):
    help = "Run simulation pipeline on all plots for a TP; output CSV with all parameters per plot."

    def add_arguments(self, parser):
        parser.add_argument("--tp", type=int, required=True, help="TP scheme number (e.g. 14)")
        parser.add_argument("--height", type=float, default=16.5, help="Building height (m)")
        parser.add_argument("--road-width", type=float, default=12.0, help="Road width (m)")
        parser.add_argument("--zone", type=str, default="R1", help="Zone code")
        parser.add_argument("--authority", type=str, default="SUDA", help="Authority")
        parser.add_argument("--storey-height", type=float, default=None, help="Storey height (m); default 3.0")
        parser.add_argument("--output", type=str, default="tp_simulation_results.csv", help="Output CSV path")
        parser.add_argument("--limit", type=int, default=None, help="Max number of plots (default: all)")
        parser.add_argument(
            "--benchmark-set",
            type=str,
            default="",
            help="Optional CSV path with `fp_number` column to run a fixed benchmark subset.",
        )
        parser.add_argument(
            "--fidelity-profile",
            type=str,
            default="",
            help=f"Fidelity profile id (supported: {FIDELITY_PROFILE_TP14_V1}).",
        )
        parser.add_argument(
            "--strict-missing-road-width",
            action="store_true",
            dest="strict_missing_road_width",
            help="When fidelity profile is active, skip plots missing Plot.road_width_m.",
        )
        parser.add_argument(
            "--maximize-fsi",
            action="store_true",
            dest="maximize_fsi",
            help="Use development optimizer to report maximum compliant FSI per plot (ignores fixed-height scoring intent).",
        )
        parser.add_argument(
            "--mixed-strategy",
            action="store_true",
            dest="mixed_strategy",
            help="Run Phase 1 mixed unit strategy and output mixed analysis summary.",
        )

    def handle(self, *args, **options):
        tp = options["tp"]
        height = options["height"]
        road_width = options["road_width"]
        out_path = options["output"]
        limit = options["limit"]
        benchmark_set = (options.get("benchmark_set") or "").strip()
        fidelity_profile = (options.get("fidelity_profile") or "").strip()
        strict_missing_road_width = bool(options.get("strict_missing_road_width"))
        maximize_fsi = bool(options.get("maximize_fsi"))
        storey_height = options.get("storey_height")
        mixed_strategy = options.get("mixed_strategy", False)

        plots = list(Plot.objects.filter(tp_scheme=f"TP{tp}").order_by("fp_number"))
        if benchmark_set:
            wanted = _load_benchmark_fp_numbers(benchmark_set)
            plots = [p for p in plots if str(p.fp_number) in wanted]
        plots = sorted(plots, key=lambda p: _fp_sort_key(p.fp_number))
        if limit is not None:
            plots = plots[:limit]

        if not plots:
            raise CommandError(f"No plots found for TP{tp}")

        profile_msg = f", profile={fidelity_profile}" if fidelity_profile else ""
        self.stdout.write(
            f"Running simulation on {len(plots)} plots (TP{tp}, H={height}m, road={road_width}m{profile_msg})..."
        )

        columns = [
            "fp_number", "plot_area_sqft", "plot_area_sqm", "shape_class", "frontage_m", "depth_m",
            "height_band", "envelope_status", "placement_status", "core_status", "skeleton_status",
            "skeleton_valid", "compliance_status", "fsi_achieved", "fsi_max", "gc_achieved_pct",
            "gc_permissible_pct", "cop_provided_sqft", "cop_required_sqft", "cop_pct",
            "storey_height_used_m", "num_floors_estimated", "footprint_width_m", "footprint_depth_m",
            "efficiency_pct", "core_failed", "fallback_road_used", "error",
            "strategy_unit_type", "strategy_units_per_floor", "strategy_floors", "strategy_total_units",
            "strategy_fsi_usage_pct", "strategy_efficiency_pct",
            "mixed_mix", "mixed_is_mixed", "mixed_diversity_score", "mixed_fsi_usage_pct",
            "mixed_units_per_floor", "mixed_total_units",
            "fidelity_profile_id", "road_width_source", "road_edge_source", "fidelity_flag",
            "road_edge_count", "governing_road_edge_count", "governing_road_edges",
            "corridor_eligible", "corridor_distance_m", "fsi_zone", "fsi_authority",
            "counted_bua_sqft", "premium_additional_fsi_used",
            "compliance_pass",
        ]

        rows = []
        for i, plot in enumerate(plots):
            row = _run_one_plot(
                plot,
                height,
                road_width,
                storey_height,
                mixed_strategy,
                fidelity_profile=fidelity_profile,
                strict_missing_road_width=strict_missing_road_width,
                maximize_fsi=maximize_fsi,
            )
            rows.append(row)
            if (i + 1) % 20 == 0:
                self.stdout.write(f"  Processed {i + 1}/{len(plots)}...")

        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

        success = sum(1 for r in rows if r.get("compliance_status") == "COMPLIANT")
        envelope_fail = sum(1 for r in rows if r.get("envelope_status") and r["envelope_status"] != "VALID")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out_path} ({len(rows)} rows). Success (compliant): {success}, Envelope failed: {envelope_fail}"))

        if mixed_strategy:
            _print_mixed_analysis_summary(self.stdout, self.style, rows)
