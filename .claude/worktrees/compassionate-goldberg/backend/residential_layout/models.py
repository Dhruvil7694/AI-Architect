"""
residential_layout/models.py — UnitLayoutContract and RoomInstance.

Presentation and repetition depend only on this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from shapely.geometry import Polygon, LineString


@dataclass
class RoomInstance:
    """One room in a composed unit. v1: LIVING | BEDROOM | KITCHEN | TOILET only."""

    room_type: str  # LIVING | BEDROOM | KITCHEN | TOILET
    polygon: "Polygon"
    area_sqm: float


@dataclass
class UnitLayoutContract:
    """
    Output contract for Phase 2 composer. Presentation consumes only this.

    entry_door_segment: centred on LIVING–corridor (or frontage) shared edge, length = door_width_m.
    unit_id: None for single-unit call; set by repetition when present.
    """

    rooms: list[RoomInstance]
    entry_door_segment: "LineString"  # two-point segment on LIVING–corridor/frontage edge
    unit_id: Optional[str] = None
    resolved_template_name: Optional[str] = None  # set by orchestrator for batch metrics
