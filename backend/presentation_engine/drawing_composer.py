"""
presentation_engine/drawing_composer.py
-----------------------------------------
Orchestrates all presentation sub-modules with per-stage try/except guards.

Each stage is independently wrapped so a failure in one stage never prevents
subsequent stages from running.  Audit flags on the PresentationModel record
which fallbacks were taken.

Pipeline
--------
    FloorSkeleton
        Stage 1 → wall_builder.build()      (fallback: single-line walls)
        Stage 2 → room_splitter.split()     (fallback: unsplit unit zones)
        Stage 3 → door_placer.place()       (fallback: doors = [])
        Stage 4 → annotation_builder.build()  (always succeeds)
        → PresentationModel

The compose() function itself NEVER raises.  If a catastrophic failure
occurs (e.g. annotation_builder crashes), the caller (generate_floorplan)
is expected to catch it and fall back to export_floor_skeleton_to_dxf.

Public API
----------
    compose(skeleton, *, tp_num, fp_num, height_m) -> PresentationModel
"""

from __future__ import annotations

import logging
from typing import Optional

from floor_skeleton.models import FloorSkeleton
from presentation_engine import (
    wall_builder,
    room_splitter,
    door_placer,
    annotation_builder,
)
from presentation_engine.models import PresentationModel

logger = logging.getLogger(__name__)


def compose(
    skeleton: FloorSkeleton,
    *,
    tp_num:   Optional[int]   = None,
    fp_num:   Optional[int]   = None,
    height_m: Optional[float] = None,
) -> PresentationModel:
    """
    Build a PresentationModel from *skeleton* with full fallback protection.

    Parameters
    ----------
    skeleton  : Validated FloorSkeleton (is_geometry_valid must be True).
    tp_num    : TP scheme number for annotation (optional).
    fp_num    : FP number for annotation (optional).
    height_m  : Building height in metres for annotation (optional).

    Returns
    -------
    PresentationModel with at least walls and a title block.
    Audit flags indicate which fallback paths were taken.
    """
    # ── Stage 1: Walls ─────────────────────────────────────────────────────────
    used_fallback_walls = False
    try:
        ext_walls, core_walls, partition_lines, any_fallback = (
            wall_builder.build(skeleton)
        )
        used_fallback_walls = any_fallback
    except Exception as exc:
        logger.warning(
            "wall_builder.build() raised %s: %s — using single-line fallback.",
            type(exc).__name__, exc,
        )
        try:
            ext_walls, core_walls, partition_lines = (
                wall_builder.build_fallback(skeleton)
            )
        except Exception as exc2:
            logger.error(
                "wall_builder.build_fallback() also failed: %s — "
                "using empty walls.", exc2,
            )
            ext_walls, core_walls, partition_lines = [], [], []
        used_fallback_walls = True

    # ── Stage 2: Rooms ─────────────────────────────────────────────────────────
    used_fallback_rooms = False
    try:
        rooms = room_splitter.split(skeleton)
    except Exception as exc:
        logger.warning(
            "room_splitter.split() raised %s: %s — using unsplit zones.",
            type(exc).__name__, exc,
        )
        try:
            rooms = room_splitter.split_fallback(skeleton)
        except Exception as exc2:
            logger.error(
                "room_splitter.split_fallback() also failed: %s — "
                "using empty rooms.", exc2,
            )
            rooms = []
        used_fallback_rooms = True

    # ── Stage 3: Doors ─────────────────────────────────────────────────────────
    used_fallback_doors = False
    try:
        doors = door_placer.place(skeleton, rooms)
    except Exception as exc:
        logger.warning(
            "door_placer.place() raised %s: %s — skipping doors.",
            type(exc).__name__, exc,
        )
        doors = []
        used_fallback_doors = True

    # ── Stage 4: Annotations ───────────────────────────────────────────────────
    # annotation_builder.build() is pure string operations; should not fail.
    # If it does, we still produce a minimal AnnotationBlock so the model is valid.
    try:
        title_block, room_labels = annotation_builder.build(
            skeleton, rooms,
            tp_num=tp_num,
            fp_num=fp_num,
            height_m=height_m,
        )
    except Exception as exc:
        logger.warning(
            "annotation_builder.build() raised %s: %s — using minimal title.",
            type(exc).__name__, exc,
        )
        from presentation_engine.models import AnnotationBlock
        minx, miny, _, _ = skeleton.footprint_polygon.bounds
        title_block = AnnotationBlock(
            lines=["ARCHITECTURE AI", f"Pattern: {skeleton.pattern_used}"],
            insert_point=(round(minx, 6), round(miny - 0.8, 6)),
            text_height=0.20,
            layer="A-TEXT",
        )
        room_labels = []

    return PresentationModel(
        skeleton=skeleton,
        external_walls=ext_walls,
        core_walls=core_walls,
        partition_lines=partition_lines,
        rooms=rooms,
        doors=doors,
        title_block=title_block,
        room_labels=room_labels,
        used_fallback_walls=used_fallback_walls,
        used_fallback_rooms=used_fallback_rooms,
        used_fallback_doors=used_fallback_doors,
    )
