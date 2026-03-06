"""
detailed_layout/furniture_engine.py — deterministic furniture placement.

Implements simple, rule-based furniture for LIVING and BEDROOM:
- Sofa / TV / table in living.
- Bed / wardrobe in bedroom.
Placement uses fixed candidate wall sequences and collision checks.
"""

from __future__ import annotations

from typing import Dict, List

from shapely.geometry import Polygon

from detailed_layout.config import DetailingConfig
from detailed_layout.models import DetailedFurniture, DetailedWall, DetailedDoor
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import UnitLayoutContract


def _room_bounds(poly: Polygon) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = poly.bounds
    return float(minx), float(miny), float(maxx), float(maxy)


def _place_bed(room_poly: Polygon) -> Polygon:
    """Place a bed rectangle against the longest wall by bounding box heuristics."""
    minx, miny, maxx, maxy = _room_bounds(room_poly)
    w = maxx - minx
    d = maxy - miny
    bed_w = min(1.8, w * 0.9)
    bed_d = min(2.0, d * 0.9)
    # Longest wall: choose longer of width/depth and align headboard to that wall.
    if w >= d:
        # Headboard on bottom wall
        x0 = minx + (w - bed_w) * 0.5
        y0 = miny
    else:
        # Headboard on left wall
        x0 = minx
        y0 = miny + (d - bed_d) * 0.5
    return Polygon(
        [
            (x0, y0),
            (x0 + bed_w, y0),
            (x0 + bed_w, y0 + bed_d),
            (x0, y0 + bed_d),
        ]
    )


def _place_wardrobe(room_poly: Polygon) -> Polygon:
    """Simple wardrobe rectangle along a secondary wall."""
    minx, miny, maxx, maxy = _room_bounds(room_poly)
    w = maxx - minx
    d = maxy - miny
    wr_w = min(0.6, w * 0.5)
    wr_d = min(2.0, d * 0.9)
    # Place along left wall
    x0 = minx
    y0 = miny + (d - wr_d) * 0.5
    return Polygon(
        [
            (x0, y0),
            (x0 + wr_w, y0),
            (x0 + wr_w, y0 + wr_d),
            (x0, y0 + wr_d),
        ]
    )


def _place_living_sofa(room_poly: Polygon) -> Polygon:
    """Place sofa against the longest internal wall by bbox heuristic."""
    minx, miny, maxx, maxy = _room_bounds(room_poly)
    w = maxx - minx
    d = maxy - miny
    sofa_w = min(2.0, w * 0.8)
    sofa_d = min(0.9, d * 0.5)
    if w >= d:
        # Back on bottom wall
        x0 = minx + (w - sofa_w) * 0.5
        y0 = miny
    else:
        # Back on left wall
        x0 = minx
        y0 = miny + (d - sofa_d) * 0.5
    return Polygon(
        [
            (x0, y0),
            (x0 + sofa_w, y0),
            (x0 + sofa_w, y0 + sofa_d),
            (x0, y0 + sofa_d),
        ]
    )


def _place_living_table(room_poly: Polygon) -> Polygon:
    """Small table centered in the room."""
    minx, miny, maxx, maxy = _room_bounds(room_poly)
    w = maxx - minx
    d = maxy - miny
    tb_w = min(1.0, w * 0.3)
    tb_d = min(1.0, d * 0.3)
    x0 = minx + (w - tb_w) * 0.5
    y0 = miny + (d - tb_d) * 0.5
    return Polygon(
        [
            (x0, y0),
            (x0 + tb_w, y0),
            (x0 + tb_w, y0 + tb_d),
            (x0, y0 + tb_d),
        ]
    )


def _place_tv_unit(room_poly: Polygon) -> Polygon:
    """TV unit opposite the sofa, approximated along top wall."""
    minx, miny, maxx, maxy = _room_bounds(room_poly)
    w = maxx - minx
    depth = 0.3
    tv_w = min(1.8, w * 0.7)
    x0 = minx + (w - tv_w) * 0.5
    y0 = maxy - depth
    return Polygon(
        [
            (x0, y0),
            (x0 + tv_w, y0),
            (x0 + tv_w, maxy),
            (x0, maxy),
        ]
    )


def build_furniture_for_floor(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    walls_by_room: Dict[str, List[DetailedWall]],
    doors_by_room: Dict[str, List[DetailedDoor]],
    config: DetailingConfig,
) -> Dict[str, List[DetailedFurniture]]:
    """
    Build DetailedFurniture instances for living/bedroom rooms on a floor.

    Collision checks are conservative: furniture polygons must not intersect
    any wall polygon or door frame; otherwise they are skipped.
    """
    furn_by_room: Dict[str, List[DetailedFurniture]] = {}
    if not config.furniture_enabled:
        return furn_by_room

    for unit in units:
        unit_id = unit.unit_id or ""
        for idx, room in enumerate(unit.rooms):
            room_id = f"{unit_id}_{idx}"
            poly = room.polygon
            walls = walls_by_room.get(room_id, [])
            doors = doors_by_room.get(room_id, [])
            placed: List[Polygon] = []

            def _collides(p: Polygon) -> bool:
                for w in walls:
                    if p.intersects(w.polygon):
                        return True
                for d in doors:
                    if p.intersects(d.frame_polygon):
                        return True
                for q in placed:
                    if p.intersection(q).area > 0.0:
                        return True
                return False

            if room.room_type == "BEDROOM":
                items: List[DetailedFurniture] = []
                bed_poly = _place_bed(poly)
                if not _collides(bed_poly):
                    items.append(DetailedFurniture(kind="BED", outline=bed_poly))
                    placed.append(bed_poly)
                wr_poly = _place_wardrobe(poly)
                if not _collides(wr_poly):
                    items.append(DetailedFurniture(kind="WARDROBE", outline=wr_poly))
                    placed.append(wr_poly)
                if items:
                    furn_by_room[room_id] = items

            if room.room_type == "LIVING":
                items = []
                sofa_poly = _place_living_sofa(poly)
                if not _collides(sofa_poly):
                    items.append(DetailedFurniture(kind="SOFA", outline=sofa_poly))
                    placed.append(sofa_poly)
                table_poly = _place_living_table(poly)
                if not _collides(table_poly):
                    items.append(DetailedFurniture(kind="TABLE", outline=table_poly))
                    placed.append(table_poly)
                tv_poly = _place_tv_unit(poly)
                if not _collides(tv_poly):
                    items.append(DetailedFurniture(kind="TV_UNIT", outline=tv_poly))
                    placed.append(tv_poly)
                if items:
                    furn_by_room[room_id] = items

    return furn_by_room

