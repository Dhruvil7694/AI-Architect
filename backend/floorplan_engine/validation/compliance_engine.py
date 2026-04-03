"""
floorplan_engine/validation/compliance_engine.py
------------------------------------------------
Full circulation compliance validation.

R2-4: Travel distance via 2 m interval centerline sampling.
R2-6: Dead-end detection via graph degree-1 nodes.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, MultiLineString, Point

from floorplan_engine.config import POINT_CORE, CoreConfig
from floorplan_engine.models import (
    CirculationGraph,
    CorridorResult,
    NODE_CORRIDOR_END,
    NODE_STAIR,
    StairResult,
)


def validate_circulation(
    core_type: str,
    stairs: StairResult,
    corridor: CorridorResult,
    graph: CirculationGraph,
    footprint_length_m: float,
    footprint_width_m: float,
    config: CoreConfig,
) -> dict[str, Any]:
    """
    Run all compliance checks and return a dict of results.

    Returns
    -------
    dict with keys:
        corridor_width_ok, travel_distance_ok, travel_distance_max_m,
        dead_end_ok, dead_end_max_m, dead_end_count,
        stair_separation_ok, stair_separation_m, stair_separation_required_m,
        violations (list[str]), warnings (list[str])
    """
    violations: list[str] = []
    warnings: list[str] = []

    # ── Corridor width ───────────────────────────────────────────────────
    corridor_width_ok = corridor.corridor_width_m >= config.corridor_width - 1e-6
    if not corridor_width_ok:
        violations.append(
            f"Corridor width {corridor.corridor_width_m:.2f}m "
            f"< required {config.corridor_width}m"
        )

    # ── Travel distance (R2-4: centerline sampling) ──────────────────────
    travel_max = _compute_max_travel_distance(
        corridor.centerline, stairs.stair_centroids_m, config,
    )
    travel_ok = travel_max <= config.max_travel_dist_m + 1e-6
    if not travel_ok:
        violations.append(
            f"Max travel distance {travel_max:.1f}m "
            f"> limit {config.max_travel_dist_m}m"
        )

    # ── Dead-end detection (R2-6: graph-based) ───────────────────────────
    dead_end_max, dead_end_count = _compute_dead_ends(graph, stairs, corridor)
    dead_end_ok = dead_end_max <= config.max_dead_end_m + 1e-6
    if not dead_end_ok:
        violations.append(
            f"Dead-end length {dead_end_max:.1f}m "
            f"> limit {config.max_dead_end_m}m"
        )

    # ── Stair separation ─────────────────────────────────────────────────
    diagonal = math.hypot(footprint_length_m, footprint_width_m)
    required_sep = diagonal * config.stair_sep_ratio
    sep_ok = stairs.separation_ok
    if not sep_ok:
        msg = (
            f"Stair separation {stairs.separation_m:.1f}m "
            f"< required {required_sep:.1f}m (1/3 diagonal)"
        )
        if core_type == POINT_CORE:
            warnings.append(msg + " [POINT_CORE — warning only]")
            sep_ok = True  # downgrade to warning for point towers
        else:
            violations.append(msg)

    return {
        "corridor_width_ok": corridor_width_ok,
        "travel_distance_ok": travel_ok,
        "travel_distance_max_m": round(travel_max, 2),
        "dead_end_ok": dead_end_ok,
        "dead_end_max_m": round(dead_end_max, 2),
        "dead_end_count": dead_end_count,
        "stair_separation_ok": sep_ok,
        "stair_separation_m": round(stairs.separation_m, 2),
        "stair_separation_required_m": round(required_sep, 2),
        "violations": violations,
        "warnings": warnings,
    }


# ── Travel distance (R2-4) ──────────────────────────────────────────────────

def _compute_max_travel_distance(
    centerline: LineString | MultiLineString | None,
    stair_centroids: list[tuple[float, float]],
    config: CoreConfig,
) -> float:
    """
    Sample the corridor centerline every ``travel_sample_interval_m`` and
    compute the maximum path distance from any sample point to the nearest
    staircase.
    """
    if centerline is None or not stair_centroids:
        return 0.0

    lines = (
        list(centerline.geoms) if isinstance(centerline, MultiLineString)
        else [centerline]
    )

    max_travel = 0.0
    interval = config.travel_sample_interval_m

    for line in lines:
        total_len = line.length
        if total_len < 1e-6:
            continue
        n_samples = max(2, int(total_len / interval))

        for i in range(n_samples + 1):
            frac = i / n_samples
            sample_pt = line.interpolate(frac, normalized=True)
            sample_proj = line.project(sample_pt)

            # Path distance to nearest stair
            min_dist = float("inf")
            for sc in stair_centroids:
                stair_proj = line.project(Point(sc))
                dist = abs(sample_proj - stair_proj)
                if dist < min_dist:
                    min_dist = dist

            if min_dist < float("inf"):
                max_travel = max(max_travel, min_dist)

    return max_travel


# ── Dead-end detection (R2-6) ────────────────────────────────────────────────

def _compute_dead_ends(
    graph: CirculationGraph,
    stairs: StairResult,
    corridor: CorridorResult,
) -> tuple[float, int]:
    """
    Dead-end = corridor endpoint (degree-1 node) that is not directly
    at a staircase.  Returns (max_dead_end_length, count).
    """
    stair_ids = {f"stair_{i}" for i in range(stairs.n_stairs)}
    dead_end_lengths: list[float] = []

    for node in graph.dead_end_nodes():
        if node.node_type != NODE_CORRIDOR_END:
            continue

        # Find the distance from this endpoint to the nearest stair
        # via graph edges
        min_dist = float("inf")
        for edge in graph.edges_from(node.node_id):
            other = edge.to_id if edge.from_id == node.node_id else edge.from_id
            # Check if `other` is a stair or connects to one
            if other in stair_ids:
                min_dist = min(min_dist, edge.distance_m)
            else:
                # One hop through corridor to stair
                for e2 in graph.edges_from(other):
                    o2 = e2.to_id if e2.from_id == other else e2.from_id
                    if o2 in stair_ids:
                        min_dist = min(min_dist, edge.distance_m + e2.distance_m)

        if min_dist < float("inf"):
            dead_end_lengths.append(min_dist)

    max_de = max(dead_end_lengths) if dead_end_lengths else 0.0
    return max_de, len(dead_end_lengths)
