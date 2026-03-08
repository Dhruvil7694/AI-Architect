"""
room_geometry_solver.py
-----------------------
Convert graph-node centre positions into axis-aligned rectangles that satisfy:

  - Target area  (from node spec)
  - Min clear width / depth  (GDCR §13.1.9)
  - Max aspect ratio
  - Passage fixed-width constraint (1.1 m)
  - Snap to 0.1 m grid
  - Clamped inside the unit bounding box

Each rectangle is a plain dict:
  { "x": float, "y": float, "w": float, "h": float }
  x, y = bottom-left corner in metres (origin = SW corner of flat)
  w    = width  (east-west)
  h    = height (north-south / depth)

The solver does NOT resolve overlaps — that is left to layout_optimizer.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Optional, Tuple

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

GRID = 0.10   # snap grid (metres)


# ─── Rect helpers ──────────────────────────────────────────────────────────────

def _snap(v: float) -> float:
    """Snap a value to the nearest GRID increment."""
    return round(round(v / GRID) * GRID, 4)


def _make_rect(cx: float, cy: float, w: float, h: float,
               unit_w: float, unit_d: float) -> Dict[str, float]:
    """
    Build a rect from centre (cx, cy) and dimensions (w, h),
    snapping to grid and clamping inside [0, unit_w] × [0, unit_d].
    """
    w = _snap(max(w, GRID))
    h = _snap(max(h, GRID))
    x = _snap(cx - w / 2)
    y = _snap(cy - h / 2)
    # Clamp
    x = max(0.0, min(unit_w - w, x))
    y = max(0.0, min(unit_d - h, y))
    return {"x": x, "y": y, "w": w, "h": h}


def _aspect_correct(w: float, h: float, area: float,
                    aspect_max: float) -> Tuple[float, float]:
    """
    Adjust (w, h) so aspect_ratio ≤ aspect_max while preserving area.
    Returns (new_w, new_h).
    """
    if w < h:
        w, h = h, w   # ensure w ≥ h initially

    ratio = w / h if h > 0 else aspect_max + 1
    if ratio > aspect_max:
        # Fix by equalising toward square
        h = math.sqrt(area / aspect_max)
        w = area / h
    return w, h


def _initial_dims(area: float, min_w: float, min_d: float,
                  aspect_max: float,
                  fixed_w: Optional[float] = None) -> Tuple[float, float]:
    """
    Compute initial (width, height) for a room rectangle.

    Strategy:
      1. If fixed_w is set (passage) → w = fixed_w, h = area / w
      2. Otherwise start from square root of area, apply aspect + min constraints
    """
    if fixed_w is not None:
        w = max(fixed_w, min_w)
        h = area / w
        h = max(h, min_d)
        return _snap(w), _snap(h)

    # Start square-ish
    w = math.sqrt(area)
    h = area / w

    # Enforce min dimensions
    if w < min_w:
        w = min_w
        h = area / w
    if h < min_d:
        h = min_d
        w = area / h

    # Enforce aspect
    w, h = _aspect_correct(w, h, area, aspect_max)

    # Re-enforce mins after aspect correction
    if w < min_w:
        w = min_w
        h = area / w
    if h < min_d:
        h = min_d
        w = area / h

    return _snap(w), _snap(h)


# ─── Main solver ───────────────────────────────────────────────────────────────

def build_rectangles(
    G: nx.Graph,
    positions: Dict[str, Tuple[float, float]],
    unit_w: float,
    unit_d: float,
) -> Dict[str, Dict[str, float]]:
    """
    Convert centre positions (from graph_layout_solver) into room rectangles.

    Parameters
    ----------
    G          : annotated topology graph
    positions  : room_id → (x_centre_m, y_centre_m)
    unit_w     : flat outer width  (m)
    unit_d     : flat outer depth  (m)

    Returns
    -------
    rects : dict  room_id → { x, y, w, h }  (bottom-left corner + dims)
    """
    rects: Dict[str, Dict[str, float]] = {}

    for nid, data in G.nodes(data=True):
        if nid not in positions:
            logger.warning("room %s has no position — skipped", nid)
            continue

        cx, cy = positions[nid]
        area       = float(data.get("area",       6.0))
        min_w      = float(data.get("min_w",      1.2))
        min_d      = float(data.get("min_d",      1.2))
        aspect_max = float(data.get("aspect_max", 2.5))
        fixed_w    = data.get("fixed_w")
        room_type  = data.get("room_type", "room")

        # Passage: orient so the long axis connects its neighbours
        if room_type == "passage" and fixed_w is not None:
            nbrs = [n for n in G.neighbors(nid) if n in positions]
            if len(nbrs) >= 2:
                # Direction vector between outermost neighbours
                p0 = np.array(positions[nbrs[0]])
                p1 = np.array(positions[nbrs[-1]])
                dx, dy = p1 - p0
                length = max(math.hypot(dx, dy), min_d)
                if abs(dx) >= abs(dy):
                    # Mostly horizontal passage
                    w = _snap(length)
                    h = _snap(max(fixed_w, min_d))
                else:
                    # Mostly vertical passage
                    w = _snap(max(fixed_w, min_w))
                    h = _snap(length)
                rects[nid] = _make_rect(cx, cy, w, h, unit_w, unit_d)
                continue

        w, h = _initial_dims(area, min_w, min_d, aspect_max, fixed_w)

        # Balconies: always wider than deep (they hang off the facade)
        if room_type == "balcony" and w < h:
            w, h = h, w
            # Re-check min depth
            h = max(h, min_d)
            w = area / h

        rects[nid] = _make_rect(cx, cy, w, h, unit_w, unit_d)

    logger.info("build_rectangles: %d rects generated", len(rects))
    return rects


# ─── Shared-edge query helpers ─────────────────────────────────────────────────

def shared_edge_length(r1: Dict, r2: Dict) -> float:
    """
    Length of the shared edge between two axis-aligned rectangles.
    Returns 0 if they do not share an edge (with 5 cm tolerance).
    """
    tol = 0.05
    # Horizontal shared edge?
    if abs((r1["y"] + r1["h"]) - r2["y"]) < tol or abs((r2["y"] + r2["h"]) - r1["y"]) < tol:
        ox = min(r1["x"] + r1["w"], r2["x"] + r2["w"]) - max(r1["x"], r2["x"])
        return max(0.0, ox)
    # Vertical shared edge?
    if abs((r1["x"] + r1["w"]) - r2["x"]) < tol or abs((r2["x"] + r2["w"]) - r1["x"]) < tol:
        oy = min(r1["y"] + r1["h"], r2["y"] + r2["h"]) - max(r1["y"], r2["y"])
        return max(0.0, oy)
    return 0.0


def overlap_area(r1: Dict, r2: Dict) -> float:
    """Return the overlapping area between two rects (0 if no overlap)."""
    ox = min(r1["x"] + r1["w"], r2["x"] + r2["w"]) - max(r1["x"], r2["x"])
    oy = min(r1["y"] + r1["h"], r2["y"] + r2["h"]) - max(r1["y"], r2["y"])
    if ox > 0 and oy > 0:
        return ox * oy
    return 0.0


def is_exterior(rect: Dict, unit_w: float, unit_d: float, tol: float = 0.50) -> bool:
    """True if the rectangle touches any exterior wall of the flat."""
    return (
        rect["x"] <= tol
        or rect["y"] <= tol
        or rect["x"] + rect["w"] >= unit_w - tol
        or rect["y"] + rect["h"] >= unit_d - tol
    )
