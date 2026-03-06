"""
dxf_export/geometry_writer.py
------------------------------
Converts Shapely Polygon objects from a FloorSkeleton into DXF LWPOLYLINE
entities written to the supplied modelspace object.

All geometry is in the local metres frame produced by the floor_skeleton
module — no scaling, rotation, or translation is applied.

Public functions
----------------
    write_polygon(msp, polygon, layer_name)
    write_floor_skeleton_geometry(msp, floor_skeleton)
    write_floor_layout_geometry(msp, floor_layout_contract)  # Phase A: layout from contract
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shapely.geometry import Polygon

if TYPE_CHECKING:
    import ezdxf
    from floor_skeleton.models import FloorSkeleton
    from residential_layout.floor_aggregation import FloorLayoutContract


def write_polygon(
    msp: "ezdxf.layouts.Modelspace",
    polygon: Polygon | None,
    layer_name: str,
) -> None:
    """
    Write a single Shapely polygon as a closed DXF LWPOLYLINE.

    Defensive guards (applied before writing)
    -----------------------------------------
    1. None check      — returns silently; protects against optional polygons.
    2. is_valid check  — raises ValueError with Shapely's validity explanation.
    3. Zero-area check — returns silently; skips degenerate (line/point) polygons.

    Coordinate precision
    --------------------
    All (x, y) values are rounded to 6 decimal places (~1 micrometre) before
    being written.  This eliminates Shapely floating-point noise such as
    7.390000000000002 without losing any architecturally meaningful precision.

    Closure handling
    ----------------
    Shapely's exterior.coords repeats the first vertex to close the ring.
    ezdxf's add_lwpolyline(..., closed=True) adds its own closure, so the
    duplicate trailing vertex is stripped to avoid a double-vertex artifact
    in the DXF entity.

    Interior rings (polygon holes) are intentionally ignored in POC v1.

    Parameters
    ----------
    msp        : ezdxf modelspace object.
    polygon    : Shapely Polygon, or None (skipped silently).
    layer_name : Target DXF layer name (must already exist in the document).
    """
    # Guard 1 — None
    if polygon is None:
        return

    # Guard 2 — invalid geometry
    if not polygon.is_valid:
        raise ValueError(
            f"Invalid polygon passed to write_polygon (layer={layer_name!r}): "
            f"{polygon.explain_validity()}"
        )

    # Guard 3 — zero or negative area (degenerate polygon)
    if polygon.area <= 0:
        return

    # Round coordinates to 6 decimal places; drop Z component if present
    raw_coords = list(polygon.exterior.coords)
    points = [
        (round(x, 6), round(y, 6))
        for x, y, *_ in raw_coords
    ]

    # Strip the duplicate closing vertex that Shapely adds
    if points and points[0] == points[-1]:
        points = points[:-1]

    # Write the closed polyline
    msp.add_lwpolyline(
        points,
        dxfattribs={"layer": layer_name, "closed": True},
    )


def write_floor_skeleton_geometry(
    msp: "ezdxf.layouts.Modelspace",
    floor_skeleton: "FloorSkeleton",
) -> None:
    """
    Write all geometric polygons from *floor_skeleton* to *msp*.

    Layer assignment
    ----------------
    footprint_polygon  → A_FOOTPRINT
    core_polygon       → A_CORE
    corridor_polygon   → A_CORRIDOR  (skipped if None)
    unit_zones[i]      → A_UNITS     (one entity per zone)

    Parameters
    ----------
    msp            : ezdxf modelspace object.
    floor_skeleton : FloorSkeleton instance (must pass is_geometry_valid).
    """
    write_polygon(msp, floor_skeleton.footprint_polygon, "A_FOOTPRINT")
    write_polygon(msp, floor_skeleton.core_polygon,      "A_CORE")

    if floor_skeleton.corridor_polygon is not None:
        write_polygon(msp, floor_skeleton.corridor_polygon, "A_CORRIDOR")

    for unit_zone in floor_skeleton.unit_zones:
        write_polygon(msp, unit_zone.polygon, "A_UNITS")


def write_floor_layout_geometry(
    msp: "ezdxf.layouts.Modelspace",
    floor_layout_contract: "FloorLayoutContract",
) -> None:
    """
    Write layout geometry from a FloorLayoutContract (Phase A).

    Same layer assignment as skeleton: A_FOOTPRINT, A_CORE, A_CORRIDOR, A_UNITS.
    Units are drawn from contract all_units (one polygon per room).
    No engine geometry mutation; read-only use of contract.
    """
    write_polygon(msp, floor_layout_contract.footprint_polygon, "A_FOOTPRINT")
    write_polygon(msp, floor_layout_contract.core_polygon, "A_CORE")
    if floor_layout_contract.corridor_polygon is not None:
        write_polygon(msp, floor_layout_contract.corridor_polygon, "A_CORRIDOR")
    for unit in floor_layout_contract.all_units:
        for room in unit.rooms:
            write_polygon(msp, room.polygon, "A_UNITS")
