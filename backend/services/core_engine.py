"""
Deterministic core placement engine.

This module builds a centered vertical core (stairs, lifts, lobby) without any LLM use.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Geometric constants (metres)
LIFT_SHAFT_W = 1.85
LIFT_SHAFT_D = 1.80
STAIR_W = 1.20
STAIR_D = 3.50
LOBBY_D = 2.00
WALL_T = 0.23


def build_core_layout(
    floor_width: float,
    floor_depth: float,
    n_lifts: int,
    n_stairs: int,
) -> Dict[str, Any]:
    """
    Build a centered core rectangle plus component rectangles.

    Input:
      - floor_width, floor_depth: floor-plate dimensions in metres
      - n_lifts, n_stairs: required vertical circulation counts

    Output:
      {
        "x", "y", "w", "h",
        "lifts": [{"x","y","w","h"}, ...],
        "stairs": [{"x","y","w","h"}, ...],
        "lobby": {"x","y","w","h"}
      }
    """
    if floor_width <= 0 or floor_depth <= 0:
        raise ValueError("floor dimensions must be positive")
    if n_lifts < 0 or n_stairs < 0:
        raise ValueError("lift/stair counts cannot be negative")
    if n_lifts == 0 and n_stairs == 0:
        raise ValueError("at least one lift or stair is required")

    service_depth = max(STAIR_D if n_stairs else 0.0, LIFT_SHAFT_D if n_lifts else 0.0)
    inter_group_gap = WALL_T if (n_lifts > 0 and n_stairs > 0) else 0.0
    internal_w = (n_stairs * STAIR_W) + (n_lifts * LIFT_SHAFT_W) + inter_group_gap
    core_w = round(internal_w + (2 * WALL_T), 2)
    core_h = round(service_depth + LOBBY_D + (2 * WALL_T), 2)

    if core_w > floor_width or core_h > floor_depth:
        raise ValueError("computed core does not fit inside floor plate")

    core_x = round((floor_width - core_w) / 2.0, 2)
    core_y = round((floor_depth - core_h) / 2.0, 2)
    service_y = core_y + WALL_T

    stairs: List[Dict[str, float]] = []
    lifts: List[Dict[str, float]] = []

    cursor_x = core_x + WALL_T
    for _ in range(n_stairs):
        stairs.append(
            _rect(
                x=cursor_x,
                y=service_y,
                w=STAIR_W,
                h=STAIR_D,
            )
        )
        cursor_x += STAIR_W

    if n_stairs > 0 and n_lifts > 0:
        cursor_x += inter_group_gap

    for _ in range(n_lifts):
        lift_y = service_y + (service_depth - LIFT_SHAFT_D) / 2.0
        lifts.append(
            _rect(
                x=cursor_x,
                y=lift_y,
                w=LIFT_SHAFT_W,
                h=LIFT_SHAFT_D,
            )
        )
        cursor_x += LIFT_SHAFT_W

    lobby = _rect(
        x=core_x + WALL_T,
        y=service_y + service_depth,
        w=internal_w,
        h=LOBBY_D,
    )

    _assert_no_overlaps(stairs + lifts + [lobby])

    return {
        "x": core_x,
        "y": core_y,
        "w": core_w,
        "h": core_h,
        "lifts": lifts,
        "stairs": stairs,
        "lobby": lobby,
    }


def _rect(x: float, y: float, w: float, h: float) -> Dict[str, float]:
    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "w": round(w, 2),
        "h": round(h, 2),
    }


def _assert_no_overlaps(rects: List[Dict[str, float]]) -> None:
    for i, a in enumerate(rects):
        for b in rects[i + 1 :]:
            if _overlap(a, b):
                raise ValueError("core components overlap; invalid deterministic layout")


def _overlap(a: Dict[str, float], b: Dict[str, float]) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"]
        or b["x"] + b["w"] <= a["x"]
        or a["y"] + a["h"] <= b["y"]
        or b["y"] + b["h"] <= a["y"]
    )
