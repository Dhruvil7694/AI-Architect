from __future__ import annotations

"""
architecture.regulatory.fsi_optimizer
-------------------------------------

Deterministic solver that maximises achieved FSI utilisation under:
  - Full GDCR compliance (via rules engine)
  - Envelope + placement feasibility
  - Layout viability (single-tower, Phase 4 floor layout)

This module:
  - Does NOT modify any geometry engines or the height solver.
  - Reuses height_solver helpers for feasibility and layout checks.
  - Pulls regulatory ceilings only via architecture.regulatory_accessors.
"""

from dataclasses import dataclass
from math import floor
from typing import Optional

from tp_ingestion.models import Plot

from architecture.regulatory_accessors import (
    get_max_permissible_height_by_road_width,
    get_max_fsi,
    get_max_ground_coverage_pct,
)
from architecture.regulatory.height_solver import (
    HeightSolution,
    solve_max_legal_height,
    _is_feasible_height,
    _is_compliant_via_rules,
    _is_layout_viable,
)


@dataclass
class OptimalFSISolution:
    optimal_height_m: float
    floors: int
    achieved_fsi: float
    fsi_utilization_pct: float
    total_bua_sqft: float
    footprint_area_sqft: float
    gc_utilization_pct: float
    controlling_constraint: str


def _infeasible_solution() -> OptimalFSISolution:
    return OptimalFSISolution(
        optimal_height_m=0.0,
        floors=0,
        achieved_fsi=0.0,
        fsi_utilization_pct=0.0,
        total_bua_sqft=0.0,
        footprint_area_sqft=0.0,
        gc_utilization_pct=0.0,
        controlling_constraint="INFEASIBLE",
    )


def solve_optimal_fsi_configuration(
    plot: Plot,
    storey_height_m: float = 3.0,
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
) -> OptimalFSISolution:
    """
    Find the configuration (height/floors) that maximises achieved FSI while
    remaining fully GDCR-compliant and layout-viable.

    Strategy:
      1. Use height_solver.solve_max_legal_height() to find the legal height ceiling.
      2. Iterate floors from that ceiling downward, at discrete floor heights.
      3. For each floor count:
           - Reuse _is_feasible_height (envelope + placement + metrics).
           - Reuse _is_compliant_via_rules (rules engine).
           - Reuse _is_layout_viable (skeleton + floor layout).
         Keep the configuration with the highest achieved_fsi.
      4. Stop early if FSI utilisation is ~100%.
    """
    if storey_height_m <= 0:
        raise ValueError("storey_height_m must be positive.")

    # Step 1 — legal height ceiling (already layout-aware)
    height_solution: HeightSolution = solve_max_legal_height(
        plot=plot,
        building_height_upper_bound=None,
        storey_height_m=storey_height_m,
        min_width_m=min_width_m,
        min_depth_m=min_depth_m,
    )
    max_legal_height = float(height_solution.max_height_m or 0.0)
    max_legal_floors = floor(max_legal_height / storey_height_m) if max_legal_height > 0.0 else 0

    if max_legal_floors <= 0:
        return _infeasible_solution()

    # Regulatory ceilings via accessors (passed through to _is_feasible_height)
    max_fsi = get_max_fsi()
    max_gc_pct = get_max_ground_coverage_pct()

    best_solution: Optional[OptimalFSISolution] = None
    best_fsi: float = -1.0
    # Single tolerance used for FSI comparisons and "maxed" checks to keep
    # regulatory math consistent.
    fsi_tol = 1e-6

    for floors in range(max_legal_floors, 0, -1):
        height_m = floors * storey_height_m

        feasible, ctx = _is_feasible_height(
            plot=plot,
            height_m=height_m,
            storey_height_m=storey_height_m,
            min_width_m=min_width_m,
            min_depth_m=min_depth_m,
            max_fsi=max_fsi,
            max_gc_pct=max_gc_pct,
        )
        if not feasible or not ctx:
            continue

        if not _is_compliant_via_rules(plot, ctx):
            continue

        if not _is_layout_viable(plot, height_m, ctx, storey_height_m):
            continue

        regulatory = ctx["regulatory"]
        achieved_fsi = float(regulatory.achieved_fsi)
        fsi_utilization_pct = float(regulatory.fsi_utilization_pct)
        footprint_area_sqft = float(ctx["footprint_area_sqft"])
        total_bua_sqft = achieved_fsi * float(plot.plot_area_sqft)
        gc_utilization_pct = float(regulatory.achieved_gc_pct)

        # Primary objective: maximise achieved FSI. On ties (within fsi_tol),
        # prefer configurations with more floors (taller building) to make the
        # tie-break explicit and deterministic.
        if achieved_fsi > best_fsi + fsi_tol:
            best_fsi = achieved_fsi
            best_solution = OptimalFSISolution(
                optimal_height_m=height_m,
                floors=floors,
                achieved_fsi=achieved_fsi,
                fsi_utilization_pct=fsi_utilization_pct,
                total_bua_sqft=total_bua_sqft,
                footprint_area_sqft=footprint_area_sqft,
                gc_utilization_pct=gc_utilization_pct,
                controlling_constraint="",  # filled in after the loop
            )
        elif (
            best_solution is not None
            and abs(achieved_fsi - best_fsi) <= fsi_tol
            and floors > best_solution.floors
        ):
            best_solution = OptimalFSISolution(
                optimal_height_m=height_m,
                floors=floors,
                achieved_fsi=achieved_fsi,
                fsi_utilization_pct=fsi_utilization_pct,
                total_bua_sqft=total_bua_sqft,
                footprint_area_sqft=footprint_area_sqft,
                gc_utilization_pct=gc_utilization_pct,
                controlling_constraint="",
            )

        # Early exit when achieved FSI is effectively at the GDCR maximum.
        if achieved_fsi >= max_fsi - fsi_tol:
            break

    if best_solution is None:
        return _infeasible_solution()

    # Controlling constraint attribution for the chosen configuration.
    road_width = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    h_road_cap = (
        get_max_permissible_height_by_road_width(road_width) if road_width > 0.0 else 0.0
    )

    # If achieved FSI is effectively at the GDCR maximum, classify as FSI_MAXED
    # even if the road cap is also binding; this makes the priority explicit.
    # Controlling constraint precedence:
    #   1. FSI_MAXED       — achieved FSI is effectively at the GDCR maximum.
    #   2. ROAD_WIDTH_CAP  — height is at (or within tolerance of) the road-width cap.
    #   3. GEOMETRY_LIMIT  — everything else (spacing, GC, envelope, packing, layout).
    if best_solution.achieved_fsi >= max_fsi - fsi_tol:
        controlling = "FSI_MAXED"
    elif abs(best_solution.optimal_height_m - h_road_cap) <= 0.05:
        controlling = "ROAD_WIDTH_CAP"
    else:
        controlling = "GEOMETRY_LIMIT"

    best_solution.controlling_constraint = controlling
    return best_solution

