"""
dxf_export/annotation_writer.py
---------------------------------
Builds and places a summary MTEXT annotation block for a FloorSkeleton.

The annotation is a five-line block placed at the top-left corner of the
footprint polygon (0.1 m inset), written to layer A_TEXT using the
ARCH_STANDARD text style.

Text box width is computed dynamically:
    text_width = min(5.0, footprint_width * 0.8)

This ensures the annotation never overflows the footprint boundary on narrow
slabs while capping the width at 5 m on wide slabs.

Public functions
----------------
    build_mtext_content(floor_skeleton)  → str
    write_summary_text(msp, floor_skeleton)
    write_layout_annotation(msp, floor_layout_contract, preset_name)  # Phase A
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ezdxf
    from floor_skeleton.models import FloorSkeleton
    from residential_layout.floor_aggregation import FloorLayoutContract

# MTEXT newline escape sequence
_NL = r"\P"

# Maximum text box width (metres)
_MAX_TEXT_WIDTH = 5.0

# Fractional width relative to footprint (before cap)
_TEXT_WIDTH_FRACTION = 0.8

# Text inset from footprint corner (metres)
_INSET = 0.1


def build_mtext_content(floor_skeleton: "FloorSkeleton") -> str:
    """
    Build the MTEXT string for the skeleton summary annotation.

    Lines
    -----
    Pattern:    {pattern_used}
    Placement:  {placement_label}
    Efficiency: {efficiency_ratio * 100:.1f} %
    Unit Area:  {unit_area_sqm:.2f} sqm
    Core Area:  {core_area_sqm:.2f} sqm

    Lines are joined with \\P (the MTEXT paragraph separator).

    Parameters
    ----------
    floor_skeleton : FloorSkeleton instance.

    Returns
    -------
    str — ready to pass directly to msp.add_mtext().
    """
    summary = floor_skeleton.area_summary
    unit_area = summary.get("unit_area_sqm", 0.0)
    core_area = summary.get("core_area_sqm", 0.0)
    efficiency_pct = floor_skeleton.efficiency_ratio * 100.0

    lines = [
        f"Pattern:    {floor_skeleton.pattern_used}",
        f"Placement:  {floor_skeleton.placement_label}",
        f"Efficiency: {efficiency_pct:.1f} %",
        f"Unit Area:  {unit_area:.2f} sqm",
        f"Core Area:  {core_area:.2f} sqm",
    ]
    return _NL.join(lines)


def _get_annotation_origin(floor_skeleton: "FloorSkeleton") -> tuple[float, float]:
    """
    Return the MTEXT insertion point: top-left corner of footprint, 0.1 m inset.

    Parameters
    ----------
    floor_skeleton : FloorSkeleton instance.

    Returns
    -------
    (x, y) tuple in local metres frame.
    """
    minx, _miny, _maxx, maxy = floor_skeleton.footprint_polygon.bounds
    return (minx + _INSET, maxy - _INSET)


def write_summary_text(
    msp: "ezdxf.layouts.Modelspace",
    floor_skeleton: "FloorSkeleton",
) -> None:
    """
    Place a five-line MTEXT summary block on layer A_TEXT.

    Dynamic text box width
    ----------------------
    text_width = min(5.0, footprint_width * 0.8)

    This prevents the annotation overflowing the footprint on narrow slabs
    (e.g. a 4 m-wide slab gets a 3.2 m box) while capping spread on wide slabs.
    No custom text-wrapping logic is introduced; ezdxf soft-wraps within the box.

    Parameters
    ----------
    msp            : ezdxf modelspace object.
    floor_skeleton : FloorSkeleton instance.
    """
    origin  = _get_annotation_origin(floor_skeleton)
    content = build_mtext_content(floor_skeleton)

    # Dynamic text box width
    minx, _miny, maxx, _maxy = floor_skeleton.footprint_polygon.bounds
    footprint_width = maxx - minx
    text_width = min(_MAX_TEXT_WIDTH, footprint_width * _TEXT_WIDTH_FRACTION)

    msp.add_mtext(
        content,
        dxfattribs={
            "layer":            "A_TEXT",
            "char_height":       0.25,
            "style":            "ARCH_STANDARD",
            "insert":            origin,
            "attachment_point":  1,          # top-left attachment
            "width":             text_width,
        },
    )


def write_layout_annotation(
    msp: "ezdxf.layouts.Modelspace",
    floor_layout_contract: "FloorLayoutContract",
    preset_name: str,
) -> None:
    """
    Phase A: minimal annotation for layout-level DXF (best preset).
    Single line at footprint top-left; no skeleton dependency.
    """
    fp = floor_layout_contract.footprint_polygon
    minx, _miny, maxx, maxy = fp.bounds
    origin = (minx + _INSET, maxy - _INSET)
    content = f"Layout (best preset: {preset_name})"
    width = min(_MAX_TEXT_WIDTH, (maxx - minx) * _TEXT_WIDTH_FRACTION)
    msp.add_mtext(
        content,
        dxfattribs={
            "layer": "A_TEXT",
            "char_height": 0.25,
            "style": "ARCH_STANDARD",
            "insert": origin,
            "attachment_point": 1,
            "width": width,
        },
    )
