"""
floor_skeleton
--------------
Floor Skeleton Generator — converts a rectangular building footprint and a
selected core pattern into deterministic zone polygons (core, corridor, unit
zones) using a five-candidate placement strategy and scored selection.

All geometry is produced in a local 2-D metres frame (origin at footprint
bottom-left, X = width axis, Y = depth axis) — independent of the DXF SRID=0
frame used by the upstream placement engine.

Public API
----------
    from floor_skeleton.services import generate_floor_skeleton
"""
