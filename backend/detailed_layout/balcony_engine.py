"""
detailed_layout/balcony_engine.py — balcony and railing detailing.

Phase D v1 treats balconies only when explicitly tagged (room_type == "BALCONY").
"""

from __future__ import annotations

from typing import Dict, List

from shapely.affinity import scale
from shapely.geometry import LineString

from detailed_layout.models import DetailedBalcony
from residential_layout.floor_aggregation import FloorLayoutContract
from residential_layout.models import UnitLayoutContract


def build_balconies_for_floor(
    floor: FloorLayoutContract,
    units: List[UnitLayoutContract],
) -> Dict[str, List[DetailedBalcony]]:
    balconies_by_room: Dict[str, List[DetailedBalcony]] = {}

    for unit in units:
        unit_id = unit.unit_id or ""
        for idx, room in enumerate(unit.rooms):
            room_id = f"{unit_id}_{idx}"
            if room.room_type != "BALCONY":
                continue
            outline = room.polygon
            # Simple railing line: slightly inset copy of one edge (use top edge)
            minx, miny, maxx, maxy = outline.bounds
            railing = LineString([(minx, maxy), (maxx, maxy)])
            balconies_by_room.setdefault(room_id, []).append(
                DetailedBalcony(outline=outline, railing_line=railing)
            )

    return balconies_by_room

