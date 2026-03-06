"""
detailed_layout/models.py — Detailed geometric contracts for Phase D.

These dataclasses are read/write in-memory models used by the detailing
engines and DXF adapter. They mirror FloorLayoutContract / BuildingLayoutContract
but enrich them with drafting-ready primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from shapely.geometry import LineString, Point, Polygon


# ── Atomic geometry types ─────────────────────────────────────────────────────


WallType = Literal["EXTERNAL", "INTERNAL", "SHAFT"]
DoorType = Literal["ENTRY", "BEDROOM", "TOILET", "KITCHEN"]


@dataclass
class DetailedWall:
    """Single wall segment with centerline and polygon, classified by type."""

    centerline: LineString
    polygon: Polygon
    wall_type: WallType


@dataclass
class DetailedDoor:
    """Door opening, frame, and swing geometry along a wall."""

    opening_segment: LineString
    frame_polygon: Polygon
    swing_arc: LineString
    door_type: DoorType


@dataclass
class DetailedWindow:
    """Window opening and frame geometry on an external wall."""

    opening_segment: LineString
    frame_polygon: Polygon
    sill_height_m: float


@dataclass
class DetailedFixture:
    """Sanitary or kitchen fixture (WC, basin, sink, cooktop, trap, etc.)."""

    kind: str
    outline: Polygon


@dataclass
class DetailedFurniture:
    """Furniture footprint (bed, sofa, wardrobe, table, etc.)."""

    kind: str
    outline: Polygon


@dataclass
class DetailedGridLine:
    """Structural grid line."""

    line: LineString
    label: Optional[str] = None


@dataclass
class DetailedColumn:
    """Structural column footprint."""

    outline: Polygon
    label: Optional[str] = None


@dataclass
class DetailedStair:
    """Stair flight and landing geometry."""

    outline: Polygon
    direction_arrow: Optional[LineString] = None


@dataclass
class DetailedCore:
    """Core outline (stair+lift) and optional hatch polygon."""

    outline: Polygon
    hatch: Optional[Polygon] = None


@dataclass
class DetailedBalcony:
    """Balcony polygon and railing geometry."""

    outline: Polygon
    railing_line: Optional[LineString] = None


@dataclass
class DetailedAnnotation:
    """Text or symbolic annotation positioned in model space."""

    text: str
    position: Point
    layer: str = "A-TEXT"


# ── Room, unit, floor, building contracts ─────────────────────────────────────


@dataclass
class DetailedRoomGeometry:
    """Detailed geometry for a single logical room."""

    room_id: str
    room_type: str
    footprint: Polygon
    walls_ext: list[DetailedWall] = field(default_factory=list)
    walls_int: list[DetailedWall] = field(default_factory=list)
    doors: list[DetailedDoor] = field(default_factory=list)
    windows: list[DetailedWindow] = field(default_factory=list)
    fixtures: list[DetailedFixture] = field(default_factory=list)
    furniture: list[DetailedFurniture] = field(default_factory=list)
    annotations: list[DetailedAnnotation] = field(default_factory=list)


@dataclass
class DetailedUnitGeometry:
    """Detailed geometry for one residential unit."""

    unit_id: str
    rooms: dict[str, DetailedRoomGeometry]
    entry_door: Optional[DetailedDoor]
    unit_outline: Polygon


@dataclass
class DetailedFloorLayoutContract:
    """
    Phase D floor-level output: units plus shared elements (grid, core, etc.).
    """

    floor_id: str
    units: dict[str, DetailedUnitGeometry]
    grid_lines: list[DetailedGridLine] = field(default_factory=list)
    columns: list[DetailedColumn] = field(default_factory=list)
    stairs: list[DetailedStair] = field(default_factory=list)
    cores: list[DetailedCore] = field(default_factory=list)
    balconies: list[DetailedBalcony] = field(default_factory=list)
    annotations: list[DetailedAnnotation] = field(default_factory=list)


@dataclass
class DetailedBuildingLayoutContract:
    """
    Phase D building-level output: stack of detailed floors.
    """

    building_id: str
    floors: list[DetailedFloorLayoutContract]

