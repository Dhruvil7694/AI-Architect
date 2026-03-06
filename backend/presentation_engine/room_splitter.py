"""
presentation_engine/room_splitter.py
--------------------------------------
Deterministic room splitting: maximum 1 split per UnitZone (TOILET + ROOM).

The decision is purely arithmetic — no recursion, no AI, no branching tree.

Splitting rule
--------------
    if zone_width_m < MIN_SPLIT_ZONE_WIDTH (4.8 m):
        → return unsplit [UNIT]
    else:
        → split into [TOILET strip (1.8 m wide) + ROOM strip (remainder)]

Toilet position:
    Always placed at the core-adjacent edge of the unit zone.
    - END_CORE_LEFT, CENTER_CORE  → toilet at min-x of zone
    - END_CORE_RIGHT               → toilet at max-x of zone
    - SINGLE_LOADED / DOUBLE_LOADED → toilet at min-x (deterministic default)

Fallback:
    If any split polygon is invalid or area < 0.1 m² → return unsplit [UNIT].

Public API
----------
    split(skeleton) -> list[RoomGeometry]
    split_fallback(skeleton) -> list[RoomGeometry]
"""

from __future__ import annotations

import logging

from shapely.geometry import box as shapely_box

from floor_skeleton.models import (
    FloorSkeleton,
    LABEL_END_CORE_RIGHT,
)
from presentation_engine.models import RoomGeometry

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

TOILET_WIDTH_M:      float = 1.8
TOILET_DEPTH_M:      float = 2.1   # not used for splitting depth — full zone
MIN_ROOM_WIDTH_M:    float = 3.0
MIN_SPLIT_ZONE_WIDTH: float = TOILET_WIDTH_M + MIN_ROOM_WIDTH_M   # 4.8 m
_MIN_ROOM_AREA:      float = 0.1   # m² — degenerate polygon guard


# ── Public functions ──────────────────────────────────────────────────────────

def split(skeleton: FloorSkeleton) -> list[RoomGeometry]:
    """
    Split each UnitZone into at most two rooms.

    Returns a flat list of RoomGeometry objects for all zones.
    """
    rooms: list[RoomGeometry] = []
    for uz in skeleton.unit_zones:
        rooms.extend(_split_zone(uz, skeleton.placement_label))
    return rooms


def split_fallback(skeleton: FloorSkeleton) -> list[RoomGeometry]:
    """
    Return each UnitZone as a single unsplit UNIT — no splitting attempted.
    """
    rooms: list[RoomGeometry] = []
    for uz in skeleton.unit_zones:
        rooms.append(RoomGeometry(
            polygon=uz.polygon,
            label="UNIT",
            area_sqm=round(uz.polygon.area, 4),
        ))
    return rooms


# ── Internal helpers ──────────────────────────────────────────────────────────

def _split_zone(uz, placement_label: str) -> list[RoomGeometry]:
    """
    Attempt to split a single UnitZone.

    Uses zone_width_m (explicit, pre-computed, safe) for the decision.
    The toilet strip is full zone depth for simplicity (schematic only).
    """
    zone_width = uz.zone_width_m

    if zone_width < MIN_SPLIT_ZONE_WIDTH:
        return [_as_unit(uz)]

    # Determine toilet placement side (core-adjacent edge)
    toilet_at_min_x = placement_label != LABEL_END_CORE_RIGHT

    minx, miny, maxx, maxy = uz.polygon.bounds

    if toilet_at_min_x:
        toilet_box = shapely_box(minx, miny, minx + TOILET_WIDTH_M, maxy)
        room_box   = shapely_box(minx + TOILET_WIDTH_M, miny, maxx, maxy)
    else:
        toilet_box = shapely_box(maxx - TOILET_WIDTH_M, miny, maxx, maxy)
        room_box   = shapely_box(minx, miny, maxx - TOILET_WIDTH_M, maxy)

    # Validate split polygons
    if (
        not toilet_box.is_valid or toilet_box.area < _MIN_ROOM_AREA
        or not room_box.is_valid or room_box.area < _MIN_ROOM_AREA
    ):
        logger.warning(
            "Room split produced invalid polygon (zone_width=%.2f m) — "
            "returning unsplit zone.", zone_width,
        )
        return [_as_unit(uz)]

    room_width = maxx - (minx + TOILET_WIDTH_M) if toilet_at_min_x else (
        maxx - TOILET_WIDTH_M - minx
    )
    if room_width < MIN_ROOM_WIDTH_M:
        logger.warning(
            "Room width after split (%.2f m) < MIN_ROOM_WIDTH_M (%.2f m) — "
            "returning unsplit zone.", room_width, MIN_ROOM_WIDTH_M,
        )
        return [_as_unit(uz)]

    return [
        RoomGeometry(polygon=toilet_box, label="TOILET",
                     area_sqm=round(toilet_box.area, 4)),
        RoomGeometry(polygon=room_box,   label="ROOM",
                     area_sqm=round(room_box.area, 4)),
    ]


def _as_unit(uz) -> RoomGeometry:
    """Return zone as a single unsplit UNIT."""
    return RoomGeometry(
        polygon=uz.polygon,
        label="UNIT",
        area_sqm=round(uz.polygon.area, 4),
    )
