"""
presentation_engine/models.py
------------------------------
Pure-Python dataclasses for the Presentation Engine.

No Django ORM.  All geometry is Shapely in the same local metres frame
as the source FloorSkeleton — no coordinate transformation.

FloorSkeleton is held by *reference* and must never be mutated.

Dataclasses
-----------
    WallGeometry    — outer + inner ring coords for one wall polygon
    RoomGeometry    — labelled zone polygon (UNIT / ROOM / TOILET)
    DoorSymbol      — jamb point + swing parameters for one door
    AnnotationBlock — multi-line text block with insert point
    PresentationModel — complete presentation record for one floor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from floor_skeleton.models import FloorSkeleton


# ── WallGeometry ───────────────────────────────────────────────────────────────

@dataclass
class WallGeometry:
    """
    Represents one wall polygon as a pair of LWPOLYLINE coordinate lists.

    For double-line mode:
        outer_coords — exterior ring of the source polygon
        inner_coords — exterior ring of the inward-buffered polygon

    For single-line fallback:
        outer_coords — exterior ring only
        inner_coords — empty list
        is_double_line — False

    Attributes
    ----------
    outer_coords  : list of (x, y) tuples for the outer boundary.
    inner_coords  : list of (x, y) tuples for the inner boundary;
                    empty list when is_double_line is False.
    layer         : DXF layer name for both polylines.
    is_double_line: True → two polylines exported; False → one polyline.
    """
    outer_coords:  list[tuple[float, float]]
    inner_coords:  list[tuple[float, float]]
    layer:         str
    is_double_line: bool


# ── RoomGeometry ───────────────────────────────────────────────────────────────

@dataclass
class RoomGeometry:
    """
    A labelled room polygon in the local metres frame.

    Labels: "UNIT"  — unsplit unit zone
            "ROOM"  — bedroom / living zone after toilet split
            "TOILET"— wet-zone strip after toilet split

    Attributes
    ----------
    polygon  : Shapely Polygon in local metres frame (read-only reference).
    label    : Display string ("UNIT" / "ROOM" / "TOILET").
    area_sqm : Pre-computed area in square metres.
    """
    polygon:  object  # shapely.geometry.Polygon — avoid hard import cycle
    label:    str
    area_sqm: float


# ── DoorSymbol ─────────────────────────────────────────────────────────────────

@dataclass
class DoorSymbol:
    """
    Parameters needed to draw one door symbol as LINE + ARC.

    The door is a symbolic overlay — it does NOT cut the wall polylines.

    Attributes
    ----------
    jamb_point    : Hinge point (x, y) in local metres frame.
    direction_deg : Angle (degrees) of the open door leaf relative to +X axis.
                    The leaf LINE goes from jamb_point in this direction.
    arc_start_deg : Start angle of the swing ARC (degrees, CCW from +X).
    arc_end_deg   : End angle of the swing ARC (degrees, CCW from +X).
    width_m       : Door leaf length (= swing arc radius).  Default 0.9 m.
    """
    jamb_point:    tuple[float, float]
    direction_deg: float
    arc_start_deg: float
    arc_end_deg:   float
    width_m:       float = 0.9


# ── AnnotationBlock ────────────────────────────────────────────────────────────

@dataclass
class AnnotationBlock:
    """
    A multi-line text block for the DXF exporter.

    Attributes
    ----------
    lines        : Ordered list of text strings (one per line).
    insert_point : (x, y) insertion point for the top-left attachment.
    text_height  : Character height in metres.
    layer        : DXF layer name.
    """
    lines:        list[str]
    insert_point: tuple[float, float]
    text_height:  float
    layer:        str


# ── PresentationModel ──────────────────────────────────────────────────────────

@dataclass
class PresentationModel:
    """
    Complete presentation record for one floor skeleton.

    The source FloorSkeleton is held by reference and must not be mutated.
    All geometry in this model is in the same local metres frame as the
    FloorSkeleton.

    Audit flags record which fallback paths were taken so the exporter can
    add a warning note to the title block if needed.

    Attributes
    ----------
    skeleton         : Source FloorSkeleton (reference; do not mutate).
    external_walls   : Double-line (or fallback) wall for footprint exterior.
    core_walls       : Double-line (or fallback) wall for core polygon.
    partition_lines  : Zone-boundary lines as lists of (x,y) tuples.
    rooms            : Labelled room geometries (post-split or unsplit).
    doors            : Door symbols (may be empty list if placer failed).
    title_block      : Title block annotation.
    room_labels      : Per-room centroid labels.
    used_fallback_walls : True if wall_builder fell back from double-line.
    used_fallback_rooms : True if room_splitter fell back to unsplit zones.
    used_fallback_doors : True if door_placer was skipped entirely.
    """
    skeleton:          "FloorSkeleton"
    external_walls:    list[WallGeometry]
    core_walls:        list[WallGeometry]
    partition_lines:   list[list[tuple[float, float]]]
    rooms:             list[RoomGeometry]
    doors:             list[DoorSymbol]
    title_block:       AnnotationBlock
    room_labels:       list[AnnotationBlock]
    # Audit flags
    used_fallback_walls: bool
    used_fallback_rooms: bool
    used_fallback_doors: bool
