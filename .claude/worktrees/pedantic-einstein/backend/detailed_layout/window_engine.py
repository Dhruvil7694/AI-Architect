"""
detailed_layout/window_engine.py — deterministic window placement engine.

Windows are placed only on external walls (room–footprint boundary) with
minimum edge length constraints per room type.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon

from detailed_layout.config import DetailingConfig
from detailed_layout.geometry_utils import extract_edges
from detailed_layout.models import DetailedWindow
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import RoomInstance, UnitLayoutContract


def _edge_on_boundary(edge: LineString, boundary: Polygon, tol: float) -> bool:
    """Return True if edge lies on the polygon boundary (within tolerance)."""
    inter = edge.intersection(boundary.boundary)
    if inter.is_empty:
        return False
    if isinstance(inter, LineString):
        return inter.length + tol >= edge.length
    max_len = 0.0
    for geom in getattr(inter, "geoms", []):
        if isinstance(geom, LineString):
            max_len = max(max_len, geom.length)
    return max_len + tol >= edge.length


def _choose_window_edge(
    room: RoomInstance,
    footprint: Polygon,
    width_m: float,
    clear_m: float,
    tol: float,
) -> Optional[LineString]:
    """Pick the longest external edge that can host a window."""
    candidates: List[Tuple[LineString, float]] = []
    for seg in extract_edges(room.polygon):
        if not _edge_on_boundary(seg, footprint, tol):
            continue
        L = seg.length
        if L < width_m + 2 * clear_m:
            continue
        candidates.append((seg, L))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[1], reverse=True)
    return candidates[0][0]


def _make_window_segment(edge: LineString, width_m: float) -> LineString:
    """Center a window of width_m on the given edge."""
    p0 = edge.coords[0]
    p1 = edge.coords[-1]
    vx = p1[0] - p0[0]
    vy = p1[1] - p0[1]
    L = (vx * vx + vy * vy) ** 0.5
    if L <= 0:
        return edge
    ux, uy = vx / L, vy / L
    cx = (p0[0] + p1[0]) * 0.5
    cy = (p0[1] + p1[1]) * 0.5
    half = width_m / 2.0
    ax = cx - ux * half
    ay = cy - uy * half
    bx = cx + ux * half
    by = cy + uy * half
    return LineString([(ax, ay), (bx, by)])


def build_windows_for_floor(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
) -> Dict[str, List[DetailedWindow]]:
    """
    Build DetailedWindow instances for all rooms on a floor.

    Returns:
      windows_by_room: room_id -> list[DetailedWindow]
    """
    windows_by_room: Dict[str, List[DetailedWindow]] = {}

    footprint = floor.footprint_polygon
    tol = config.snap_tol_m
    clearance = config.window_clearance_min_m

    for unit in units:
        unit_id = unit.unit_id or ""
        for idx, room in enumerate(unit.rooms):
            room_id = f"{unit_id}_{idx}"
            room_type = room.room_type
            if room_type not in ("LIVING", "BEDROOM", "TOILET"):
                continue

            if room_type == "TOILET":
                width = config.window_widths_m.get("TOILET_VENT", 0.6)
                sill = config.window_sill_heights_m.get("TOILET_VENT", 1.8)
            else:
                width = config.window_widths_m.get(room_type, 1.2)
                sill = config.window_sill_heights_m.get(room_type, 0.9)

            edge = _choose_window_edge(room, footprint, width, clearance, tol)
            if edge is None:
                continue

            opening = _make_window_segment(edge, width)
            frame = opening.buffer(0.02, cap_style=2)
            win = DetailedWindow(
                opening_segment=opening,
                frame_polygon=frame,  # type: ignore[arg-type]
                sill_height_m=sill,
            )
            windows_by_room.setdefault(room_id, []).append(win)

    return windows_by_room

