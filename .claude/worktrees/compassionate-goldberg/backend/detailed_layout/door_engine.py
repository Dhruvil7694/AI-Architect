"""
detailed_layout/door_engine.py — deterministic door placement engine.

Implements the rule-based door system described in the Phase D plan:
- Entry door on living–corridor edge.
- Bedroom doors on bedroom–living shared walls.
- Toilet doors on toilet–bedroom or toilet–corridor shared walls.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon

from detailed_layout.config import DetailingConfig
from detailed_layout.models import DetailedDoor
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import RoomInstance, UnitLayoutContract


def _longest_shared_edge(a: Polygon, b: Polygon, tol: float) -> Optional[LineString]:
    """Return the longest shared boundary segment between two polygons."""
    inter = a.boundary.intersection(b.boundary)
    if inter.is_empty:
        return None
    candidates: List[LineString] = []
    if isinstance(inter, LineString):
        candidates.append(inter)
    else:
        for geom in getattr(inter, "geoms", []):
            if isinstance(geom, LineString) and geom.length > tol:
                candidates.append(geom)
    if not candidates:
        return None
    return max(candidates, key=lambda g: g.length)


def _compute_door_segment(
    wall_segment: LineString,
    width_m: float,
    min_clear_m: float,
) -> Optional[LineString]:
    """Return a centered door segment on wall_segment, or None if too short."""
    p0 = wall_segment.coords[0]
    p1 = wall_segment.coords[-1]
    vx = p1[0] - p0[0]
    vy = p1[1] - p0[1]
    L = (vx * vx + vy * vy) ** 0.5
    if L <= 0:
        return None
    if L < width_m + 2 * min_clear_m:
        return None
    ux, uy = vx / L, vy / L
    cx = (p0[0] + p1[0]) * 0.5
    cy = (p0[1] + p1[1]) * 0.5
    half = width_m / 2.0
    ax = cx - ux * half
    ay = cy - uy * half
    bx = cx + ux * half
    by = cy + uy * half
    return LineString([(ax, ay), (bx, by)])


def _make_swing_arc(opening: LineString, inward: bool = True) -> LineString:
    """
    Very simple swing arc approximation: quarter-circle based on door width.
    The exact shape is not semantically important for Phase D; determinism is.
    """
    coords = list(opening.coords)
    p0 = coords[0]
    p1 = coords[-1]
    vx = p1[0] - p0[0]
    vy = p1[1] - p0[1]
    L = (vx * vx + vy * vy) ** 0.5
    if L <= 0:
        return opening
    ux, uy = vx / L, vy / L
    # normal to the left (or right) of the door
    if inward:
        nx, ny = -uy, ux
    else:
        nx, ny = uy, -ux
    cx = (p0[0] + p1[0]) * 0.5
    cy = (p0[1] + p1[1]) * 0.5
    r = L  # exaggerate for clarity
    return LineString(
        [
            (cx, cy),
            (cx + nx * r * 0.5 + ux * r * 0.5, cy + ny * r * 0.5 + uy * r * 0.5),
            (cx + nx * r, cy + ny * r),
        ]
    )


def build_doors_for_floor(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
) -> Tuple[Dict[str, List[DetailedDoor]], Dict[str, Optional[DetailedDoor]]]:
    """
    Build DetailedDoor instances for all units/rooms on a floor.

    Returns:
      - doors_by_room: room_id -> list[DetailedDoor]
      - entry_by_unit: unit_id -> DetailedDoor or None
    """
    doors_by_room: Dict[str, List[DetailedDoor]] = {}
    entry_by_unit: Dict[str, Optional[DetailedDoor]] = {}

    width_cfg = config.door_widths_m
    clear_cfg = config.door_clearances_m
    min_clear = clear_cfg.get("from_corner_min", 0.2)
    tol = config.snap_tol_m

    for unit in units:
        unit_id = unit.unit_id or ""
        living: Optional[RoomInstance] = next(
            (r for r in unit.rooms if r.room_type == "LIVING"), None
        )
        rooms = list(unit.rooms)
        entry_by_unit[unit_id] = None

        # Entry door: living–corridor
        if living and floor.corridor_polygon is not None:
            shared = _longest_shared_edge(living.polygon, floor.corridor_polygon, tol)
            if shared:
                door_ls = _compute_door_segment(
                    shared, width_cfg.get("ENTRY", 1.0), min_clear
                )
                if door_ls:
                    swing = _make_swing_arc(door_ls, inward=False)
                    frame = door_ls.buffer(0.05, cap_style=2)
                    door = DetailedDoor(
                        opening_segment=door_ls,
                        frame_polygon=frame,  # type: ignore[arg-type]
                        swing_arc=swing,
                        door_type="ENTRY",
                    )
                    room_id = f"{unit_id}_{rooms.index(living)}"
                    doors_by_room.setdefault(room_id, []).append(door)
                    entry_by_unit[unit_id] = door

        # Bedroom and toilet doors
        for idx, room in enumerate(rooms):
            room_id = f"{unit_id}_{idx}"
            if room.room_type == "BEDROOM" and living:
                shared = _longest_shared_edge(room.polygon, living.polygon, tol)
                if shared:
                    door_ls = _compute_door_segment(
                        shared, width_cfg.get("BEDROOM", 0.9), min_clear
                    )
                    if door_ls:
                        swing = _make_swing_arc(door_ls, inward=True)
                        frame = door_ls.buffer(0.04, cap_style=2)
                        door = DetailedDoor(
                            opening_segment=door_ls,
                            frame_polygon=frame,  # type: ignore[arg-type]
                            swing_arc=swing,
                            door_type="BEDROOM",
                        )
                        doors_by_room.setdefault(room_id, []).append(door)

            if room.room_type == "TOILET":
                # Prefer toilet–bedroom; fall back to toilet–corridor
                target_seg: Optional[LineString] = None
                bedroom = next(
                    (r for r in rooms if r.room_type == "BEDROOM"), None
                )
                if bedroom:
                    target_seg = _longest_shared_edge(room.polygon, bedroom.polygon, tol)
                if target_seg is None and floor.corridor_polygon is not None:
                    target_seg = _longest_shared_edge(
                        room.polygon, floor.corridor_polygon, tol
                    )
                if target_seg:
                    door_ls = _compute_door_segment(
                        target_seg, width_cfg.get("TOILET", 0.75), min_clear
                    )
                    if door_ls:
                        swing = _make_swing_arc(door_ls, inward=True)
                        frame = door_ls.buffer(0.03, cap_style=2)
                        door = DetailedDoor(
                            opening_segment=door_ls,
                            frame_polygon=frame,  # type: ignore[arg-type]
                            swing_arc=swing,
                            door_type="TOILET",
                        )
                        doors_by_room.setdefault(room_id, []).append(door)

    return doors_by_room, entry_by_unit

