"""
detailed_layout/diagnostics.py — Phase D geometry diagnostics.

Utilities to:
- Compute aggregate counts of detailed elements.
- Check for obvious overlaps (fixtures/furniture vs room and each other).

These are intended for debugging and tests before wiring DXF export.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from shapely.geometry import Polygon

from detailed_layout.models import DetailedFloorLayoutContract


@dataclass
class FloorDiagnostics:
    total_walls: int
    total_doors: int
    total_windows: int
    total_fixtures: int
    total_furniture: int


def compute_counts(detailed_floor: DetailedFloorLayoutContract) -> FloorDiagnostics:
    walls = doors = windows = fixtures = furniture = 0
    for unit in detailed_floor.units.values():
        for room in unit.rooms.values():
            walls += len(room.walls_ext) + len(room.walls_int)
            doors += len(room.doors)
            windows += len(room.windows)
            fixtures += len(room.fixtures)
            furniture += len(room.furniture)
    return FloorDiagnostics(
        total_walls=walls,
        total_doors=doors,
        total_windows=windows,
        total_fixtures=fixtures,
        total_furniture=furniture,
    )


def check_overlaps(
    detailed_floor: DetailedFloorLayoutContract,
    tol: float = 1e-4,
) -> List[str]:
    """
    Conservative overlap checks focused on presentation elements:
    - Fixtures and furniture must lie inside their room footprint.
    - Furniture vs furniture: no positive-area intersection.
    """
    issues: List[str] = []

    for unit in detailed_floor.units.values():
        for room in unit.rooms.values():
            fp: Polygon = room.footprint

            # Containment
            for fx in room.fixtures:
                if not fx.outline.buffer(tol).within(fp.buffer(tol)):
                    issues.append(f"Fixture outside room footprint in {room.room_id}")
            for furn in room.furniture:
                if not furn.outline.buffer(tol).within(fp.buffer(tol)):
                    issues.append(f"Furniture outside room footprint in {room.room_id}")

            # Pairwise furniture overlaps only (fixtures may overlap counters, etc.)
            for i, furn in enumerate(room.furniture):
                for j in range(i + 1, len(room.furniture)):
                    other = room.furniture[j]
                    if furn.outline.intersection(other.outline).area > tol:
                        issues.append(f"Furniture/furniture overlap in {room.room_id}")

    return issues

