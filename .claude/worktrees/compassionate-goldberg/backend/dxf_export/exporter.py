"""
dxf_export/exporter.py
-----------------------
Public API for the DXF Exporter module.

Entry-point functions:

    export_floor_skeleton_to_dxf(floor_skeleton, output_path)
    export_layout_to_dxf(floor_layout_contract, output_path, preset_name)  # Phase A

This is a pure function — no database writes, no Shapely mutation, no global
state.  It raises ValueError for invalid inputs and OSError (from ezdxf) if
the output path is not writable.

Pipeline
--------
1. Guard checks (raise ValueError on invalid input)
2. Create DXF R2010 document
3. Set document units to metres ($INSUNITS = 4)
4. Create layers (setup_layers)
5. Register text style (ensure_text_style)
6. Get modelspace
7. Write geometry (write_floor_skeleton_geometry)
8. Write annotation (write_summary_text)
9. Save file (doc.saveas)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import ezdxf

from floor_skeleton.models import NO_SKELETON_PATTERN, FloorSkeleton

from dxf_export.layers import setup_layers
from dxf_export.styles import ensure_text_style
from dxf_export.geometry_writer import (
    write_floor_skeleton_geometry,
    write_floor_layout_geometry,
)
from dxf_export.annotation_writer import write_summary_text, write_layout_annotation
from detailed_layout.config import DetailingConfig
from detailed_layout.service import detail_floor_layout
from detailed_layout.dxf_adapter import write_detailed_floor

if TYPE_CHECKING:
    from residential_layout.floor_aggregation import FloorLayoutContract

# Sentinel values that indicate an unusable skeleton
_INVALID_PATTERNS = {NO_SKELETON_PATTERN, "NONE", ""}


def export_floor_skeleton_to_dxf(
    floor_skeleton: FloorSkeleton,
    output_path: str,
) -> None:
    """
    Export *floor_skeleton* to a layered DXF R2010 file at *output_path*.

    Guard checks
    ------------
    Raises ValueError if:
    - floor_skeleton.is_geometry_valid is False
    - floor_skeleton.pattern_used is NO_SKELETON / "NONE" / empty string

    Layer inventory
    ---------------
    A_FOOTPRINT  — outer footprint boundary
    A_CORE       — core strip polygon
    A_CORRIDOR   — corridor strip polygon (omitted when None)
    A_UNITS      — unit zone polygons (one entity per zone)
    A_TEXT       — five-line summary annotation
    A_AUDIT      — reserved, no entities written in POC v1

    Coordinate system
    -----------------
    Local metres frame from FloorSkeleton — no site-frame back-transformation.
    $INSUNITS header set to 4 (metres) for AutoCAD unit display.

    Parameters
    ----------
    floor_skeleton : Validated FloorSkeleton instance.
    output_path    : Absolute or relative path for the output .dxf file.
                     Raises OSError if path is not writable.
    """
    # ── Guard checks ──────────────────────────────────────────────────────────
    if not floor_skeleton.is_geometry_valid:
        raise ValueError(
            "FloorSkeleton.is_geometry_valid is False — cannot export. "
            "Audit log: " + str(floor_skeleton.audit_log)
        )

    if floor_skeleton.pattern_used in _INVALID_PATTERNS:
        raise ValueError(
            f"FloorSkeleton.pattern_used is {floor_skeleton.pattern_used!r} — "
            "cannot export a skeleton with no valid pattern."
        )

    # ── Create document ───────────────────────────────────────────────────────
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4          # metres

    # ── Setup layers and text style ───────────────────────────────────────────
    setup_layers(doc)
    ensure_text_style(doc)

    # ── Write geometry and annotation ─────────────────────────────────────────
    msp = doc.modelspace()
    write_floor_skeleton_geometry(msp, floor_skeleton)
    write_summary_text(msp, floor_skeleton)

    # ── Save ──────────────────────────────────────────────────────────────────
    doc.saveas(output_path)


def export_layout_to_dxf(
    floor_layout_contract: "FloorLayoutContract",
    output_path: str,
    preset_name: str,
) -> None:
    """
    Phase D: export detailed layout DXF from a FloorLayoutContract.

    The input contract is read-only; Phase D derives a DetailedFloorLayoutContract
    and writes walls, doors, windows, fixtures, furniture, core/stair, balconies,
    and annotations to DXF.
    """
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    setup_layers(doc)
    ensure_text_style(doc)
    msp = doc.modelspace()

    detailed = detail_floor_layout(floor_layout_contract, DetailingConfig())
    write_detailed_floor(msp, detailed)
    # Keep minimal layout-level annotation with preset name
    write_layout_annotation(msp, floor_layout_contract, preset_name)

    doc.saveas(output_path)
