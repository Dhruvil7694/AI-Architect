"""
surat_spatial_rules.py
-----------------------
Machine-enforceable Surat residential planning norms.

These are not strings or comments — they are structured constraint objects
consumed by layout_engine.py (Subsystem C: Constraint Validator) and by
the prompt compiler to generate directional, positional natural language.

Surat Entry Norm (canonical):
  Main entrance → Living Hall (first, largest front room)
  → Powder Room adjacent at entry wall
  → Dining (behind living, same axis)
  → Kitchen (behind dining, rear, ventilated)
  → Central Passage (spine from dining zone to rear)
  → All Bedrooms via passage ONLY (no direct access from living/dining)
  → Master Bedroom at far rear with attached bath

Coordinate convention (used throughout layout_engine.py):
  Origin (0, 0) = bottom-left of unit (entry side)
  +Y = depth direction toward rear of unit
  +X = width direction (left to right facing unit)
  Normalised: (0.0–1.0) in both axes where 1.0 = full unit dimension
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Room constraint objects
# ---------------------------------------------------------------------------

@dataclass
class RoomConstraint:
    """Spatial constraint for a single room type."""
    zone: str                        # "front" | "middle" | "rear"
    direction: Optional[str]         # "north"=toward rear, "south"=toward entry
    relative_to: Optional[str]       # room name this is positioned relative to
    alignment: Optional[str]         # "same_axis" | "side_wall" | "flush"
    shared_edge_with: Optional[str]  # room name that shares a full wall
    touches_external_wall: bool
    min_width_fraction: float        # fraction of unit width (0.0–1.0)
    accessed_via: Optional[str]      # "passage" | "living" | None (direct from entry)
    max_distance_from_entry_m: Optional[float]  # metres; enforced for powder_room


@dataclass
class PassageConstraint:
    """Passage is a topological constraint, not a room."""
    type: str                        # "linear_spine"
    orientation: str                 # "depth_axis" | "width_axis" | "L_shape"
    min_width_m: float
    connects: List[str]              # room names passage must connect
    no_direct_access_from: List[str] # rooms that must NOT open to these
    zone: str                        # "middle_to_rear"
    normalised_x: float              # centred at this normalised x position


@dataclass
class ProhibitedEdge:
    """A direct room-to-room connection that must NOT exist."""
    room_a: str
    room_b: str
    reason: str


# ---------------------------------------------------------------------------
# Canonical Surat rules
# ---------------------------------------------------------------------------

SURAT_ROOM_CONSTRAINTS: Dict[str, RoomConstraint] = {

    "living": RoomConstraint(
        zone="front",
        direction="north",                 # first room going north from entry
        relative_to="entry",
        alignment=None,
        shared_edge_with=None,
        touches_external_wall=True,
        min_width_fraction=0.7,            # living spans ≥70% of unit width (visual density)
        accessed_via=None,                 # direct from entry
        max_distance_from_entry_m=None,
    ),

    "powder_room": RoomConstraint(
        zone="front",
        direction=None,
        relative_to="living",
        alignment="side_wall",             # tucked at side of entry wall
        shared_edge_with=None,
        touches_external_wall=False,
        min_width_fraction=0.0,
        accessed_via="living",
        max_distance_from_entry_m=2.5,     # must be close to entry
    ),

    "dining": RoomConstraint(
        zone="middle",
        direction="north",                 # directly behind living
        relative_to="living",
        alignment="same_axis",             # centred on same width axis as living
        shared_edge_with="living",         # full shared wall between living and dining
        touches_external_wall=False,
        min_width_fraction=0.0,
        accessed_via=None,                 # open connection from living
        max_distance_from_entry_m=None,
    ),

    "kitchen": RoomConstraint(
        zone="rear",
        direction="north",
        relative_to="dining",
        alignment="same_axis",
        shared_edge_with="dining",         # flush behind dining
        touches_external_wall=True,        # ventilation requirement
        min_width_fraction=0.0,
        accessed_via=None,
        max_distance_from_entry_m=None,
    ),

    "utility": RoomConstraint(
        zone="rear",
        direction="north",
        relative_to="kitchen",
        alignment="flush",                 # beside or behind kitchen
        shared_edge_with="kitchen",
        touches_external_wall=True,        # service access
        min_width_fraction=0.0,
        accessed_via=None,
        max_distance_from_entry_m=None,
    ),

    "master_bed": RoomConstraint(
        zone="rear",
        direction="north",
        relative_to="passage",
        alignment="side_wall",
        shared_edge_with=None,
        touches_external_wall=True,
        min_width_fraction=0.0,
        accessed_via="passage",            # ONLY via passage
        max_distance_from_entry_m=None,
    ),

    "bed_2": RoomConstraint(
        zone="rear",
        direction=None,
        relative_to="passage",
        alignment="side_wall",
        shared_edge_with=None,
        touches_external_wall=True,
        min_width_fraction=0.0,
        accessed_via="passage",
        max_distance_from_entry_m=None,
    ),

    "bed_3": RoomConstraint(
        zone="rear",
        direction=None,
        relative_to="passage",
        alignment="side_wall",
        shared_edge_with=None,
        touches_external_wall=True,
        min_width_fraction=0.0,
        accessed_via="passage",
        max_distance_from_entry_m=None,
    ),

    "bed_4": RoomConstraint(
        zone="rear",
        direction=None,
        relative_to="passage",
        alignment="side_wall",
        shared_edge_with=None,
        touches_external_wall=True,
        min_width_fraction=0.0,
        accessed_via="passage",
        max_distance_from_entry_m=None,
    ),
}

SURAT_PASSAGE: PassageConstraint = PassageConstraint(
    type="linear_spine",
    orientation="depth_axis",
    min_width_m=1.2,
    connects=["dining", "master_bed", "bed_2", "bed_3", "bed_4"],
    no_direct_access_from=["living", "dining"],  # bedrooms cannot open directly here
    zone="middle_to_rear",
    normalised_x=0.5,                    # centred on unit width
)

SURAT_PROHIBITED_EDGES: List[ProhibitedEdge] = [
    ProhibitedEdge("master_bed", "living", "Private bedroom must not open to living room"),
    ProhibitedEdge("bed_2",      "living", "Private bedroom must not open to living room"),
    ProhibitedEdge("bed_3",      "living", "Private bedroom must not open to living room"),
    ProhibitedEdge("bed_4",      "living", "Private bedroom must not open to living room"),
    ProhibitedEdge("master_bed", "dining", "Bedroom must not open directly to dining"),
    ProhibitedEdge("bed_2",      "dining", "Bedroom must not open directly to dining"),
    ProhibitedEdge("bed_3",      "dining", "Bedroom must not open directly to dining"),
    ProhibitedEdge("kitchen",    "living", "Kitchen must not open directly to living room"),
]

# ---------------------------------------------------------------------------
# Band depth fractions (normalised Y axis)
# front band:  y=0.00–0.30  (entry + living + powder room)
# middle band: y=0.30–0.60  (dining + passage + kitchen)
# rear band:   y=0.60–1.00  (bedrooms + utility + bathrooms)
# ---------------------------------------------------------------------------

BAND_FRACTIONS: Dict[str, Tuple[float, float]] = {
    "front":  (0.00, 0.30),
    "middle": (0.30, 0.60),
    "rear":   (0.60, 1.00),
}

# Normalised Y centre positions for prompt compiler
ZONE_CENTRE_Y: Dict[str, float] = {
    "front":  0.15,
    "middle": 0.45,
    "rear":   0.80,
}
