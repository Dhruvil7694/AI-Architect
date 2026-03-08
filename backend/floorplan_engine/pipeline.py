"""
pipeline.py
-----------
End-to-end flat floor plan generator.

    Claude topology JSON
        → topology_generator.build_graph()
        → graph_layout_solver.solve_layout()
        → room_geometry_solver.build_rectangles()
        → layout_optimizer.optimize()
        → compliance_validator.validate()
        → renderer_svg.render_svg()
        → SVG string + structured result dict

Public API
----------
    generate_floorplan_svg(topology, unit_w, unit_d, flat_type, **kw)
    generate_floorplan(topology, unit_w, unit_d, flat_type, **kw)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

from floorplan_engine.topology_generator import build_graph, graph_summary
from floorplan_engine.graph_layout_solver import solve_layout
from floorplan_engine.room_geometry_solver import build_rectangles
from floorplan_engine.layout_optimizer import optimize, layout_score_report
from floorplan_engine.compliance_validator import validate
from floorplan_engine.renderer_svg import render_svg

logger = logging.getLogger(__name__)


def _auto_unit_dims(topology: Dict, flat_type: Optional[str]) -> tuple[float, float]:
    """
    Estimate unit outer dimensions from total room areas if not provided.
    Target: ~65% floor efficiency → footprint ≈ total_area / 0.65
    Aspect ratio ≈ 1.6 (typical residential plate)
    """
    rooms = topology.get("rooms", topology.get("nodes", []))
    total = 0.0
    for r in rooms:
        if isinstance(r, dict):
            total += float(r.get("area_sqm", 0) or r.get("area", 0))

    # Fallback to flat-type typical areas
    if total < 5:
        defaults = {"1BHK": 41, "2BHK": 58, "3BHK": 75}
        total = defaults.get(flat_type or "", 55)

    footprint = total / 0.65
    aspect    = 1.55   # width/depth
    unit_d    = math.sqrt(footprint / aspect)
    unit_w    = footprint / unit_d
    return round(unit_w, 1), round(unit_d, 1)


def generate_floorplan(
    topology: Dict[str, Any],
    unit_w: float = 0.0,
    unit_d: float = 0.0,
    flat_type: Optional[str] = None,
    sa_steps: int = 2500,
    seed: int = 42,
    room_overrides: Optional[Dict[str, Dict]] = None,
) -> Dict[str, Any]:
    """
    Full pipeline — returns structured result dict.

    Parameters
    ----------
    topology      : Claude topology JSON (rooms + adjacency_graph)
    unit_w        : flat outer width in metres   (0 → auto-estimated)
    unit_d        : flat outer depth in metres   (0 → auto-estimated)
    flat_type     : "1BHK" | "2BHK" | "3BHK"   (drives area defaults)
    sa_steps      : simulated annealing iterations
    seed          : RNG seed for reproducibility
    room_overrides: per-room spec overrides

    Returns
    -------
    {
      "svg":          str — complete SVG document,
      "rects":        dict — room_id → {x,y,w,h},
      "compliance":   dict — full compliance report,
      "score":        dict — score component breakdown,
      "unit_w":       float,
      "unit_d":       float,
      "flat_type":    str,
      "graph_summary":dict,
    }
    """
    flat_type = flat_type or topology.get("flat_type") or "2BHK"

    # Auto-size unit if dimensions not given
    if unit_w <= 0 or unit_d <= 0:
        unit_w, unit_d = _auto_unit_dims(topology, flat_type)
        logger.info("auto unit dims: %.1f m × %.1f m", unit_w, unit_d)

    # ── Step 1: Graph ─────────────────────────────────────────────────────────
    G = build_graph(topology, flat_type=flat_type,
                    unit_w=unit_w, unit_d=unit_d,
                    room_overrides=room_overrides)
    summary = graph_summary(G)

    # ── Step 2: Spring layout → 2D positions ──────────────────────────────────
    positions = solve_layout(G, unit_w=unit_w, unit_d=unit_d, seed=seed)

    # ── Step 3: Convert positions → rectangles ────────────────────────────────
    rects = build_rectangles(G, positions, unit_w, unit_d)

    # ── Step 4: Optimise (collision + SA) ─────────────────────────────────────
    rects = optimize(G, rects, unit_w, unit_d, sa_steps=sa_steps, seed=seed)

    # ── Step 5: Compliance ────────────────────────────────────────────────────
    compliance = validate(G, rects, unit_w, unit_d)

    # ── Step 6: Render SVG ────────────────────────────────────────────────────
    title = f"{flat_type} — Flat Floor Plan  ({unit_w:.1f} m × {unit_d:.1f} m)"
    svg   = render_svg(G, rects, unit_w, unit_d, compliance, title)

    # ── Score report ──────────────────────────────────────────────────────────
    score = layout_score_report(G, rects, unit_w, unit_d)

    return {
        "svg":          svg,
        "rects":        rects,
        "compliance":   compliance,
        "score":        score,
        "unit_w":       unit_w,
        "unit_d":       unit_d,
        "flat_type":    flat_type,
        "graph_summary": summary,
    }


def generate_floorplan_svg(
    topology: Dict[str, Any],
    unit_w: float = 0.0,
    unit_d: float = 0.0,
    flat_type: Optional[str] = None,
    **kwargs,
) -> str:
    """Convenience wrapper — returns only the SVG string."""
    return generate_floorplan(topology, unit_w, unit_d, flat_type, **kwargs)["svg"]
