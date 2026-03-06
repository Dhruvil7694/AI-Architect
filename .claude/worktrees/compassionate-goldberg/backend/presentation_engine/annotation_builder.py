"""
presentation_engine/annotation_builder.py
------------------------------------------
Builds text annotation for the presentation DXF.

Produces:
    title_block  — project / building summary placed below the footprint
    room_labels  — one AnnotationBlock per room placed at its centroid

No DXF entity creation here — only text content and insert coordinates.
The presentation_exporter handles the actual ezdxf MTEXT/TEXT writing.

Public API
----------
    build(skeleton, rooms, *, tp_num, fp_num, height_m)
        -> tuple[AnnotationBlock, list[AnnotationBlock]]
"""

from __future__ import annotations

from typing import Optional

from floor_skeleton.models import FloorSkeleton
from presentation_engine.models import AnnotationBlock, RoomGeometry

# ── Constants ──────────────────────────────────────────────────────────────────

_TITLE_TEXT_HEIGHT = 0.20     # metres
_LABEL_TEXT_HEIGHT = 0.15     # metres
_LABEL_MIN_DIM     = 0.80     # metres — skip label if room bounding box < this

_TITLE_LAYER = "A-TEXT"
_LABEL_LAYER = "A-TEXT"

# Gap below footprint baseline before title block insert point
_TITLE_GAP_M = 0.80


# ── Public function ────────────────────────────────────────────────────────────

def build(
    skeleton: FloorSkeleton,
    rooms: list[RoomGeometry],
    *,
    tp_num: Optional[int] = None,
    fp_num: Optional[int] = None,
    height_m: Optional[float] = None,
) -> tuple[AnnotationBlock, list[AnnotationBlock]]:
    """
    Build title block and room label annotations from *skeleton*.

    Parameters
    ----------
    skeleton  : Source FloorSkeleton.
    rooms     : Post-split RoomGeometry list from room_splitter.
    tp_num    : TP scheme number for title block (optional).
    fp_num    : FP number for title block (optional).
    height_m  : Building height in metres for title block (optional).

    Returns
    -------
    title_block  : Single AnnotationBlock placed below the footprint.
    room_labels  : One AnnotationBlock per room placed at its centroid.
    """
    title_block = _build_title_block(skeleton, tp_num, fp_num, height_m)
    room_labels = _build_room_labels(rooms)
    return title_block, room_labels


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_title_block(
    skeleton: FloorSkeleton,
    tp_num: Optional[int],
    fp_num: Optional[int],
    height_m: Optional[float],
) -> AnnotationBlock:
    """Build the project / metrics title block placed below the footprint."""
    minx, miny, maxx, maxy = skeleton.footprint_polygon.bounds

    # Insert point: left edge, below footprint
    insert_x = minx
    insert_y = miny - _TITLE_GAP_M

    # ── Header line ────────────────────────────────────────────────────────────
    header_parts = ["ARCHITECTURE AI"]
    if tp_num is not None:
        header_parts.append(f"TP{tp_num}")
    if fp_num is not None:
        header_parts.append(f"FP{fp_num}")
    header = "  |  ".join(header_parts)

    # ── Building info ─────────────────────────────────────────────────────────
    height_str = f"{height_m:.1f} m" if height_m is not None else "—"

    # ── Metrics ───────────────────────────────────────────────────────────────
    eff_pct  = skeleton.efficiency_ratio * 100
    fp_area  = skeleton.area_summary.get("footprint_area_sqm", 0.0)
    unit_area = skeleton.area_summary.get("unit_area_sqm", 0.0)
    core_area = skeleton.area_summary.get("core_area_sqm", 0.0)
    corr_area = skeleton.area_summary.get("corridor_area_sqm", 0.0)

    lines = [
        header,
        f"Height: {height_str}   Pattern: {skeleton.pattern_used}",
        f"Placement: {skeleton.placement_label}",
        f"Footprint: {fp_area:.1f} sqm   Efficiency: {eff_pct:.1f}%",
        f"Unit: {unit_area:.1f} sqm   Core: {core_area:.1f} sqm   "
        f"Corridor: {corr_area:.1f} sqm",
    ]

    # Append viability flag
    if not skeleton.is_architecturally_viable:
        lines.append("* EFFICIENCY BELOW 35% THRESHOLD *")

    return AnnotationBlock(
        lines=lines,
        insert_point=(round(insert_x, 6), round(insert_y, 6)),
        text_height=_TITLE_TEXT_HEIGHT,
        layer=_TITLE_LAYER,
    )


def _build_room_labels(rooms: list[RoomGeometry]) -> list[AnnotationBlock]:
    """Build one label block per room, placed at the room centroid."""
    labels: list[AnnotationBlock] = []

    for room in rooms:
        try:
            minx, miny, maxx, maxy = room.polygon.bounds
            # Skip if room is too small to show a label legibly
            if (maxx - minx) < _LABEL_MIN_DIM or (maxy - miny) < _LABEL_MIN_DIM:
                continue

            centroid = room.polygon.centroid
            label_lines = [
                room.label,
                f"{room.area_sqm:.1f}m\u00b2",  # ² character
            ]
            labels.append(AnnotationBlock(
                lines=label_lines,
                insert_point=(round(centroid.x, 6), round(centroid.y, 6)),
                text_height=_LABEL_TEXT_HEIGHT,
                layer=_LABEL_LAYER,
            ))
        except Exception:
            # Never crash on label generation — silently skip
            continue

    return labels
