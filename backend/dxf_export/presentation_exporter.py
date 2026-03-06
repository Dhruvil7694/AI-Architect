"""
dxf_export/presentation_exporter.py
--------------------------------------
DXF writer for the Presentation Engine.

Consumes a PresentationModel and writes a professional schematic floor-plan
DXF.  This file is completely isolated from the original exporter.py — the
existing export_floor_skeleton_to_dxf() function is never called or modified.

Public API
----------
    export_presentation_to_dxf(pm, output_path) -> None

Entity types written
---------------------
    LWPOLYLINE — wall outer + inner rings, corridor boundary
    LINE       — partition lines, door leaf
    ARC        — door swing arc
    MTEXT      — title block, room labels

Layer usage
-----------
    A-WALL-EXT  — external footprint walls (outer + inner ring)
    A-CORE      — core walls (outer + inner ring)
    A-WALL-INT  — internal partition lines
    A-DOOR      — door leaf LINE + swing ARC
    A-CORR      — corridor polygon boundary (dashed)
    A-TEXT      — title block MTEXT + room label MTEXT

Coordinate system
-----------------
Local metres frame from FloorSkeleton — no site-frame back-transformation.
$INSUNITS = 4 (metres).
"""

from __future__ import annotations

import math

import ezdxf
from ezdxf.enums import TextEntityAlignment

from dxf_export.presentation_layers import setup_presentation_layers
from dxf_export.styles import ensure_text_style
from presentation_engine.models import (
    PresentationModel,
    WallGeometry,
    DoorSymbol,
    AnnotationBlock,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_INSUNITS_METRES = 4

# MTEXT width is capped at this fraction of the footprint width
_TEXT_WIDTH_RATIO = 0.8
_MAX_TEXT_WIDTH_M = 8.0


# ── Public API ─────────────────────────────────────────────────────────────────

def export_presentation_to_dxf(
    pm: PresentationModel,
    output_path: str,
) -> None:
    """
    Write *pm* to a layered DXF R2010 file at *output_path*.

    Never raises for geometry errors — individual entity writes are wrapped
    in try/except so a degenerate wall or door cannot abort the export.

    Parameters
    ----------
    pm          : PresentationModel from drawing_composer.compose().
    output_path : Absolute or relative path for the output .dxf file.
                  Raises OSError if path is not writable.
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = _INSUNITS_METRES

    setup_presentation_layers(doc)
    ensure_text_style(doc)

    msp = doc.modelspace()

    # ── Walls ──────────────────────────────────────────────────────────────────
    for wall in pm.external_walls:
        _write_wall(msp, wall)
    for wall in pm.core_walls:
        _write_wall(msp, wall)

    # ── Partition lines ────────────────────────────────────────────────────────
    for line_coords in pm.partition_lines:
        _write_partition(msp, line_coords)

    # ── Corridor boundary (dashed, A-CORR) ────────────────────────────────────
    if pm.skeleton.corridor_polygon is not None:
        _write_corridor(msp, pm.skeleton.corridor_polygon)

    # ── Door symbols ──────────────────────────────────────────────────────────
    for door in pm.doors:
        _write_door(msp, door)

    # ── Title block ───────────────────────────────────────────────────────────
    fp_minx, _, fp_maxx, _ = pm.skeleton.footprint_polygon.bounds
    fp_width = fp_maxx - fp_minx
    _write_annotation(msp, pm.title_block, fp_width)

    # ── Room labels ───────────────────────────────────────────────────────────
    for label in pm.room_labels:
        _write_annotation(msp, label, fp_width)

    # ── Fallback note (if any stage fell back) ────────────────────────────────
    if pm.used_fallback_walls or pm.used_fallback_rooms or pm.used_fallback_doors:
        _write_fallback_note(msp, pm)

    doc.saveas(output_path)


# ── Entity writers ─────────────────────────────────────────────────────────────

def _write_wall(msp, wall: WallGeometry) -> None:
    """Write outer (and optionally inner) LWPOLYLINE for one wall."""
    if not wall.outer_coords:
        return
    try:
        msp.add_lwpolyline(
            wall.outer_coords,
            dxfattribs={"layer": wall.layer, "closed": True},
        )
    except Exception:
        return

    if wall.is_double_line and wall.inner_coords:
        try:
            msp.add_lwpolyline(
                wall.inner_coords,
                dxfattribs={"layer": wall.layer, "closed": True},
            )
        except Exception:
            pass  # inner ring failure does not abort outer ring


def _write_partition(msp, coords: list[tuple]) -> None:
    """Write a partition line as a single LINE on A-WALL-INT."""
    if len(coords) < 2:
        return
    try:
        # Draw as polyline (may have > 2 points for diagonal partitions)
        msp.add_lwpolyline(
            coords,
            dxfattribs={"layer": "A-WALL-INT", "closed": False},
        )
    except Exception:
        pass


def _write_corridor(msp, corridor_polygon) -> None:
    """Write corridor boundary as a dashed LWPOLYLINE on A-CORR."""
    try:
        coords = list(corridor_polygon.exterior.coords)
        if coords and coords[0] == coords[-1]:
            coords = coords[:-1]
        coords = [(round(x, 6), round(y, 6)) for x, y in coords]
        if len(coords) >= 3:
            msp.add_lwpolyline(
                coords,
                dxfattribs={"layer": "A-CORR", "closed": True},
            )
    except Exception:
        pass


def _write_door(msp, door: DoorSymbol) -> None:
    """Write door leaf LINE and swing ARC on A-DOOR."""
    try:
        jx, jy = door.jamb_point
        rad_dir = math.radians(door.direction_deg)

        # Door leaf: LINE from jamb in direction_deg
        end_x = jx + door.width_m * math.cos(rad_dir)
        end_y = jy + door.width_m * math.sin(rad_dir)
        msp.add_line(
            start=(jx, jy),
            end=(round(end_x, 6), round(end_y, 6)),
            dxfattribs={"layer": "A-DOOR"},
        )

        # Swing ARC: center=jamb, radius=width, from arc_start to arc_end
        arc_span = abs(door.arc_end_deg - door.arc_start_deg)
        if arc_span >= 5.0:
            msp.add_arc(
                center=(jx, jy),
                radius=door.width_m,
                start_angle=door.arc_start_deg,
                end_angle=door.arc_end_deg,
                dxfattribs={"layer": "A-DOOR"},
            )
    except Exception:
        pass


def _write_annotation(msp, block: AnnotationBlock, fp_width: float) -> None:
    """Write an AnnotationBlock as an MTEXT entity."""
    if not block.lines:
        return
    try:
        text_content = "\\P".join(block.lines)  # MTEXT paragraph break
        ix, iy = block.insert_point

        text_width = min(_MAX_TEXT_WIDTH_M, fp_width * _TEXT_WIDTH_RATIO)
        text_width = max(text_width, 1.5)  # floor for very narrow footprints

        msp.add_mtext(
            text_content,
            dxfattribs={
                "layer":       block.layer,
                "char_height": block.text_height,
                "width":       text_width,
                "insert":      (ix, iy),
                "attachment_point": 7,   # top-left attachment
            },
        )
    except Exception:
        pass


def _write_fallback_note(msp, pm: PresentationModel) -> None:
    """Append a small warning note below the title block."""
    try:
        fp_minx, fp_miny, fp_maxx, _ = pm.skeleton.footprint_polygon.bounds
        fp_width = fp_maxx - fp_minx

        notes = []
        if pm.used_fallback_walls:
            notes.append("WALLS: single-line fallback")
        if pm.used_fallback_rooms:
            notes.append("ROOMS: unsplit fallback")
        if pm.used_fallback_doors:
            notes.append("DOORS: skipped")

        if not notes:
            return

        insert_y = fp_miny - 0.8 - 0.6 * (len(pm.title_block.lines) + 1)
        text_content = "\\P".join(["[FALLBACK ACTIVE]"] + notes)
        text_width = min(_MAX_TEXT_WIDTH_M, fp_width * _TEXT_WIDTH_RATIO)

        msp.add_mtext(
            text_content,
            dxfattribs={
                "layer":       "A-TEXT",
                "char_height": 0.12,
                "width":       text_width,
                "insert":      (round(fp_minx, 6), round(insert_y, 6)),
                "attachment_point": 7,
            },
        )
    except Exception:
        pass
