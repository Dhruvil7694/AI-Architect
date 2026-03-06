"""
detailed_layout/wet_area_engine.py — toilet and kitchen detailing.

Places simple WC / basin / shower / sink / cooktop fixtures and wet hatches
in TOILET and KITCHEN rooms, using deterministic rules.
"""

from __future__ import annotations

from typing import Dict, List

from shapely.affinity import translate
from shapely.geometry import Polygon

from detailed_layout.config import DetailingConfig
from detailed_layout.models import DetailedFixture
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import RoomInstance, UnitLayoutContract


def _room_bounds(poly: Polygon) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = poly.bounds
    return float(minx), float(miny), float(maxx), float(maxy)


def _toilet_fixtures(room: RoomInstance) -> List[DetailedFixture]:
    """Deterministic WC, basin, shower, trap inside a toilet polygon."""
    fixtures: List[DetailedFixture] = []
    minx, miny, maxx, maxy = _room_bounds(room.polygon)
    w = maxx - minx
    d = maxy - miny
    # WC: small rectangle at back-left corner, then clipped to room polygon
    wc_w, wc_d = min(0.8, w * 0.5), min(1.2, d * 0.6)
    wc_raw = Polygon(
        [
            (minx, miny),
            (minx + wc_w, miny),
            (minx + wc_w, miny + wc_d),
            (minx, miny + wc_d),
        ]
    )
    wc = room.polygon.intersection(wc_raw)
    if not wc.is_empty:
        fixtures.append(DetailedFixture(kind="WC", outline=wc))
    # Basin: small rectangle on front wall, centered
    basin_w, basin_d = min(0.6, w * 0.4), 0.4
    bx0 = minx + (w - basin_w) * 0.5
    basin_raw = Polygon(
        [
            (bx0, maxy - basin_d),
            (bx0 + basin_w, maxy - basin_d),
            (bx0 + basin_w, maxy),
            (bx0, maxy),
        ]
    )
    basin = room.polygon.intersection(basin_raw)
    if not basin.is_empty:
        fixtures.append(DetailedFixture(kind="BASIN", outline=basin))
    # Shower: square in back-right corner
    sh = min(0.9, min(w, d) * 0.5)
    shower_raw = Polygon(
        [
            (maxx - sh, miny),
            (maxx, miny),
            (maxx, miny + sh),
            (maxx - sh, miny + sh),
        ]
    )
    shower = room.polygon.intersection(shower_raw)
    if not shower.is_empty:
        fixtures.append(DetailedFixture(kind="SHOWER", outline=shower))
    # Floor trap: tiny square near shower
    ft = 0.2
    trap_raw = Polygon(
        [
            (maxx - ft * 1.5, miny + ft),
            (maxx - ft * 0.5, miny + ft),
            (maxx - ft * 0.5, miny + 2 * ft),
            (maxx - ft * 1.5, miny + 2 * ft),
        ]
    )
    trap = room.polygon.intersection(trap_raw)
    if not trap.is_empty:
        fixtures.append(DetailedFixture(kind="TRAP", outline=trap))
    return fixtures


def _kitchen_fixtures(room: RoomInstance) -> List[DetailedFixture]:
    """Deterministic counter, sink, cooktop in a kitchen polygon."""
    fixtures: List[DetailedFixture] = []
    minx, miny, maxx, maxy = _room_bounds(room.polygon)
    w = maxx - minx
    d = maxy - miny
    depth = min(0.6, d * 0.6)
    # Counter along back wall (miny), then clipped
    counter_raw = Polygon(
        [
            (minx, miny),
            (maxx, miny),
            (maxx, miny + depth),
            (minx, miny + depth),
        ]
    )
    counter = room.polygon.intersection(counter_raw)
    if not counter.is_empty:
        fixtures.append(DetailedFixture(kind="COUNTER", outline=counter))
    # Sink: left side of counter
    sink_w = min(0.8, w * 0.4)
    sink_raw = Polygon(
        [
            (minx, miny),
            (minx + sink_w, miny),
            (minx + sink_w, miny + depth),
            (minx, miny + depth),
        ]
    )
    sink = room.polygon.intersection(sink_raw)
    if not sink.is_empty:
        fixtures.append(DetailedFixture(kind="SINK", outline=sink))
    # Cooktop: right side of counter
    cook_w = min(0.9, w * 0.4)
    cx0 = maxx - cook_w
    cooktop_raw = Polygon(
        [
            (cx0, miny),
            (maxx, miny),
            (maxx, miny + depth),
            (cx0, miny + depth),
        ]
    )
    cooktop = room.polygon.intersection(cooktop_raw)
    if not cooktop.is_empty:
        fixtures.append(DetailedFixture(kind="COOKTOP", outline=cooktop))
    return fixtures


def build_wet_areas_for_floor(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
    config: DetailingConfig,
) -> Dict[str, List[DetailedFixture]]:
    """
    Build DetailedFixture instances for toilets and kitchens on a floor.

    Returns:
      fixtures_by_room: room_id -> list[DetailedFixture]
    """
    fixtures_by_room: Dict[str, List[DetailedFixture]] = {}

    for unit in units:
        unit_id = unit.unit_id or ""
        for idx, room in enumerate(unit.rooms):
            room_id = f"{unit_id}_{idx}"
            if room.room_type == "TOILET":
                fixtures_by_room[room_id] = _toilet_fixtures(room)
            elif room.room_type == "KITCHEN":
                fixtures_by_room[room_id] = _kitchen_fixtures(room)

    return fixtures_by_room

