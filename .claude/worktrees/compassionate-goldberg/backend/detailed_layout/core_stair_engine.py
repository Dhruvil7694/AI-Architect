"""
detailed_layout/core_stair_engine.py — core/stair detailing.

Uses the deterministic partition rules from the Phase D plan to place a
stair rectangle and lift shaft inside the core polygon.
"""

from __future__ import annotations

from typing import List

from shapely.geometry import Polygon, box

from detailed_layout.models import DetailedCore, DetailedStair
from residential_layout.floor_aggregation import FloorLayoutContract


def build_core_for_floor(floor: FloorLayoutContract) -> tuple[List[DetailedCore], List[DetailedStair]]:
    cores: List[DetailedCore] = []
    stairs: List[DetailedStair] = []

    core_poly = floor.core_polygon
    if core_poly is None or core_poly.is_empty:
        return cores, stairs

    minx, miny, maxx, maxy = core_poly.bounds
    W = maxx - minx
    D = maxy - miny
    if W <= 0 or D <= 0:
        return cores, stairs

    # Deterministic partition: stair takes 60% along longest dimension
    if W >= D:
        stair_box = box(minx, miny, minx + 0.6 * W, maxy)
        lift_box = box(maxx - 0.3 * W, miny, maxx, miny + 0.4 * D)
    else:
        stair_box = box(minx, miny, maxx, miny + 0.6 * D)
        lift_box = box(maxx - 0.3 * W, maxy - 0.4 * D, maxx, maxy)

    stair = DetailedStair(outline=stair_box)
    core = DetailedCore(outline=core_poly, hatch=lift_box)
    cores.append(core)
    stairs.append(stair)
    return cores, stairs

