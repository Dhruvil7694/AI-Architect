from __future__ import annotations

"""
detailed_layout package — Phase D deterministic detailing layer.

Converts FloorLayoutContract / BuildingLayoutContract into richer
detailing contracts (DetailedFloorLayoutContract / DetailedBuildingLayoutContract)
that contain walls, doors, windows, fixtures, furniture, grids, core details,
balconies, and annotations suitable for DXF export.
"""

from detailed_layout.config import DetailingConfig
from detailed_layout.models import (
    DetailedAnnotation,
    DetailedBalcony,
    DetailedBuildingLayoutContract,
    DetailedColumn,
    DetailedCore,
    DetailedDoor,
    DetailedFixture,
    DetailedFloorLayoutContract,
    DetailedFurniture,
    DetailedGridLine,
    DetailedRoomGeometry,
    DetailedStair,
    DetailedUnitGeometry,
    DetailedWall,
    DetailedWindow,
)

__all__ = [
    "DetailingConfig",
    "DetailedWall",
    "DetailedDoor",
    "DetailedWindow",
    "DetailedFixture",
    "DetailedFurniture",
    "DetailedGridLine",
    "DetailedColumn",
    "DetailedStair",
    "DetailedCore",
    "DetailedBalcony",
    "DetailedAnnotation",
    "DetailedRoomGeometry",
    "DetailedUnitGeometry",
    "DetailedFloorLayoutContract",
    "DetailedBuildingLayoutContract",
]

