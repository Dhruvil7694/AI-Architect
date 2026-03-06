"""
presentation_engine/door_placer.py
------------------------------------
Places symbolic door overlays (LINE + ARC) on shared wall boundaries.

Doors are symbolic only — no boolean cuts to wall polylines.
If any exception occurs the composer catches it and sets doors=[].

Door symbol components (per door)
----------------------------------
    LINE : door leaf from jamb_point in direction perpendicular to wall,
           length = door_width_m (0.9 m default).
    ARC  : swing arc from open position back to wall face,
           radius = door_width_m, span = 90°.

Placement logic
---------------
For each pair of (source_zone, unit_zone) that share an edge:
    1. Find the shared boundary LineString.
    2. Check segment length >= 1.1 × door_width_m.
    3. Place jamb at segment midpoint.
    4. Determine swing direction from the unit zone centroid.
    5. Build DoorSymbol.

Fallback:
    If any individual door fails (degenerate geometry, very short wall) it is
    silently skipped.  The function never raises; any top-level exception is
    caught by drawing_composer.

Public API
----------
    place(skeleton, rooms) -> list[DoorSymbol]
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from shapely.geometry import Polygon, LineString

from floor_skeleton.models import FloorSkeleton
from presentation_engine.models import DoorSymbol, RoomGeometry

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

DOOR_WIDTH_M:    float = 0.9
_MIN_WALL_RATIO: float = 1.1    # shared segment must be >= 1.1 × door width
_ARC_SPAN:       float = 90.0   # degrees — standard door swing


# ── Public function ────────────────────────────────────────────────────────────

def place(skeleton: FloorSkeleton, rooms: list[RoomGeometry]) -> list[DoorSymbol]:
    """
    Build door symbols for *skeleton* given the room geometry.

    Doors are placed at the midpoint of shared wall segments between:
    - core / corridor and each room
    - partition between TOILET and ROOM (within the same zone)

    Returns a (possibly empty) list of DoorSymbol.
    """
    doors: list[DoorSymbol] = []

    # Source zones that face unit zones across a shared wall
    source_polys: list[Polygon] = [skeleton.core_polygon]
    if skeleton.corridor_polygon is not None:
        source_polys.append(skeleton.corridor_polygon)

    # For each source zone, find rooms adjacent to it
    for src_poly in source_polys:
        for room in rooms:
            door = _try_make_door(src_poly, room.polygon)
            if door is not None:
                doors.append(door)

    # Intra-unit doors: between TOILET and adjacent ROOM
    toilet_rooms  = [r for r in rooms if r.label == "TOILET"]
    bedroom_rooms = [r for r in rooms if r.label == "ROOM"]

    for toilet in toilet_rooms:
        for bedroom in bedroom_rooms:
            door = _try_make_door(toilet.polygon, bedroom.polygon)
            if door is not None:
                doors.append(door)
                break  # max one toilet door per toilet zone

    return doors


# ── Internal helpers ──────────────────────────────────────────────────────────

def _try_make_door(
    source_poly: Polygon,
    room_poly: Polygon,
) -> Optional[DoorSymbol]:
    """
    Attempt to create a door symbol on the shared boundary between two polygons.
    Returns None (silently) if unsuccessful.
    """
    try:
        shared = source_poly.boundary.intersection(room_poly.boundary)
        if shared.is_empty:
            return None

        # Extract the longest LineString from the intersection
        seg = _longest_linestring(shared)
        if seg is None:
            return None

        seg_len = seg.length
        if seg_len < _MIN_WALL_RATIO * DOOR_WIDTH_M:
            return None  # wall too short for a door

        # Jamb at midpoint of segment
        jamb = seg.interpolate(0.5, normalized=True)
        jx, jy = jamb.x, jamb.y

        # Determine which side the room is on (for swing direction)
        room_cx, room_cy = room_poly.centroid.x, room_poly.centroid.y
        # Vector from jamb to room centroid
        dx = room_cx - jx
        dy = room_cy - jy
        angle_to_room = math.degrees(math.atan2(dy, dx))

        # Door leaf direction: perpendicular to wall, pointing into room
        # The wall direction is along the shared segment
        coords = list(seg.coords)
        wx = coords[-1][0] - coords[0][0]
        wy = coords[-1][1] - coords[0][1]
        wall_angle = math.degrees(math.atan2(wy, wx))

        # Two perpendicular options (+90° and −90° from wall)
        perp_a = wall_angle + 90.0
        perp_b = wall_angle - 90.0

        # Choose perpendicular pointing into room
        def _angular_diff(a: float, b: float) -> float:
            diff = abs(a - b) % 360
            return diff if diff <= 180 else 360 - diff

        if _angular_diff(perp_a, angle_to_room) <= _angular_diff(perp_b, angle_to_room):
            leaf_dir = perp_a
        else:
            leaf_dir = perp_b

        leaf_dir = leaf_dir % 360.0

        # ARC: from the closed position (leaf along wall) to open position
        # closed position = leaf_dir + 90° (or − 90°), swings 90° to open
        # Convention: arc goes from closed_angle to open_angle (= leaf_dir)
        closed_dir = (leaf_dir + 90.0) % 360.0
        # Ensure arc span is exactly 90° and > 0°
        arc_start = min(closed_dir, leaf_dir) % 360.0
        arc_end   = max(closed_dir, leaf_dir) % 360.0
        if abs(arc_end - arc_start) < 5.0:
            return None  # degenerate arc — skip

        return DoorSymbol(
            jamb_point=(round(jx, 6), round(jy, 6)),
            direction_deg=round(leaf_dir, 2),
            arc_start_deg=round(arc_start, 2),
            arc_end_deg=round(arc_end, 2),
            width_m=DOOR_WIDTH_M,
        )

    except Exception as exc:
        logger.debug("Door placement failed: %s", exc)
        return None


def _longest_linestring(geom) -> Optional[LineString]:
    """Extract the longest LineString from any geometry."""
    if geom.geom_type == "LineString":
        return geom if geom.length > 0 else None
    if geom.geom_type in ("MultiLineString", "GeometryCollection"):
        candidates = [
            g for g in geom.geoms
            if g.geom_type == "LineString" and g.length > 0
        ]
        return max(candidates, key=lambda g: g.length) if candidates else None
    return None
