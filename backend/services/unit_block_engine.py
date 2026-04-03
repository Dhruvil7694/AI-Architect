"""
Deterministic unit-block placement engine.

Generates rectangular unit envelopes (no internal room geometry) around a core.
"""

from __future__ import annotations

from typing import Any, Dict, List

CORRIDOR_W = 1.50


def generate_unit_blocks(
    floor_width: float,
    floor_depth: float,
    core: Dict[str, Any],
    units_per_core: int,
) -> Dict[str, Any]:
    """
    Create north/south unit blocks around a central corridor and core.

    Input:
      - floor_width, floor_depth
      - core rectangle (x, y, w, h)
      - units_per_core total unit count for the floor

    Output:
      {
        "corridor": {"x","y","w","h"},
        "units": [
          {"id","side","x","y","w","h"},
          ...
        ]
      }
    """
    if floor_width <= 0 or floor_depth <= 0:
        raise ValueError("floor dimensions must be positive")
    if units_per_core <= 0:
        raise ValueError("units_per_core must be positive")

    core_x = float(core["x"])
    core_w = float(core["w"])

    corridor_y = round((floor_depth - CORRIDOR_W) / 2.0, 2)
    south_y = 0.0
    north_y = round(corridor_y + CORRIDOR_W, 2)
    south_h = round(corridor_y, 2)
    north_h = round(floor_depth - north_y, 2)
    if south_h <= 0 or north_h <= 0:
        raise ValueError("insufficient depth for south/north bands")

    corridor = {
        "x": 0.0,
        "y": corridor_y,
        "w": round(floor_width, 2),
        "h": CORRIDOR_W,
    }

    n_south = max(units_per_core // 2, 1)
    n_north = max(units_per_core - n_south, 1)

    south_units = _build_band_units(
        side="south",
        count=n_south,
        y=south_y,
        h=south_h,
        floor_width=floor_width,
        core_x=core_x,
        core_w=core_w,
        start_idx=1,
    )
    north_units = _build_band_units(
        side="north",
        count=n_north,
        y=north_y,
        h=north_h,
        floor_width=floor_width,
        core_x=core_x,
        core_w=core_w,
        start_idx=len(south_units) + 1,
    )

    units = south_units + north_units
    _assert_units_non_overlapping(units)
    core_rect = _as_rect(core)
    for unit in units:
        if _overlap(unit, corridor):
            raise ValueError("unit overlaps corridor")
        if _overlap(unit, core_rect):
            raise ValueError("unit overlaps core")

    return {
        "corridor": corridor,
        "units": units,
    }


def _build_band_units(
    side: str,
    count: int,
    y: float,
    h: float,
    floor_width: float,
    core_x: float,
    core_w: float,
    start_idx: int,
) -> List[Dict[str, Any]]:
    left_w = max(core_x, 0.0)
    right_x = core_x + core_w
    right_w = max(floor_width - right_x, 0.0)
    total_avail = left_w + right_w
    if total_avail <= 0:
        raise ValueError("no width available for units outside core")

    n_left = int(round(count * left_w / total_avail))
    n_left = min(max(n_left, 0), count)
    n_right = count - n_left

    if left_w > 0 and n_left == 0 and count > 0:
        n_left, n_right = 1, count - 1
    if right_w > 0 and n_right == 0 and count > 0:
        n_right, n_left = 1, count - 1

    units: List[Dict[str, Any]] = []
    idx = start_idx

    if n_left > 0:
        left_unit_w = left_w / n_left
        cursor_x = 0.0
        for _ in range(n_left):
            units.append(_unit(idx, side, cursor_x, y, left_unit_w, h))
            cursor_x += left_unit_w
            idx += 1

    if n_right > 0:
        right_unit_w = right_w / n_right
        cursor_x = right_x
        for _ in range(n_right):
            units.append(_unit(idx, side, cursor_x, y, right_unit_w, h))
            cursor_x += right_unit_w
            idx += 1

    return units


def _unit(i: int, side: str, x: float, y: float, w: float, h: float) -> Dict[str, Any]:
    return {
        "id": f"U{i}",
        "side": side,
        "x": round(x, 2),
        "y": round(y, 2),
        "w": round(w, 2),
        "h": round(h, 2),
    }


def _as_rect(rect_like: Dict[str, Any]) -> Dict[str, float]:
    return {
        "x": float(rect_like["x"]),
        "y": float(rect_like["y"]),
        "w": float(rect_like["w"]),
        "h": float(rect_like["h"]),
    }


def _assert_units_non_overlapping(units: List[Dict[str, Any]]) -> None:
    for i, a in enumerate(units):
        for b in units[i + 1 :]:
            if _overlap(a, b):
                raise ValueError("overlap detected in unit-block layout")


def _overlap(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return not (
        float(a["x"]) + float(a["w"]) <= float(b["x"])
        or float(b["x"]) + float(b["w"]) <= float(a["x"])
        or float(a["y"]) + float(a["h"]) <= float(b["y"])
        or float(b["y"]) + float(b["h"]) <= float(a["y"])
    )
