"""
detailed_layout/dxf_adapter.py — write DetailedFloorLayoutContract into a DXF modelspace.

This module does not create or save DXF documents; callers are responsible for
document lifecycle (creation, layers, styles, save). We only populate entities.
"""

from __future__ import annotations

from detailed_layout.models import DetailedFloorLayoutContract


def write_detailed_floor(
    msp,
    detailed_floor: DetailedFloorLayoutContract,
) -> None:
    """Write detailed floor geometry into the given modelspace."""
    # Walls
    for unit in detailed_floor.units.values():
        for room in unit.rooms.values():
            for w in room.walls_ext:
                _write_polygon(msp, w.polygon, "A-WALL-EXT")
            for w in room.walls_int:
                _write_polygon(msp, w.polygon, "A-WALL-INT")

            for d in room.doors:
                _write_linestring(msp, d.opening_segment, "A-DOOR")
                _write_polygon(msp, d.frame_polygon, "A-DOOR")
            for win in room.windows:
                _write_linestring(msp, win.opening_segment, "A-WINDOW")
                _write_polygon(msp, win.frame_polygon, "A-WINDOW")

            for fx in room.fixtures:
                _write_polygon(msp, fx.outline, "A-FIXTURE")
            for furn in room.furniture:
                _write_polygon(msp, furn.outline, "A-FURN")

            for ann in room.annotations:
                msp.add_text(
                    ann.text,
                    dxfattribs={
                        "layer": ann.layer,
                        "height": 0.25,
                        "insert": (ann.position.x, ann.position.y),
                    },
                )

    # Shared elements
    for stair in detailed_floor.stairs:
        _write_polygon(msp, stair.outline, "A-STAIR")
    for core in detailed_floor.cores:
        _write_polygon(msp, core.outline, "A-CORE")
        if core.hatch is not None:
            _write_polygon(msp, core.hatch, "A-HATCH-CORE")
    for balc in detailed_floor.balconies:
        _write_polygon(msp, balc.outline, "A-BALC")
    for ann in detailed_floor.annotations:
        msp.add_text(
            ann.text,
            dxfattribs={
                "layer": ann.layer,
                "height": 0.25,
                "insert": (ann.position.x, ann.position.y),
            },
        )


def _write_polygon(msp, poly, layer: str) -> None:
    if poly is None or poly.is_empty:
        return
    raw = list(poly.exterior.coords)
    pts = [(x, y) for x, y, *_ in raw]
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer, "closed": True})


def _write_linestring(msp, ls, layer: str) -> None:
    if ls is None or ls.is_empty:
        return
    pts = [(x, y) for x, y, *_ in ls.coords]
    if len(pts) < 2:
        return
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})

