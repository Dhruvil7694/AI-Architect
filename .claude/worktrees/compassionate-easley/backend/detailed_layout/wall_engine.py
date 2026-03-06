"""
detailed_layout/wall_engine.py — build DetailedWall instances from contracts.

Implements the edge normalization and classification strategy described in
the Phase D plan:

- Shared room edges → internal walls
- Footprint-only edges → external walls
- Core/corridor-only edges → shaft/core walls
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from detailed_layout.config import DetailingConfig
from detailed_layout.geometry_utils import EdgeKey, edge_key, extract_edges, snap_linestring
from detailed_layout.models import DetailedWall
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import UnitLayoutContract, RoomInstance


@dataclass
class EdgeRecord:
    key: EdgeKey
    segment: LineString
    rooms: List[str]
    on_footprint: bool = False
    on_core: bool = False
    on_corridor: bool = False


def _collect_room_edges(
    units: List[UnitLayoutContract],
    floor_id: str,
    snap_tol: float,
) -> Dict[EdgeKey, EdgeRecord]:
    records: Dict[EdgeKey, EdgeRecord] = {}

    for unit in units:
        unit_id = unit.unit_id or ""
        for idx, room in enumerate(unit.rooms):
            room_id = f"{unit_id or floor_id}_{idx}"
            for seg in extract_edges(room.polygon):
                coords = list(seg.coords)
                p0 = (coords[0][0], coords[0][1])
                p1 = (coords[-1][0], coords[-1][1])
                k = edge_key(p0, p1, snap_tol)
                rec = records.get(k)
                if rec is None:
                    rec = EdgeRecord(key=k, segment=snap_linestring(seg, snap_tol), rooms=[room_id])
                    records[k] = rec
                else:
                    rec.rooms.append(room_id)
    return records


def _mark_boundary_edges(
    poly: Optional[Polygon],
    records: Dict[EdgeKey, EdgeRecord],
    snap_tol: float,
    attr: str,
) -> None:
    if poly is None or poly.is_empty:
        return
    for seg in extract_edges(poly):
        coords = list(seg.coords)
        p0 = (coords[0][0], coords[0][1])
        p1 = (coords[-1][0], coords[-1][1])
        k = edge_key(p0, p1, snap_tol)
        rec = records.get(k)
        if rec is None:
            rec = EdgeRecord(key=k, segment=snap_linestring(seg, snap_tol), rooms=[])
            records[k] = rec
        setattr(rec, attr, True)


def _classify_wall_type(rec: EdgeRecord) -> Optional[str]:
    """Return 'EXTERNAL', 'INTERNAL', 'SHAFT', or None for 'no wall'."""
    if rec.on_core or rec.on_corridor:
        return "SHAFT"
    if len(rec.rooms) >= 2:
        return "INTERNAL"
    if rec.on_footprint and len(rec.rooms) == 1:
        return "EXTERNAL"
    # Edges that belong to a single room but are not on footprint/core/corridor
    # are still internal partitions (e.g. room-to-void), but we skip them for v1.
    return None


def build_walls_for_floor(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
) -> Tuple[List[DetailedWall], Dict[str, List[DetailedWall]], Dict[str, List[DetailedWall]]]:
    """
    Build DetailedWall instances for a FloorLayoutContract.

    Returns:
      - all_walls: flat list of all DetailedWall objects.
      - walls_ext_by_room: room_id -> list of external walls.
      - walls_int_by_room: room_id -> list of internal walls.
    """
    snap_tol = config.snap_tol_m

    # 1. Collect normalized room edges.
    records = _collect_room_edges(units, floor.floor_id, snap_tol)

    # 2. Mark footprint/core/corridor edges.
    _mark_boundary_edges(floor.footprint_polygon, records, snap_tol, "on_footprint")
    _mark_boundary_edges(floor.core_polygon, records, snap_tol, "on_core")
    _mark_boundary_edges(floor.corridor_polygon, records, snap_tol, "on_corridor")

    walls: List[DetailedWall] = []
    walls_ext_by_room: Dict[str, List[DetailedWall]] = {}
    walls_int_by_room: Dict[str, List[DetailedWall]] = {}

    # 3. For each edge record, classify and create wall centerline + polygon.
    for rec in records.values():
        wall_type = _classify_wall_type(rec)
        if wall_type is None:
            continue
        centerline = rec.segment
        if wall_type == "EXTERNAL":
            thickness = config.external_wall_thickness_m
        elif wall_type == "INTERNAL":
            thickness = config.internal_wall_thickness_m
        else:
            thickness = config.shaft_wall_thickness_m

        # Construct a simple wall polygon by buffering the centerline.
        # For internal walls we split thickness evenly around the centerline;
        # for external walls this initial polygon will be trimmed/adjusted by
        # the caller if needed.
        poly = centerline.buffer(thickness / 2.0, cap_style=2)  # square caps
        wall = DetailedWall(centerline=centerline, polygon=poly, wall_type=wall_type)  # type: ignore[arg-type]
        walls.append(wall)

        if wall_type == "EXTERNAL":
            for room_id in rec.rooms:
                walls_ext_by_room.setdefault(room_id, []).append(wall)
        elif wall_type == "INTERNAL":
            for room_id in rec.rooms:
                walls_int_by_room.setdefault(room_id, []).append(wall)

    # 4. Cleanup: optional union pass to remove tiny overlaps at junctions.
    if walls:
        merged = unary_union([w.polygon for w in walls])
        # We keep original polygons; union is used only as a global sanity check
        # (e.g. to catch invalid topology during tests) and for potential future
        # trimming logic.
        _ = merged

    return walls, walls_ext_by_room, walls_int_by_room

