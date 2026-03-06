"""
residential_layout/templates.py — UnitTemplate, RoomTemplate, built-in variants.

No dependence on repetition count or module_width.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Margin added to LIVING depth (frontage side). v1 use 0.0 for stability.
MARGIN_FRONTAGE_M = 0.0


@dataclass
class RoomTemplate:
    """Min dimensions and min area for one room type."""

    min_width_m: float
    min_depth_m: float
    min_area_sqm: Optional[float] = None


@dataclass
class UnitTemplate:
    """
    Template for one unit type. min_width_m / min_depth_m are required zone extents.

    room_templates: LIVING, BEDROOM, TOILET, KITCHEN (or LIVING, TOILET for STUDIO).
    door_width_m: length of entry_door_segment (e.g. 0.9 m).
    """

    name: str
    min_width_m: float
    min_depth_m: float
    room_templates: Dict[str, RoomTemplate] = field(default_factory=dict)
    door_width_m: float = 0.9

    def room(self, room_type: str) -> RoomTemplate:
        """Get room template by type. Raises KeyError if missing."""
        return self.room_templates[room_type]

    def room_order(self) -> List[str]:
        """Order of room types for slicing. 1BHK: LIVING, BEDROOM, TOILET, KITCHEN; STUDIO: LIVING, TOILET."""
        if "BEDROOM" in self.room_templates:
            return ["LIVING", "BEDROOM", "TOILET", "KITCHEN"]
        return ["LIVING", "TOILET"]


def _required_depth(t: UnitTemplate) -> float:
    """required_depth = d_living + d_bed + d_back_strip."""
    d_living = t.room("LIVING").min_depth_m + MARGIN_FRONTAGE_M
    if "BEDROOM" in t.room_templates:
        d_bed = t.room("BEDROOM").min_depth_m
        d_back = max(
            t.room("TOILET").min_depth_m,
            t.room("KITCHEN").min_depth_m,
        )
        return d_living + d_bed + d_back
    # STUDIO
    return d_living + t.room("TOILET").min_depth_m


def _required_width(t: UnitTemplate) -> float:
    """max(living.min_width_m, bedroom.min_width_m, w_toilet + w_kitchen) for 1BHK."""
    living_w = t.room("LIVING").min_width_m
    if "BEDROOM" in t.room_templates:
        bed_w = t.room("BEDROOM").min_width_m
        wet_w = t.room("TOILET").min_width_m + t.room("KITCHEN").min_width_m
        return max(living_w, bed_w, wet_w)
    return max(living_w, t.room("TOILET").min_width_m)


# ── Built-in templates (stability first; no optimization) ────────────────────

STANDARD_1BHK = UnitTemplate(
    name="STANDARD_1BHK",
    min_width_m=3.6,
    min_depth_m=8.0,
    door_width_m=0.9,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=3.6, min_depth_m=3.0, min_area_sqm=10.0),
        "BEDROOM": RoomTemplate(min_width_m=3.0, min_depth_m=3.0, min_area_sqm=8.0),
        "TOILET": RoomTemplate(min_width_m=1.5, min_depth_m=2.0, min_area_sqm=2.5),
        "KITCHEN": RoomTemplate(min_width_m=2.0, min_depth_m=1.5, min_area_sqm=2.5),
    },
)

COMPACT_1BHK = UnitTemplate(
    name="COMPACT_1BHK",
    min_width_m=3.0,
    min_depth_m=6.8,
    door_width_m=0.9,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=3.0, min_depth_m=2.5, min_area_sqm=6.0),
        "BEDROOM": RoomTemplate(min_width_m=2.8, min_depth_m=2.5, min_area_sqm=6.0),
        "TOILET": RoomTemplate(min_width_m=1.2, min_depth_m=1.8, min_area_sqm=1.8),
        "KITCHEN": RoomTemplate(min_width_m=1.8, min_depth_m=1.2, min_area_sqm=1.8),
    },
)

STUDIO = UnitTemplate(
    name="STUDIO",
    min_width_m=3.0,
    min_depth_m=4.3,
    door_width_m=0.9,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=3.0, min_depth_m=2.5, min_area_sqm=6.0),
        "TOILET": RoomTemplate(min_width_m=1.2, min_depth_m=1.8, min_area_sqm=1.8),
    },
)


# ── Extended multi-bedroom templates (2BHK–5BHK, v1 approximations) ─────────────
#
# These templates follow the same rectangular slicing pattern as STANDARD_1BHK:
#   - Single LIVING, BEDROOM, TOILET, KITCHEN room roles in the composer.
#   - Larger minimum depths/widths and areas to approximate higher BHK products.
# Composer semantics are unchanged; these templates simply demand larger zones.

STANDARD_2BHK = UnitTemplate(
    name="STANDARD_2BHK",
    min_width_m=6.0,
    min_depth_m=9.0,
    door_width_m=1.0,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=3.8, min_depth_m=3.2, min_area_sqm=12.0),
        "BEDROOM": RoomTemplate(min_width_m=3.2, min_depth_m=3.2, min_area_sqm=10.0),
        "TOILET": RoomTemplate(min_width_m=1.5, min_depth_m=2.0, min_area_sqm=3.0),
        "KITCHEN": RoomTemplate(min_width_m=2.4, min_depth_m=2.0, min_area_sqm=4.5),
    },
)

STANDARD_3BHK = UnitTemplate(
    name="STANDARD_3BHK",
    min_width_m=7.2,
    min_depth_m=10.0,
    door_width_m=1.0,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=4.0, min_depth_m=3.5, min_area_sqm=14.0),
        "BEDROOM": RoomTemplate(min_width_m=3.2, min_depth_m=3.4, min_area_sqm=11.0),
        "TOILET": RoomTemplate(min_width_m=1.6, min_depth_m=2.1, min_area_sqm=3.3),
        "KITCHEN": RoomTemplate(min_width_m=2.6, min_depth_m=2.1, min_area_sqm=5.0),
    },
)

STANDARD_4BHK = UnitTemplate(
    name="STANDARD_4BHK",
    min_width_m=8.0,
    min_depth_m=11.0,
    door_width_m=1.0,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=4.2, min_depth_m=3.8, min_area_sqm=16.0),
        "BEDROOM": RoomTemplate(min_width_m=3.4, min_depth_m=3.6, min_area_sqm=12.0),
        "TOILET": RoomTemplate(min_width_m=1.7, min_depth_m=2.2, min_area_sqm=3.6),
        "KITCHEN": RoomTemplate(min_width_m=2.8, min_depth_m=2.2, min_area_sqm=5.5),
    },
)

STANDARD_5BHK = UnitTemplate(
    name="STANDARD_5BHK",
    min_width_m=9.0,
    min_depth_m=12.0,
    door_width_m=1.1,
    room_templates={
        "LIVING": RoomTemplate(min_width_m=4.5, min_depth_m=4.0, min_area_sqm=18.0),
        "BEDROOM": RoomTemplate(min_width_m=3.6, min_depth_m=3.8, min_area_sqm=13.0),
        "TOILET": RoomTemplate(min_width_m=1.8, min_depth_m=2.3, min_area_sqm=3.8),
        "KITCHEN": RoomTemplate(min_width_m=3.0, min_depth_m=2.3, min_area_sqm=6.0),
    },
)


def get_unit_template(name: str) -> UnitTemplate:
    """Return built-in template by name. Raises KeyError if unknown."""
    _registry = {
        "STANDARD_1BHK": STANDARD_1BHK,
        "COMPACT_1BHK": COMPACT_1BHK,
        "STUDIO": STUDIO,
        "STANDARD_2BHK": STANDARD_2BHK,
        "STANDARD_3BHK": STANDARD_3BHK,
        "STANDARD_4BHK": STANDARD_4BHK,
        "STANDARD_5BHK": STANDARD_5BHK,
    }
    return _registry[name]
