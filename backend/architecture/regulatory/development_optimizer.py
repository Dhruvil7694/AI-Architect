from __future__ import annotations

"""
architecture.regulatory.development_optimizer
---------------------------------------------

Deterministic multi-tower development optimiser that maximises achieved FSI
under:
  - GDCR regulatory ceilings (height, FSI, GC)
  - Envelope feasibility
  - Placement constraints (multi-tower footprints)
  - Layout viability for each tower (skeleton + floor layout)

This module:
  - Does NOT modify any geometry engines or the existing height solver.
  - Reuses the same regulatory accessors and metrics used elsewhere.
  - Treats envelope/placement/skeleton/layout/rules as black-box engines.
"""

from dataclasses import dataclass
from math import floor
from typing import List, Optional, Tuple

from tp_ingestion.models import Plot

from envelope_engine.services.envelope_service import compute_envelope
from placement_engine.services.placement_service import compute_placement

from architecture.feasibility.regulatory_metrics import build_regulatory_metrics
from architecture.regulatory_accessors import (
    get_max_permissible_height_by_road_width,
    get_max_fsi,
    get_max_ground_coverage_pct,
)
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta

from rules_engine.services.evaluator import build_inputs_from_dict, evaluate_all
from rules_engine.rules.base import FAIL

from floor_skeleton.services import generate_floor_skeleton
from floor_skeleton.models import NO_SKELETON_PATTERN
from residential_layout import build_floor_layout

from architecture.regulatory.height_solver import (
    _spacing_provided_m_from_audit,
    _side_rear_margins_from_audit,
)


@dataclass
class OptimalDevelopmentSolution:
    n_towers: int
    floors: int
    height_m: float
    achieved_fsi: float
    fsi_utilization_pct: float
    total_bua_sqft: float
    per_tower_footprint_sqft: List[float]
    gc_utilization_pct: float
    controlling_constraint: str
    cop_strategy: str = "edge"
    cop_area_sqft: float = 0.0


def _infeasible_solution() -> OptimalDevelopmentSolution:
    return OptimalDevelopmentSolution(
        n_towers=0,
        floors=0,
        height_m=0.0,
        achieved_fsi=0.0,
        fsi_utilization_pct=0.0,
        total_bua_sqft=0.0,
        per_tower_footprint_sqft=[],
        gc_utilization_pct=0.0,
        controlling_constraint="INFEASIBLE",
    )


def evaluate_development_configuration(
    plot: Plot,
    storey_height_m: float = 3.0,
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
    *,
    mode: str = "strict",
    debug: bool = False,
) -> OptimalDevelopmentSolution:
    """
    Evaluate multiple COP placement strategies and return the best configuration.

    Strategies are evaluated in deterministic order ["edge", "center"] and the
    configuration with the highest achieved FSI is selected. Ties are resolved
    in favour of EDGE to preserve backwards-compatible behaviour.
    """
    strategies = ["edge", "center"]
    best_solution: Optional[OptimalDevelopmentSolution] = None
    fsi_tol = 1e-6

    for strategy in strategies:
        if debug:
            print(f"[COP-STRATEGY] Evaluating COP strategy={strategy.upper()}")

        sol = solve_optimal_development_configuration(
            plot=plot,
            storey_height_m=storey_height_m,
            min_width_m=min_width_m,
            min_depth_m=min_depth_m,
            mode=mode,
            debug=debug,
            cop_strategy=strategy,
        )

        if debug:
            print(
                "[COP-STRATEGY] Result strategy=%s, status=%s, achieved_fsi=%.3f, cop_area_sqft=%.1f"
                % (
                    strategy.upper(),
                    sol.controlling_constraint,
                    sol.achieved_fsi,
                    getattr(sol, "cop_area_sqft", 0.0),
                )
            )

        # Consider only feasible configurations with positive FSI.
        if sol.n_towers <= 0 or sol.floors <= 0 or sol.achieved_fsi <= 0.0:
            continue

        if best_solution is None or sol.achieved_fsi > best_solution.achieved_fsi + fsi_tol:
            best_solution = sol

    if best_solution is None:
        # All strategies infeasible: fall back to the baseline EDGE-only result
        # to preserve prior semantics for callers.
        fallback = solve_optimal_development_configuration(
            plot=plot,
            storey_height_m=storey_height_m,
            min_width_m=min_width_m,
            min_depth_m=min_depth_m,
            mode=mode,
            debug=debug,
            cop_strategy="edge",
        )
        if debug:
            print(
                "[COP-STRATEGY] All strategies infeasible; falling back to EDGE with achieved_fsi=%.3f"
                % fallback.achieved_fsi
            )
        return fallback

    if debug:
        print(
            "[COP-STRATEGY] Selected COP strategy=%s with achieved_fsi=%.3f"
            % (best_solution.cop_strategy.upper(), best_solution.achieved_fsi)
        )
    return best_solution


def _build_multi_tower_regulatory_ctx(
    plot: Plot,
    height_m: float,
    floors: int,
    env,
    placement,
) -> Tuple[bool, Optional[dict]]:
    """
    Build a regulatory context for a multi-tower placement at a given height.

    Uses the same regulatory_metrics helper as the single-tower solver, but
    aggregates footprint and coverage across all towers.
    """
    plot_area_sqft = float(plot.plot_area_sqft or 0.0)
    if plot_area_sqft <= 0.0:
        return False, None

    footprints = getattr(placement, "footprints", None) or []
    if not footprints:
        return False, None

    total_footprint_sqft = sum(float(fp.area_sqft or 0.0) for fp in footprints)
    if total_footprint_sqft <= 0.0:
        return False, None

    achieved_gc_pct = 100.0 * total_footprint_sqft / plot_area_sqft

    spacing_required_m = getattr(placement, "spacing_required_m", 0.0) or 0.0
    spacing_provided_m = _spacing_provided_m_from_audit(placement)

    cop_provided_sqft = env.common_plot_area_sqft or 0.0
    total_bua_sqft = total_footprint_sqft * floors

    regulatory = build_regulatory_metrics(
        plot_area_sqft=plot_area_sqft,
        total_bua_sqft=total_bua_sqft,
        achieved_gc_pct=achieved_gc_pct,
        cop_provided_sqft=cop_provided_sqft,
        spacing_required_m=spacing_required_m,
        spacing_provided_m=spacing_provided_m,
    )

    ctx = {
        "height_m": height_m,
        "floors": floors,
        "total_footprint_area_sqft": total_footprint_sqft,
        "regulatory": regulatory,
        "envelope": env,
        "placement": placement,
        "spacing_required_m": spacing_required_m,
        "spacing_provided_m": spacing_provided_m,
    }
    return True, ctx


def _is_compliant_via_rules_multi(
    plot: Plot,
    ctx: dict,
    *,
    debug: bool = False,
    mode: str = "strict",
) -> bool:
    """
    Multi-tower variant of rules compliance: aggregate BUA and coverage.
    """
    pm = plot
    env = ctx["envelope"]
    placement = ctx["placement"]

    plot_area_sqft = pm.plot_area_sqft
    height_m = ctx["height_m"]
    floors = ctx["floors"]
    total_footprint_sqft = ctx["total_footprint_area_sqft"]
    total_bua_sqft = total_footprint_sqft * floors
    road_width = float(getattr(pm, "road_width_m", 0.0) or 0.0)

    # Ground coverage: sum of tower footprints.
    ground_coverage_sqft = total_footprint_sqft

    # Side/rear margins from envelope audit (same as single-tower helper).
    side_m, rear_m = _side_rear_margins_from_audit(env.edge_margin_audit or [])

    # Road-side margin from envelope audit (first ROAD edge).
    road_margin_m = None
    for e in env.edge_margin_audit or []:
        if e.get("edge_type") == "ROAD":
            m = e.get("margin_m")
            if m is not None:
                road_margin_m = float(m)
                break

    # has_lift: any tower core that requires a lift.
    per_tower_cv = getattr(placement, "per_tower_core_validation", None) or []
    has_lift = any(getattr(cv, "lift_required", False) for cv in per_tower_cv)

    rule_params = {
        "road_width": road_width,
        "building_height": height_m,
        "total_bua": total_bua_sqft,
        "num_floors": floors,
        "ground_coverage": ground_coverage_sqft,
        "has_basement": False,
        "is_sprinklered": False,
        "has_lift": has_lift,
    }
    if side_m is not None:
        rule_params["side_margin"] = side_m
    if rear_m is not None:
        rule_params["rear_margin"] = rear_m
    if road_margin_m is not None:
        rule_params["road_margin"] = road_margin_m

    inputs = build_inputs_from_dict(plot_area_sqft, rule_params)
    results = evaluate_all(inputs)

    # Compute blocking rules depending on optimisation mode.
    if mode == "development":
        blocking = [
            r
            for r in results
            if r.status == FAIL and not (r.rule_id == "gdcr.fsi.base")
        ]
    else:
        blocking = [r for r in results if r.status == FAIL]

    if debug:
        # Log full metrics + failing rules for inspection.
        print("[METRICS-DEBUG]", inputs)
        for r in results:
            if r.status == FAIL:
                print(f"[RULE-DEBUG] rule_id={r.rule_id}")
                print(f"  category={r.category}")
                print(f"  status={r.status}")
                print(f"  required_value={r.required_value}")
                print(f"  actual_value={r.actual_value}")
                print(f"  unit={r.unit}")
                print(f"  note={r.note}")
        if blocking:
            print(
                "[BLOCKING-RULES]",
                [r.rule_id for r in blocking],
            )

    return not blocking


def _is_layout_viable_for_tower(
    height_m: float,
    placement,
    storey_height_m: float,
    tower_index: int,
) -> bool:
    """
    Check that a single tower (by index) has at least one viable floor layout.

    This mirrors the single-tower _is_layout_viable logic but targets a specific
    footprint/core_validation pair.
    """
    footprints = getattr(placement, "footprints", None) or []
    per_tower_cv = getattr(placement, "per_tower_core_validation", None) or []

    if tower_index >= len(footprints) or tower_index >= len(per_tower_cv):
        return False

    footprint = footprints[tower_index]
    core_validation = per_tower_cv[tower_index]

    try:
        skeleton = generate_floor_skeleton(
            footprint=footprint,
            core_validation=core_validation,
        )
    except Exception:
        return False

    if (
        skeleton.pattern_used == NO_SKELETON_PATTERN
        or not skeleton.is_geometry_valid
        or not skeleton.passes_min_unit_guard
        or not skeleton.is_architecturally_viable
    ):
        return False

    try:
        floor_layout = build_floor_layout(
            skeleton,
            floor_id="L0",
            module_width_m=None,
        )
    except Exception:
        return False

    return (
        floor_layout.total_units > 0
        and floor_layout.efficiency_ratio_floor > 0
    )


def solve_optimal_development_configuration(
    plot: Plot,
    storey_height_m: float = 3.0,
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
    *,
    mode: str = "strict",
    debug: bool = False,
    cop_strategy: str = "edge",
) -> OptimalDevelopmentSolution:
    """
    Multi-tower optimiser: find (floors, height, n_towers) that maximises achieved
    FSI while remaining:
      - GDCR-compliant (rules engine)
      - Envelope-feasible
      - Placement-feasible (n_towers)
      - Layout-viable for every tower.
    """
    if storey_height_m <= 0:
        raise ValueError("storey_height_m must be positive.")

    cop_strategy_normalized = (cop_strategy or "edge").lower()
    if cop_strategy_normalized not in {"edge", "center"}:
        cop_strategy_normalized = "edge"

    road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    if road_width <= 0.0:
        return _infeasible_solution()

    # Step 1 — regulatory height ceiling (road-width cap only; no layout reduction).
    h_road_cap = get_max_permissible_height_by_road_width(road_width)
    if not (h_road_cap > 0.0):
        return _infeasible_solution()

    max_floors = floor(h_road_cap / storey_height_m)
    if max_floors <= 0:
        return _infeasible_solution()

    # Step 2 — regulatory limits for FSI/GC (used only for FSI ceiling and
    # reporting; GC enforcement is delegated to the rules engine to avoid
    # double-filtering).
    # default_max_fsi retained for backwards-compatible reporting; dynamic
    # caps are computed per-plot/floors loop via get_dynamic_max_fsi().
    default_max_fsi = get_max_fsi()
    max_gc_pct = get_max_ground_coverage_pct()

    best_solution: Optional[OptimalDevelopmentSolution] = None
    best_fsi: float = -1.0
    fsi_tol = 1e-6

    # Outer loop: floors (descending).
    for floors in range(max_floors, 0, -1):
        height_m = floors * storey_height_m

        # Dynamic max FSI cap for this plot under current road width.
        max_fsi = default_max_fsi
        try:
            from architecture.regulatory_accessors import get_dynamic_max_fsi

            max_fsi = get_dynamic_max_fsi(
                float(getattr(plot, "plot_area_sqft", plot.area_geometry)),
                road_width,
            )
        except Exception:
            # Fall back to legacy global cap if dynamic accessor fails.
            max_fsi = default_max_fsi

        if debug:
            print(f"[DEV-DEBUG] Candidate floors={floors}, height_m={height_m:.3f}")

        # Envelope for this height (once).
        plot_geom = plot.geom
        road_edges, _ = detect_road_edges_with_meta(plot_geom, None)

        env = compute_envelope(
            plot_wkt=plot_geom.wkt,
            building_height=height_m,
            road_width=road_width,
            road_facing_edges=road_edges,
            enforce_gc=True,
            cop_strategy=cop_strategy_normalized,
        )
        if env.status != "VALID" or env.envelope_polygon is None:
            if debug:
                print(
                    f"  -> Envelope: FAIL (status={env.status}, "
                    f"message={getattr(env, 'error_message', '')})"
                )
            continue

        if debug:
            print(
                f"  -> Envelope: PASS (area_sqft={env.envelope_area_sqft}, "
                f"gc_pct={env.ground_coverage_pct})"
            )

        envelope_wkt = env.envelope_polygon.wkt

        # Dynamically detect max feasible towers at this height.
        hard_limit = 20
        max_feasible_towers = 0
        placements_by_n: dict[int, object] = {}

        for n in range(1, hard_limit + 1):
            placement = compute_placement(
                envelope_wkt=envelope_wkt,
                building_height_m=height_m,
                n_towers=n,
                min_width_m=min_width_m,
                min_depth_m=min_depth_m,
            )
            if placement.status != "VALID":
                if debug:
                    print(
                        f"  n_towers={n}: Placement: FAIL "
                        f"(status={placement.status}, "
                        f"error={getattr(placement, 'error_message', '')})"
                    )
                break
            max_feasible_towers = n
            placements_by_n[n] = placement

        if max_feasible_towers == 0:
            if debug:
                print("  -> No VALID placement for any n_towers at this height.")
            continue

        # Inner loop: tower count.
        for n_towers in range(1, max_feasible_towers + 1):
            placement = placements_by_n[n_towers]

            feasible, ctx = _build_multi_tower_regulatory_ctx(
                plot=plot,
                height_m=height_m,
                floors=floors,
                env=env,
                placement=placement,
            )
            if not feasible or not ctx:
                if debug:
                    print(
                        f"  n_towers={n_towers}: Regulatory context: FAIL "
                        "(insufficient footprint / plot metrics)"
                    )
                continue

            rules_ok = _is_compliant_via_rules_multi(
                plot,
                ctx,
                debug=debug and floors in (5, 6, 7) and n_towers == 1,
                mode=mode,
            )
            if not rules_ok:
                if debug:
                    print(f"  n_towers={n_towers}: Rules engine: FAIL")
                continue

            # Layout viability per tower.
            placement_obj = ctx["placement"]
            layout_ok = True
            for i in range(n_towers):
                if not _is_layout_viable_for_tower(
                    height_m=height_m,
                    placement=placement_obj,
                    storey_height_m=storey_height_m,
                    tower_index=i,
                ):
                    layout_ok = False
                    break

            if not layout_ok:
                if debug:
                    print(f"  n_towers={n_towers}: Layout: FAIL")
                continue

            regulatory = ctx["regulatory"]
            achieved_fsi = float(regulatory.achieved_fsi)
            fsi_utilization_pct = float(regulatory.fsi_utilization_pct)
            gc_utilization_pct = float(regulatory.achieved_gc_pct)

            total_bua_sqft = achieved_fsi * float(plot.plot_area_sqft)
            per_tower_footprint_sqft = [
                float(fp.area_sqft or 0.0) for fp in placement_obj.footprints
            ]

            env_obj = ctx["envelope"]
            cop_area_sqft = float(
                getattr(env_obj, "common_plot_area_sqft", None) or 0.0
            )
            cop_strategy_value = getattr(
                env_obj, "cop_strategy", cop_strategy_normalized
            )

            # Update best solution (FSI primary, floors as implicit tie-break).
            if achieved_fsi > best_fsi + fsi_tol:
                best_fsi = achieved_fsi
                best_solution = OptimalDevelopmentSolution(
                    n_towers=n_towers,
                    floors=floors,
                    height_m=height_m,
                    achieved_fsi=achieved_fsi,
                    fsi_utilization_pct=fsi_utilization_pct,
                    total_bua_sqft=total_bua_sqft,
                    per_tower_footprint_sqft=per_tower_footprint_sqft,
                    gc_utilization_pct=gc_utilization_pct,
                    controlling_constraint="",  # set after loop
                    cop_strategy=cop_strategy_value,
                    cop_area_sqft=cop_area_sqft,
                )

            if debug:
                print(
                    f"  n_towers={n_towers}: Envelope=PASS, Placement=PASS, "
                    f"Rules=PASS, Layout=PASS, achieved_fsi={achieved_fsi:.3f}"
                )

            # Early exit if FSI effectively maxed for this configuration.
            if achieved_fsi >= max_fsi - fsi_tol:
                if debug:
                    print(
                        "  -> FSI effectively at max_fsi; "
                        "stopping inner tower loop for this height."
                    )
                break

        if (
            best_solution is not None
            and best_solution.achieved_fsi >= max_fsi - fsi_tol
        ):
            if debug:
                print(
                    "[DEV-DEBUG] Achieved FSI is at max_fsi; "
                    "stopping outer floors loop."
                )
            break

    if best_solution is None:
        return _infeasible_solution()

    # Controlling constraint attribution for the chosen configuration.
    #
    # Precedence is:
    #   1. FSI_MAXED       — achieved FSI is effectively at the GDCR maximum.
    #   2. ROAD_WIDTH_CAP  — height is at (or within tolerance of) the road-width cap.
    #   3. GEOMETRY_LIMIT  — everything else (spacing, GC, envelope, packing, layout).
    if best_solution.achieved_fsi >= max_fsi - fsi_tol:
        controlling = "FSI_MAXED"
    elif abs(best_solution.height_m - h_road_cap) <= 0.05:
        controlling = "ROAD_WIDTH_CAP"
    else:
        controlling = "GEOMETRY_LIMIT"

    best_solution.controlling_constraint = controlling
    return best_solution

