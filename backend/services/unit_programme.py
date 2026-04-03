"""
unit_programme.py
-----------------
Layer 1 of the Surat floor plan prompt system.

Computes net usable area per unit from GDCR-derived tower footprint data,
then derives a room programme (room list + dimensions) based on unit type
and market segment.

The room programme feeds directly into the layout engine (layout_engine.py),
which converts it into a spatial graph for Recraft prompt compilation.

All areas in square metres. All dimensions in metres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math


# ---------------------------------------------------------------------------
# Efficiency factors by segment (carpet area / net usable area per unit)
# ---------------------------------------------------------------------------

EFFICIENCY: Dict[str, float] = {
    "Budget": 0.60,
    "Mid": 0.62,
    "Premium": 0.65,
    "Luxury": 0.68,
}

# Default passage width used for corridor_area deduction (metres)
_PASSAGE_WIDTH_M = 1.2

# Minimum room dimensions (metres) — hard lower bounds regardless of area
_MIN_ROOM_DIM: Dict[str, tuple] = {
    "living":        (3.6, 3.0),
    "dining":        (2.8, 2.4),
    "kitchen":       (2.4, 2.0),
    "utility":       (1.5, 1.2),
    "powder_room":   (1.2, 0.9),
    "master_bed":    (3.2, 3.0),
    "bed":           (2.8, 2.4),
    "bathroom":      (1.5, 1.2),
    "passage":       (1.2, 1.2),
}

# ---------------------------------------------------------------------------
# Room allocation ratios by unit type (% of carpet area)
# Rows must sum to ~100%. Passage/foyer is common circulation, not a room.
# ---------------------------------------------------------------------------

_ROOM_RATIOS: Dict[str, Dict[str, float]] = {
    "1BHK": {
        "living":      0.22,
        "kitchen":     0.14,
        "utility":     0.05,
        "powder_room": 0.03,
        "master_bed":  0.22,
        "bathroom_1":  0.10,
        "passage":     0.09,
        # 1BHK: no separate dining; remaining 0.15 allocated to living enlargement
        "_living_bonus": 0.15,
    },
    "2BHK": {
        "living":      0.20,
        "dining":      0.12,
        "kitchen":     0.12,
        "utility":     0.04,
        "powder_room": 0.03,
        "master_bed":  0.20,
        "bed_2":       0.16,
        "bathroom_1":  0.06,
        "bathroom_2":  0.04,
        "passage":     0.07,
        # remaining 0.02 → rounding
        "_living_bonus": 0.02,
    },
    "3BHK": {
        "living":      0.18,
        "dining":      0.11,
        "kitchen":     0.10,
        "utility":     0.03,
        "powder_room": 0.02,
        "master_bed":  0.17,
        "bed_2":       0.13,
        "bed_3":       0.11,
        "bathroom_1":  0.05,
        "bathroom_2":  0.03,
        "bathroom_3":  0.03,
        "passage":     0.07,
        "_living_bonus": 0.02,
    },
    "4BHK": {
        "living":      0.16,
        "dining":      0.10,
        "kitchen":     0.09,
        "utility":     0.03,
        "powder_room": 0.02,
        "master_bed":  0.15,
        "bed_2":       0.12,
        "bed_3":       0.10,
        "bed_4":       0.09,
        "bathroom_1":  0.04,
        "bathroom_2":  0.03,
        "bathroom_3":  0.03,
        "bathroom_4":  0.02,
        "passage":     0.06,
        "_living_bonus": 0.02,
    },
}

# Segment multiplier on carpet area (Luxury rooms are proportionally larger)
# This is applied on top of the base efficiency factor.
_SEGMENT_AREA_MULT: Dict[str, float] = {
    "Budget": 0.82,
    "Mid": 0.92,
    "Premium": 1.00,
    "Luxury": 1.12,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RoomSpec:
    """Single room in the programme with spatial zone hint."""
    name: str          # e.g. "living", "master_bed", "bed_2"
    area_sqm: float
    width_m: float
    depth_m: float
    zone: str          # "front" | "middle" | "rear"
    touches_external: bool = False
    is_passage: bool = False


@dataclass
class RoomProgramme:
    """Full room programme for one unit."""
    unit_type: str           # "1BHK" | "2BHK" | "3BHK" | "4BHK"
    segment: str             # "Budget" | "Mid" | "Premium" | "Luxury"
    carpet_area_sqm: float
    rooms: List[RoomSpec] = field(default_factory=list)

    def get(self, name: str) -> Optional[RoomSpec]:
        return next((r for r in self.rooms if r.name == name), None)

    def by_zone(self, zone: str) -> List[RoomSpec]:
        return [r for r in self.rooms if r.zone == zone]


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_net_usable(
    tower_footprint_sqm: float,
    core_area_sqm: float,
    units_per_core: int,
    floor_plate_depth_m: float,
    passage_width_m: float = _PASSAGE_WIDTH_M,
) -> float:
    """
    Net floor area available to residential units on one floor.

    Deducts:
      - core_area_sqm:     lift shaft + fire stairs (from core_fit.py)
      - corridor_area_sqm: public corridor running full plate depth

    Returns net usable sqm to be split across units_per_core.
    """
    corridor_area_sqm = passage_width_m * floor_plate_depth_m
    net = tower_footprint_sqm - core_area_sqm - corridor_area_sqm
    return max(net, 0.0)


def _area_to_dims(area_sqm: float, room_name: str, aspect_hint: float = 1.4) -> tuple:
    """
    Convert area to (width, depth) with a preferred aspect ratio.
    Falls back to minimum dims if area is too small.
    """
    min_w, min_d = _MIN_ROOM_DIM.get(room_name.split("_")[0], (1.2, 1.2))

    # width = sqrt(area * aspect_hint), depth = area / width
    w = math.sqrt(area_sqm * aspect_hint)
    d = area_sqm / max(w, 0.01)

    # enforce minimums
    w = max(w, min_w)
    d = max(d, min_d)

    return round(w, 2), round(d, 2)


def _zone_for_room(room_name: str) -> str:
    """Assign Surat spatial zone based on room name."""
    front = {"living", "powder_room", "foyer"}
    rear = {"kitchen", "utility", "master_bed", "bed_2", "bed_3", "bed_4",
            "bathroom_1", "bathroom_2", "bathroom_3", "bathroom_4"}
    if room_name in front:
        return "front"
    if room_name in rear:
        return "rear"
    return "middle"  # dining, passage


def _touches_external(room_name: str) -> bool:
    """Rooms that must touch an external wall per Surat norms."""
    return room_name in {
        "living", "kitchen", "utility",
        "master_bed", "bed_2", "bed_3", "bed_4",
    }


def derive_room_programme(
    unit_type: str,
    segment: str,
    net_usable_sqm: float,
    units_per_core: int,
) -> RoomProgramme:
    """
    Derive the full room programme for one unit.

    Args:
        unit_type:       "1BHK" | "2BHK" | "3BHK" | "4BHK"
        segment:         "Budget" | "Mid" | "Premium" | "Luxury"
        net_usable_sqm:  result of compute_net_usable()
        units_per_core:  number of units sharing this floor plate

    Returns:
        RoomProgramme with sized rooms ready for layout_engine.
    """
    unit_type = unit_type.upper()
    segment = segment.capitalize()

    if unit_type not in _ROOM_RATIOS:
        raise ValueError(f"Unknown unit_type: {unit_type!r}. Expected 1BHK/2BHK/3BHK/4BHK.")
    if segment not in EFFICIENCY:
        raise ValueError(f"Unknown segment: {segment!r}. Expected Budget/Mid/Premium/Luxury.")

    # Carpet area per unit
    efficiency = EFFICIENCY[segment]
    area_mult = _SEGMENT_AREA_MULT[segment]
    carpet_area = (net_usable_sqm / max(units_per_core, 1)) * efficiency * area_mult

    ratios = _ROOM_RATIOS[unit_type]
    living_bonus = ratios.get("_living_bonus", 0.0)

    rooms: List[RoomSpec] = []
    for room_name, ratio in ratios.items():
        if room_name.startswith("_"):
            continue

        room_area = carpet_area * ratio

        # Apply living bonus (absorbed dining in compact units)
        if room_name == "living":
            room_area += carpet_area * living_bonus

        # Aspect ratio hints per room type
        aspect = {
            "living": 1.3,
            "dining": 1.5,
            "kitchen": 1.8,
            "master_bed": 1.2,
            "bed": 1.15,
            "bathroom": 1.4,
            "utility": 1.5,
            "powder_room": 1.3,
            "passage": 6.0,
        }.get(room_name.split("_")[0], 1.4)

        w, d = _area_to_dims(room_area, room_name, aspect_hint=aspect)

        rooms.append(RoomSpec(
            name=room_name,
            area_sqm=round(room_area, 2),
            width_m=w,
            depth_m=d,
            zone=_zone_for_room(room_name),
            touches_external=_touches_external(room_name),
            is_passage=(room_name == "passage"),
        ))

    return RoomProgramme(
        unit_type=unit_type,
        segment=segment,
        carpet_area_sqm=round(carpet_area, 2),
        rooms=rooms,
    )
