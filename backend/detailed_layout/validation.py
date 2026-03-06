"""
detailed_layout/validation.py — conservative geometry validation.

Checks basic invariants without attempting cross-room duplicate detection:
- Room footprints and wall polygons are valid and non-empty.
- Each room has non-zero total wall length.
"""

from __future__ import annotations

from detailed_layout.config import DetailingConfig
from detailed_layout.models import DetailedFloorLayoutContract


class DetailingValidationError(Exception):
    """Raised when Phase D detects an invariant violation in detailed geometry."""


def validate_detailed_floor(
    detailed_floor: DetailedFloorLayoutContract,
    config: DetailingConfig,
) -> None:
    tol = config.snap_tol_m

    for unit in detailed_floor.units.values():
        for room in unit.rooms.values():
            if not room.footprint.is_valid or room.footprint.area <= 0:
                raise DetailingValidationError(f"Invalid room footprint for {room.room_id}")
            total_len = 0.0
            for w in room.walls_ext + room.walls_int:
                if not w.polygon.is_valid or w.polygon.area <= 0:
                    raise DetailingValidationError(f"Invalid wall polygon in {room.room_id}")
                total_len += w.centerline.length
            if total_len <= 0:
                raise DetailingValidationError(
                    f"Room {room.room_id} has zero total wall length"
                )

