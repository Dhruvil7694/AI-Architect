"""
dxf_export
----------
Exports a single FloorSkeleton to a layered, AutoCAD-compatible DXF file.

This module is a pure-function pipeline — no Django ORM, no DB writes,
no Shapely mutation.  Input is a FloorSkeleton instance; output is a .dxf
file at the caller-supplied path.

Public API
----------
    from dxf_export.exporter import export_floor_skeleton_to_dxf
"""

from dxf_export.exporter import export_floor_skeleton_to_dxf

__all__ = ["export_floor_skeleton_to_dxf"]
