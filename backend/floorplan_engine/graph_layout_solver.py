"""
graph_layout_solver.py
----------------------
Embed the topology graph into 2-D space using force-directed layout,
then apply architectural position hints and scale to real-world metres.

Strategy
--------
1.  Spring layout (Fruchterman–Reingold) gives a topologically faithful
    initial embedding — rooms that are adjacent cluster together.

2.  Architectural anchoring overrides abstract positions with domain rules:
    - entry    → south-center (flat entrance)
    - balcony* → north or south exterior edge
    - passage  → midpoint of its two heaviest neighbours
    - kitchen  → near dining or living but pushed east/west
    - bathrooms→ interior (no exterior needed)

3.  Scale from normalised [-1, 1] to [0, unit_w] × [0, unit_d] in metres,
    preserving the relative topology cluster structure.

Returns
-------
Dict[room_id, (x_m, y_m)]  — centre positions in metres, origin = SW corner.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Dict, Optional, Tuple

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

# Positional anchors expressed as fractional position in [0,1]×[0,1]
# (normalised flat space; 0,0 = SW corner; 1,1 = NE corner)
_POSITION_HINTS: Dict[str, Tuple[float, float]] = {
    "entry":          (0.50, 0.02),   # south centre (flat front door)
    "living":         (0.40, 0.35),   # south-west quadrant (natural living zone)
    "dining":         (0.60, 0.35),   # adjacent to kitchen, near living
    "kitchen":        (0.80, 0.30),   # east wall, near service
    "utility":        (0.90, 0.20),   # far east, service zone
    "bedroom_master": (0.25, 0.80),   # north-west, quiet zone
    "bedroom_2":      (0.65, 0.80),   # north-east
    "bedroom_3":      (0.80, 0.80),   # far north-east
    "bathroom_master": (0.10, 0.80),  # attached to master, interior
    "bathroom_attached": (0.10, 0.70),
    "bathroom_common": (0.50, 0.75),  # near passage
    "passage":         (0.50, 0.60),  # transition zone between public/private
    "balcony":         (0.25, 0.98),  # north face (or south — will be overridden)
    "balcony_living":  (0.35, 0.02),  # south face off living
    "balcony_master":  (0.20, 0.98),  # north face off master
}

# Room types that must stay near exterior walls
_EXTERIOR_ROOMS = {"living", "kitchen", "bedroom", "balcony"}


def solve_layout(
    G: nx.Graph,
    unit_w: float = 10.0,
    unit_d: float = 7.0,
    seed: int = 42,
    spring_k: float = 2.0,
    spring_iters: int = 300,
) -> Dict[str, Tuple[float, float]]:
    """
    Run force-directed layout + architectural anchoring.

    Parameters
    ----------
    G        : annotated topology graph from topology_generator
    unit_w   : flat width  (metres, L-axis / east-west)
    unit_d   : flat depth  (metres, S-axis / north-south)
    seed     : RNG seed for reproducible layouts
    spring_k : optimal edge length parameter for spring_layout
    spring_iters : Fruchterman–Reingold iterations

    Returns
    -------
    positions : dict mapping room_id → (x_m, y_m) centre in metres
    """
    # ── 1. Build initial fixed-position hints for anchored nodes ──────────────
    fixed_pos: Dict[str, Tuple[float, float]] = {}
    for nid in G.nodes:
        if nid in _POSITION_HINTS:
            fx, fy = _POSITION_HINTS[nid]
            fixed_pos[nid] = (fx * 2 - 1, fy * 2 - 1)   # map [0,1]→[-1,1]

    # ── 2. Force-directed layout ──────────────────────────────────────────────
    # Seed positions: blend hints + random to avoid degenerate starts
    rng = np.random.default_rng(seed)
    init_pos: Dict[str, np.ndarray] = {}
    for nid in G.nodes:
        if nid in fixed_pos:
            hx, hy = fixed_pos[nid]
            init_pos[nid] = np.array([hx, hy]) + rng.normal(0, 0.05, 2)
        else:
            init_pos[nid] = rng.uniform(-0.9, 0.9, 2)

    # Weight edges by room importance (heavier = closer in layout)
    for u, v, d in G.edges(data=True):
        # Passage–room edges should be SHORT (passage is a hub)
        u_type = G.nodes[u].get("room_type", "")
        v_type = G.nodes[v].get("room_type", "")
        if "passage" in (u_type, v_type):
            d["weight"] = 3.0
        elif u_type == "bathroom" or v_type == "bathroom":
            d["weight"] = 2.0
        else:
            d["weight"] = 1.0

    pos = nx.spring_layout(
        G,
        pos=init_pos,
        fixed=None,            # let all nodes move (hints are only soft)
        k=spring_k,
        iterations=spring_iters,
        weight="weight",
        seed=seed,
    )

    # ── 3. Architectural overrides (hard anchors) ─────────────────────────────
    # Entry always at south centre
    if "entry" in pos:
        pos["entry"] = np.array([0.0, -0.85])

    # Balconies at extreme north or south
    for nid, data in G.nodes(data=True):
        if data.get("room_type") == "balcony":
            cur = pos[nid]
            # Push to whichever face is nearer
            if cur[1] < 0:
                pos[nid] = np.array([cur[0], -0.90])
            else:
                pos[nid] = np.array([cur[0], 0.90])

    # Passage → midpoint of its neighbours (weighted by degree)
    passage_nodes = [n for n in G.nodes if G.nodes[n].get("room_type") == "passage"]
    for pn in passage_nodes:
        nbrs = list(G.neighbors(pn))
        if nbrs:
            nbr_pos = np.mean([pos[nb] for nb in nbrs], axis=0)
            pos[pn] = nbr_pos * 0.9   # pull slightly toward centre

    # ── 4. Scale from normalised [-1,1]² → metres ────────────────────────────
    # Find actual min/max of positions after spring layout
    xs = np.array([p[0] for p in pos.values()])
    ys = np.array([p[1] for p in pos.values()])
    x_range = xs.max() - xs.min() if xs.max() != xs.min() else 1.0
    y_range = ys.max() - ys.min() if ys.max() != ys.min() else 1.0

    # Normalise to [0.1, 0.9] of unit dims, then scale to metres
    margin_x = unit_w * 0.10
    margin_y = unit_d * 0.10
    usable_w  = unit_w - 2 * margin_x
    usable_d  = unit_d - 2 * margin_y

    positions_m: Dict[str, Tuple[float, float]] = {}
    for nid, p in pos.items():
        nx_norm = (p[0] - xs.min()) / x_range       # → [0, 1]
        ny_norm = (p[1] - ys.min()) / y_range        # → [0, 1]
        xm = margin_x + nx_norm * usable_w
        ym = margin_y + ny_norm * usable_d
        # Clamp to unit bounds with small inset
        xm = max(0.1, min(unit_w - 0.1, xm))
        ym = max(0.1, min(unit_d - 0.1, ym))
        positions_m[nid] = (round(xm, 3), round(ym, 3))

    logger.info(
        "solve_layout: %d rooms embedded in %.1f×%.1f m",
        len(positions_m), unit_w, unit_d,
    )
    return positions_m


def topology_clusters(G: nx.Graph) -> Dict[str, int]:
    """
    Return community cluster ids per node (Louvain via greedy modularity).
    Useful for colour-coding rooms in the renderer.
    """
    communities = nx.community.greedy_modularity_communities(G)
    cluster_map: Dict[str, int] = {}
    for cid, members in enumerate(communities):
        for m in members:
            cluster_map[m] = cid
    return cluster_map
