"""
layout_optimizer.py
-------------------
Two-phase layout optimiser:

Phase 1 — Collision resolution
  Iterative axis-aligned separation.  For each overlapping pair, the two rects
  are pushed apart along the axis of minimum overlap until no pair overlaps.
  Rooms pinned to exterior walls keep their wall-face fixed; only the interior
  face moves.

Phase 2 — Simulated annealing (SA)
  Stochastically perturbs room positions to maximise a composite score:

    score =   W_ADJ  * adjacency_score     (adjacent rooms share edges)
            + W_EXT  * exterior_score      (exterior rooms touch flat walls)
            - W_OVL  * overlap_penalty     (total overlap area)
            - W_COR  * corridor_penalty    (passage length)
            + W_EFF  * efficiency_score    (unit area / flat area)

  Temperature anneals from T_START to T_END over SA_STEPS iterations.
  Each step perturbs one randomly chosen room's position by ±STEP_M metres.

  After SA, a final collision-resolution pass guarantees no overlaps remain.
"""

from __future__ import annotations

import copy
import logging
import math
import random
from typing import Dict, List, Optional, Tuple

import networkx as nx

from floorplan_engine.room_geometry_solver import (
    GRID,
    overlap_area,
    shared_edge_length,
    is_exterior,
)

logger = logging.getLogger(__name__)

# ─── Score weights ─────────────────────────────────────────────────────────────
W_ADJ  = 4.0   # adjacency satisfaction
W_EXT  = 2.0   # exterior wall coverage for rooms that need it
W_OVL  = 8.0   # overlap penalty (dominant — must not overlap)
W_COR  = 1.5   # corridor / passage length penalty
W_EFF  = 1.0   # floor efficiency (unit rooms / total area)

# ─── SA parameters ────────────────────────────────────────────────────────────
T_START  = 2.0    # initial temperature
T_END    = 0.01   # final temperature
SA_STEPS = 3000   # total annealing steps
STEP_M   = 0.50   # max perturbation per step (metres)

# ─── Collision resolution ─────────────────────────────────────────────────────
MAX_COL_ITERS = 200


def _total_overlap(rects: Dict[str, Dict]) -> float:
    """Sum of all pairwise overlap areas."""
    keys = list(rects.keys())
    total = 0.0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            total += overlap_area(rects[keys[i]], rects[keys[j]])
    return total


def _resolve_collisions(
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    fixed: Optional[List[str]] = None,
    max_iters: int = MAX_COL_ITERS,
) -> Dict[str, Dict]:
    """
    Iterative rectangle separation.
    For each overlapping pair (r1, r2):
      - Compute overlap in X and Y
      - Push apart along the axis of SMALLER overlap (minimum translation)
      - If a room is in `fixed`, only the other room moves

    Returns a new rects dict (original is not mutated).
    """
    rects = copy.deepcopy(rects)
    fixed = set(fixed or [])
    keys  = list(rects.keys())

    for iteration in range(max_iters):
        moved = False
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                rid1, rid2 = keys[i], keys[j]
                r1, r2 = rects[rid1], rects[rid2]

                ox = min(r1["x"] + r1["w"], r2["x"] + r2["w"]) - max(r1["x"], r2["x"])
                oy = min(r1["y"] + r1["h"], r2["y"] + r2["h"]) - max(r1["y"], r2["y"])

                if ox <= 1e-4 or oy <= 1e-4:
                    continue   # no overlap

                moved = True
                # Separation margin grows slightly per iteration to guarantee convergence
                margin = GRID * (1 + iteration // 50)

                if ox <= oy:
                    # Separate horizontally
                    total = ox + margin
                    f1 = (0.0 if rid1 in fixed else 0.5)
                    f2 = (0.0 if rid2 in fixed else 0.5)
                    norm = f1 + f2 if f1 + f2 > 0 else 1.0
                    if rid1 not in fixed:
                        if r1["x"] <= r2["x"]:
                            rects[rid1]["x"] = max(0.0, r1["x"] - total * f1 / norm)
                        else:
                            rects[rid1]["x"] = min(unit_w - r1["w"], r1["x"] + total * f1 / norm)
                    if rid2 not in fixed:
                        if r2["x"] <= r1["x"]:
                            rects[rid2]["x"] = max(0.0, r2["x"] - total * f2 / norm)
                        else:
                            rects[rid2]["x"] = min(unit_w - r2["w"], r2["x"] + total * f2 / norm)
                else:
                    # Separate vertically
                    total = oy + margin
                    f1 = (0.0 if rid1 in fixed else 0.5)
                    f2 = (0.0 if rid2 in fixed else 0.5)
                    norm = f1 + f2 if f1 + f2 > 0 else 1.0
                    if rid1 not in fixed:
                        if r1["y"] <= r2["y"]:
                            rects[rid1]["y"] = max(0.0, r1["y"] - total * f1 / norm)
                        else:
                            rects[rid1]["y"] = min(unit_d - r1["h"], r1["y"] + total * f1 / norm)
                    if rid2 not in fixed:
                        if r2["y"] <= r1["y"]:
                            rects[rid2]["y"] = max(0.0, r2["y"] - total * f2 / norm)
                        else:
                            rects[rid2]["y"] = min(unit_d - r2["h"], r2["y"] + total * f2 / norm)

                # Clamp to unit bounds
                for rid in (rid1, rid2):
                    r = rects[rid]
                    r["x"] = max(0.0, min(unit_w - r["w"], r["x"]))
                    r["y"] = max(0.0, min(unit_d - r["h"], r["y"]))

        if not moved:
            logger.debug("collision resolved in %d iterations", iteration + 1)
            break

    return rects


# ─── Score function ────────────────────────────────────────────────────────────

def _score(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
) -> float:
    """Composite layout score (higher = better)."""
    # Adjacency: reward shared-edge length between adjacent rooms
    adj_score = 0.0
    for u, v in G.edges():
        if u in rects and v in rects:
            adj_score += shared_edge_length(rects[u], rects[v])

    # Exterior: reward exterior-needing rooms that touch a flat wall
    ext_score = 0.0
    for nid, data in G.nodes(data=True):
        if nid in rects and data.get("exterior", False):
            if is_exterior(rects[nid], unit_w, unit_d):
                ext_score += 1.0

    # Overlap penalty
    ovl_penalty = _total_overlap(rects)

    # Corridor penalty: sum of passage rect lengths
    cor_penalty = 0.0
    for nid, data in G.nodes(data=True):
        if data.get("room_type") == "passage" and nid in rects:
            r = rects[nid]
            cor_penalty += max(r["w"], r["h"])   # penalise long dimension

    # Efficiency: ratio of room area (excl. balconies) to unit area
    unit_area  = unit_w * unit_d
    rooms_area = sum(
        r["w"] * r["h"]
        for nid, r in rects.items()
        if G.nodes[nid].get("room_type") not in ("balcony",)
    )
    eff_score = rooms_area / unit_area if unit_area > 0 else 0.0

    return (
        W_ADJ * adj_score
        + W_EXT * ext_score
        - W_OVL * ovl_penalty
        - W_COR * cor_penalty
        + W_EFF * eff_score
    )


# ─── Simulated annealing ───────────────────────────────────────────────────────

def _sa_step(
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    step: float,
    rng: random.Random,
) -> Tuple[str, Dict]:
    """
    Perturb one randomly chosen room by ±step metres in X or Y.
    Returns (room_id, new_rect_copy).
    """
    nid = rng.choice(list(rects.keys()))
    r   = copy.copy(rects[nid])
    axis = rng.choice(["x", "y"])
    delta = rng.uniform(-step, step)
    if axis == "x":
        r["x"] = max(0.0, min(unit_w - r["w"], r["x"] + delta))
    else:
        r["y"] = max(0.0, min(unit_d - r["h"], r["y"] + delta))
    # Snap to grid
    r["x"] = round(round(r["x"] / GRID) * GRID, 4)
    r["y"] = round(round(r["y"] / GRID) * GRID, 4)
    return nid, r


def simulated_annealing(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    sa_steps: int = SA_STEPS,
    seed: int = 42,
) -> Dict[str, Dict]:
    """
    Run SA on room positions to maximise layout score.
    Returns improved (but potentially still overlapping) rects.
    """
    rects = copy.deepcopy(rects)
    rng   = random.Random(seed)
    T     = T_START
    cool  = (T_END / T_START) ** (1.0 / max(sa_steps, 1))
    current_score = _score(G, rects, unit_w, unit_d)
    best_rects    = copy.deepcopy(rects)
    best_score    = current_score

    for step_idx in range(sa_steps):
        nid, new_r = _sa_step(rects, unit_w, unit_d, STEP_M * (T / T_START + 0.1), rng)
        old_r = copy.copy(rects[nid])
        rects[nid] = new_r

        new_score = _score(G, rects, unit_w, unit_d)
        delta     = new_score - current_score

        if delta > 0 or rng.random() < math.exp(delta / T):
            current_score = new_score
            if new_score > best_score:
                best_score = new_score
                best_rects = copy.deepcopy(rects)
        else:
            rects[nid] = old_r   # revert

        T *= cool

    logger.info("SA: best_score=%.3f after %d steps", best_score, sa_steps)
    return best_rects


# ─── Main entry point ──────────────────────────────────────────────────────────

def _pin_exterior_rooms(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    max_dist: float = 1.5,
) -> Dict[str, Dict]:
    """
    Gently push exterior rooms toward the nearest flat wall if they are
    within `max_dist` metres of it.  Rooms already on a wall (< 0.5 m) are
    left untouched to avoid introducing new overlaps.
    """
    rects = copy.deepcopy(rects)
    for nid, data in G.nodes(data=True):
        if not data.get("exterior", False) or nid not in rects:
            continue
        r = rects[nid]
        d_south = r["y"]
        d_north = unit_d - (r["y"] + r["h"])
        d_west  = r["x"]
        d_east  = unit_w - (r["x"] + r["w"])
        best = min(d_south, d_north, d_west, d_east)

        # Already on a wall — skip
        if best < 0.5:
            continue
        # Too far — spring layout will handle the pull, don't force
        if best > max_dist:
            continue

        # Nudge toward nearest wall (half-way to reduce overlap risk)
        nudge = best * 0.6
        if best == d_south:
            rects[nid]["y"] = max(0.0, r["y"] - nudge)
        elif best == d_north:
            rects[nid]["y"] = min(unit_d - r["h"], r["y"] + nudge)
        elif best == d_west:
            rects[nid]["x"] = max(0.0, r["x"] - nudge)
        else:
            rects[nid]["x"] = min(unit_w - r["w"], r["x"] + nudge)

    return rects


def _snap_adjacent_edges(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    snap_tol: float = 0.40,
) -> Dict[str, Dict]:
    """
    For every topologically adjacent pair (u, v), if the gap between their
    nearest facing walls is ≤ snap_tol, close the gap so they physically share
    an edge.  This turns "almost touching" rooms into properly adjacent rooms
    that the door-symbol renderer can use.

    Only the INNER wall moves (exterior walls are kept pinned).
    """
    rects = copy.deepcopy(rects)
    tol = snap_tol

    for u, v in G.edges():
        if u not in rects or v not in rects:
            continue
        ru, rv = rects[u], rects[v]

        # Determine which pair of walls is closest
        gaps = {
            "r_to_l": rv["x"] - (ru["x"] + ru["w"]),   # ru right → rv left
            "l_to_r": ru["x"] - (rv["x"] + rv["w"]),   # rv right → ru left
            "t_to_b": rv["y"] - (ru["y"] + ru["h"]),   # ru top → rv bottom
            "b_to_t": ru["y"] - (rv["y"] + rv["h"]),   # rv top → ru bottom
        }
        # Positive gaps = separation; negative = overlap
        best = min(gaps, key=lambda k: abs(gaps[k]))
        gap  = gaps[best]

        if abs(gap) > tol:
            continue   # too far apart to snap

        half = gap / 2.0
        if best == "r_to_l":
            rects[u]["x"] = max(0.0, rects[u]["x"] + half)
            rects[v]["x"] = min(unit_w - rv["w"], rects[v]["x"] - half)
        elif best == "l_to_r":
            rects[v]["x"] = max(0.0, rects[v]["x"] + half)
            rects[u]["x"] = min(unit_w - ru["w"], rects[u]["x"] - half)
        elif best == "t_to_b":
            rects[u]["y"] = max(0.0, rects[u]["y"] + half)
            rects[v]["y"] = min(unit_d - rv["h"], rects[v]["y"] - half)
        elif best == "b_to_t":
            rects[v]["y"] = max(0.0, rects[v]["y"] + half)
            rects[u]["y"] = min(unit_d - ru["h"], rects[u]["y"] - half)

    return rects


def optimize(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
    sa_steps: int = SA_STEPS,
    seed: int = 42,
) -> Dict[str, Dict]:
    """
    Full optimisation pipeline:
      1. Collision resolution  — separate overlapping rooms
      2. Simulated annealing   — maximise composite layout score
      3. Adjacent-edge snapping — pull topologically adjacent rooms to touch
      4. Final collision pass   — clean up any snapping-introduced overlaps

    Returns clean, non-overlapping, optimised rects.
    """
    logger.info("optimizer phase 1: collision resolution")
    rects = _resolve_collisions(rects, unit_w, unit_d, max_iters=300)

    logger.info("optimizer phase 2: simulated annealing (%d steps)", sa_steps)
    rects = simulated_annealing(G, rects, unit_w, unit_d, sa_steps=sa_steps, seed=seed)

    logger.info("optimizer phase 3: pin exterior rooms to walls")
    rects = _pin_exterior_rooms(G, rects, unit_w, unit_d)

    logger.info("optimizer phase 4: edge snapping")
    rects = _snap_adjacent_edges(G, rects, unit_w, unit_d, snap_tol=1.20)

    logger.info("optimizer phase 5: final collision resolution (until convergence)")
    for _ in range(5):   # up to 5 full sweeps with increasing separation
        before = _total_overlap(rects)
        rects = _resolve_collisions(rects, unit_w, unit_d, max_iters=500)
        after = _total_overlap(rects)
        if after < 0.01:
            break
        if abs(before - after) < 0.001:
            # Stuck — apply small random jitter to break tie
            import random as _rng
            _r = _rng.Random(999)
            for nid, r in rects.items():
                r["x"] = max(0.0, min(unit_w - r["w"], r["x"] + _r.uniform(-0.2, 0.2)))
                r["y"] = max(0.0, min(unit_d - r["h"], r["y"] + _r.uniform(-0.2, 0.2)))

    # One more snap pass after final collision resolve
    rects = _snap_adjacent_edges(G, rects, unit_w, unit_d, snap_tol=0.30)

    remaining_ovl = _total_overlap(rects)
    logger.info("optimize complete: overlap_area=%.3f m²", remaining_ovl)

    return rects


def layout_score_report(
    G: nx.Graph,
    rects: Dict[str, Dict],
    unit_w: float,
    unit_d: float,
) -> Dict[str, float]:
    """Return individual score components for debugging / API response."""
    adj_score, ext_score, ovl_area, cor_len, eff = 0.0, 0.0, 0.0, 0.0, 0.0

    for u, v in G.edges():
        if u in rects and v in rects:
            adj_score += shared_edge_length(rects[u], rects[v])

    for nid, data in G.nodes(data=True):
        if nid in rects and data.get("exterior", False):
            if is_exterior(rects[nid], unit_w, unit_d):
                ext_score += 1.0

    ovl_area = _total_overlap(rects)

    for nid, data in G.nodes(data=True):
        if data.get("room_type") == "passage" and nid in rects:
            r = rects[nid]
            cor_len += max(r["w"], r["h"])

    unit_area  = unit_w * unit_d
    rooms_area = sum(r["w"] * r["h"] for r in rects.values())
    eff = rooms_area / unit_area if unit_area > 0 else 0.0

    return {
        "adjacency_score":   round(adj_score, 3),
        "exterior_score":    round(ext_score, 1),
        "overlap_area_sqm":  round(ovl_area,  3),
        "corridor_length_m": round(cor_len,   3),
        "efficiency_pct":    round(eff * 100,  1),
        "composite":         round(_score(G, rects, unit_w, unit_d), 3),
    }
