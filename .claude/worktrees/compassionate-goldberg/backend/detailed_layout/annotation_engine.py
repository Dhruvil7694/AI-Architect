"""
detailed_layout/annotation_engine.py — room/unit/global annotations.
"""

from __future__ import annotations

from typing import Dict, List

from shapely.geometry import Point

from detailed_layout.config import DetailingConfig
from detailed_layout.models import DetailedAnnotation, DetailedFloorLayoutContract, DetailedRoomGeometry


def annotate_rooms(
    detailed_floor: DetailedFloorLayoutContract,
    config: DetailingConfig,
) -> None:
    """Add room name and area annotations to each room geometry."""
    for unit in detailed_floor.units.values():
        for room in unit.rooms.values():
            centroid = room.footprint.centroid
            area_sqm = room.footprint.area
            room.annotations.append(
                DetailedAnnotation(
                    text=room.room_type,
                    position=Point(centroid.x, centroid.y),
                    layer="A-TEXT",
                )
            )
            room.annotations.append(
                DetailedAnnotation(
                    text=f"{area_sqm:.1f} sqm",
                    position=Point(centroid.x, centroid.y - config.room_text_height_m),
                    layer="A-TEXT",
                )
            )


def annotate_floor_global(
    detailed_floor: DetailedFloorLayoutContract,
    config: DetailingConfig,
) -> None:
    """Add simple global annotations: north arrow stub and scale text."""
    # Compute floor bounding box from all room footprints
    xs: List[float] = []
    ys: List[float] = []
    for unit in detailed_floor.units.values():
        for room in unit.rooms.values():
            minx, miny, maxx, maxy = room.footprint.bounds
            xs.extend([minx, maxx])
            ys.extend([miny, maxy])
    if not xs or not ys:
        return
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)

    # North arrow at bottom-left margin
    north_pos = Point(minx - 1.0, miny - 1.0)
    detailed_floor.annotations.append(
        DetailedAnnotation(text="N", position=north_pos, layer="A-ANNOTATION")
    )
    # Scale text
    scale_pos = Point(minx, miny - 1.5)
    detailed_floor.annotations.append(
        DetailedAnnotation(text="SCALE 1:100", position=scale_pos, layer="A-TEXT")
    )

