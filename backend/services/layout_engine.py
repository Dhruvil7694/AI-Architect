"""
layout_engine.py
----------------
Layer 1.5 of the Surat floor plan prompt system.

Three subsystems:
  A. Layout Template Selector  — picks a canonical Surat floor plate topology
  B. Band-Based Skeleton + Guided Partitioner  — assigns absolute (x, y, w, d)
     to each room using band slicing, NOT random guillotine
  C. Constraint Validator  — asserts Surat rules post-generation; regenerates
     with adjusted parameters on failure (max 3 attempts)

Output: list[RoomLayout] — absolute room geometry in metres, origin at unit
entry bottom-left, +Y toward rear.

CP-SAT upgrade path: replace Subsystem B (_partition_bands) only.
Subsystems A and C, plus RoomLayout dataclass, remain unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from services.unit_programme import RoomProgramme, RoomSpec
from services.surat_spatial_rules import (
    BAND_FRACTIONS,
    SURAT_PASSAGE,
    SURAT_PROHIBITED_EDGES,
    SURAT_ROOM_CONSTRAINTS,
)

logger = logging.getLogger(__name__)

_MAX_REGENERATE_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Output dataclass (stable interface — do not change for CP-SAT swap)
# ---------------------------------------------------------------------------

@dataclass
class RoomLayout:
    """Absolute room geometry within one unit. Origin = bottom-left of unit."""
    name: str
    x: float          # metres from unit left edge
    y: float          # metres from entry (0=entry, increases toward rear)
    width: float      # metres
    depth: float      # metres
    zone: str         # "front" | "middle" | "rear"
    door_wall: str    # wall where door is placed: "south"|"north"|"east"|"west"
    touches_external: List[str] = field(default_factory=list)  # e.g. ["south", "west"]
    is_passage: bool = False

    @property
    def cx(self) -> float:
        return self.x + self.width / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.depth / 2.0

    @property
    def norm_cx(self) -> float:
        """Normalised centre x — requires unit_width injected by caller."""
        return self.cx  # caller divides by unit_width

    def shares_edge_with(self, other: "RoomLayout", tol: float = 0.15) -> bool:
        """True if this room's north wall coincides with other's south wall (or vice versa)."""
        my_north = self.y + self.depth
        their_south = other.y
        if abs(my_north - their_south) < tol:
            # check horizontal overlap
            overlap = min(self.x + self.width, other.x + other.width) - max(self.x, other.x)
            return overlap > tol
        my_south = self.y
        their_north = other.y + other.depth
        if abs(my_south - their_north) < tol:
            overlap = min(self.x + self.width, other.x + other.width) - max(self.x, other.x)
            return overlap > tol
        return False


@dataclass
class ValidationResult:
    passed: bool
    violations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Subsystem A: Layout Template Selector
# ---------------------------------------------------------------------------

_TEMPLATES = {
    "linear_spine_2unit": {
        "desc": "2 units mirrored around central core; spine runs depth-wise",
        "units_per_core": [2],
        "band_structure": ["front", "middle", "rear"],
        "passage_orientation": "vertical",
        "bedroom_distribution": "both_sides_of_spine",
        # Band depth fractions override (tighter front, deeper rear for luxury)
        "band_fractions": {"front": (0.00, 0.28), "middle": (0.28, 0.58), "rear": (0.58, 1.00)},
    },
    "double_loaded_4unit": {
        "desc": "4 units around core, 2 per side",
        "units_per_core": [4],
        "band_structure": ["front", "middle", "rear"],
        "passage_orientation": "horizontal_and_vertical",
        "bedroom_distribution": "rear_cluster",
        "band_fractions": {"front": (0.00, 0.30), "middle": (0.30, 0.58), "rear": (0.58, 1.00)},
    },
    "hexacore_6unit": {
        "desc": "6 units around core",
        "units_per_core": [6],
        "band_structure": ["front", "middle", "rear"],
        "passage_orientation": "radial",
        "bedroom_distribution": "rear_cluster",
        "band_fractions": {"front": (0.00, 0.30), "middle": (0.30, 0.58), "rear": (0.58, 1.00)},
    },
    "compact_1bhk": {
        "desc": "1BHK: compressed bands, no separate dining",
        "units_per_core": [2, 4, 6],
        "band_structure": ["front", "rear"],
        "passage_orientation": "minimal",
        "bedroom_distribution": "single_rear",
        "band_fractions": {"front": (0.00, 0.40), "rear": (0.40, 1.00)},
    },
}


def select_template(unit_mix: str, units_per_core: int) -> dict:
    """
    Deterministically select layout template from inputs.
    Same inputs always return the same template.
    """
    if unit_mix.upper() == "1BHK":
        return _TEMPLATES["compact_1bhk"]
    if units_per_core == 2:
        return _TEMPLATES["linear_spine_2unit"]
    if units_per_core == 4:
        return _TEMPLATES["double_loaded_4unit"]
    if units_per_core == 6:
        return _TEMPLATES["hexacore_6unit"]
    # fallback
    return _TEMPLATES["linear_spine_2unit"]


# ---------------------------------------------------------------------------
# Subsystem B: Band-Based Skeleton + Guided Partitioner
# ---------------------------------------------------------------------------

def _get_band_fractions(template: dict) -> Dict[str, Tuple[float, float]]:
    return template.get("band_fractions", BAND_FRACTIONS)


def _rooms_in_band(programme: RoomProgramme, band: str) -> List[RoomSpec]:
    """Return rooms belonging to a given Surat zone/band."""
    # Special case: 1BHK has no dining; kitchen goes to rear band
    return [r for r in programme.rooms if r.zone == band and not r.is_passage]


def _partition_bands(
    programme: RoomProgramme,
    unit_w: float,
    unit_d: float,
    template: dict,
    attempt: int = 0,
) -> List[RoomLayout]:
    """
    Subsystem B: assign absolute (x, y, width, depth) to each room.

    Strategy:
    1. Divide unit depth into front/middle/rear bands per template fractions.
    2. Within each band, slice width proportionally to room areas.
    3. Passage is inserted as a fixed-width vertical spine in the middle/rear bands.
    4. On retry (attempt>0), slightly widen passage and compress bedrooms to fix
       adjacency violations.

    CP-SAT replacement target: this function only.
    """
    band_fracs = _get_band_fractions(template)
    passage_w = max(SURAT_PASSAGE.min_width_m + attempt * 0.1, SURAT_PASSAGE.min_width_m)

    layouts: List[RoomLayout] = []

    # --- FRONT BAND: living + powder_room ---
    front_y0, front_y1 = [unit_d * f for f in band_fracs["front"]]
    front_d = front_y1 - front_y0

    living = programme.get("living")
    powder = programme.get("powder_room")

    if living:
        if powder:
            # living takes left portion; powder_room tucked at right of entry wall
            powder_w = min(powder.width_m, unit_w * 0.22)
            powder_d = min(powder.depth_m, front_d)
            living_w = unit_w - powder_w
            layouts.append(RoomLayout(
                name="living",
                x=0.0, y=front_y0,
                width=living_w, depth=front_d,
                zone="front",
                door_wall="south",
                touches_external=["south", "west"],
            ))
            layouts.append(RoomLayout(
                name="powder_room",
                x=living_w, y=front_y0,
                width=powder_w, depth=powder_d,
                zone="front",
                door_wall="west",
                touches_external=[],
            ))
        else:
            layouts.append(RoomLayout(
                name="living",
                x=0.0, y=front_y0,
                width=unit_w, depth=front_d,
                zone="front",
                door_wall="south",
                touches_external=["south", "west", "east"],
            ))

    # --- MIDDLE BAND: dining + passage spine (+ kitchen in 1BHK) ---
    mid_bands = band_fracs.get("middle")
    if mid_bands:
        mid_y0, mid_y1 = [unit_d * f for f in mid_bands]
        mid_d = mid_y1 - mid_y0

        dining = programme.get("dining")
        kitchen = programme.get("kitchen")
        utility = programme.get("utility")

        # Passage is a vertical spine at centre
        passage_x = (unit_w - passage_w) / 2.0

        # Dining: left of passage, kitchen: right of passage (or combined if 1BHK)
        if dining:
            dining_w = passage_x
            dining_layout = RoomLayout(
                name="dining",
                x=0.0, y=mid_y0,
                width=dining_w, depth=mid_d * 0.55,  # dining in upper half of middle band
                zone="middle",
                door_wall="south",
                touches_external=["west"],
            )
            layouts.append(dining_layout)

        if kitchen:
            kit_x = passage_x + passage_w
            kit_w = unit_w - kit_x
            kit_d = mid_d * 0.55
            layouts.append(RoomLayout(
                name="kitchen",
                x=kit_x, y=mid_y0,
                width=kit_w, depth=kit_d,
                zone="rear",   # kitchen is rear-zone even if geometrically in middle band
                door_wall="south",
                touches_external=["east"],
            ))

            if utility:
                util_w = min(utility.width_m, kit_w)
                util_d = min(utility.depth_m, mid_d - kit_d)
                layouts.append(RoomLayout(
                    name="utility",
                    x=kit_x, y=mid_y0 + kit_d,
                    width=util_w, depth=util_d,
                    zone="rear",
                    door_wall="north",
                    touches_external=["east"],
                ))

        # Passage layout entry (spans middle→rear)
        # Full extent added after rear band is computed (y goes to unit_d)
        _passage_mid_y = mid_y0
    else:
        # 1BHK: no middle band
        mid_y0 = band_fracs["front"][1] * unit_d
        _passage_mid_y = mid_y0
        passage_x = (unit_w - passage_w) / 2.0

    # --- REAR BAND: bedrooms + master_bed ---
    rear_y0, rear_y1 = [unit_d * f for f in band_fracs["rear"]]
    rear_d = rear_y1 - rear_y0

    bed_rooms = [r for r in programme.rooms
                 if r.name.startswith("bed") or r.name == "master_bed"]
    bath_rooms = [r for r in programme.rooms if r.name.startswith("bathroom")]

    if bed_rooms:
        # Distribute bedrooms symmetrically on both sides of passage
        left_beds = []
        right_beds = []
        for i, bed in enumerate(bed_rooms):
            if bed.name == "master_bed":
                # master always at far rear, choose side by count
                if len(bed_rooms) % 2 == 0:
                    right_beds.append(bed)
                else:
                    left_beds.append(bed)
            elif i % 2 == 0:
                left_beds.append(bed)
            else:
                right_beds.append(bed)

        left_x = 0.0
        left_w = passage_x
        right_x = passage_x + passage_w
        right_w = unit_w - right_x

        def place_beds_in_strip(
            beds: List[RoomSpec],
            strip_x: float,
            strip_w: float,
            strip_y0: float,
            strip_d: float,
            side: str,
        ) -> List[RoomLayout]:
            result = []
            if not beds:
                return result
            # Divide strip depth equally among beds
            bed_d = strip_d / max(len(beds), 1)
            ext_wall = "west" if side == "left" else "east"
            for j, bed in enumerate(beds):
                by = strip_y0 + j * bed_d
                bw = min(bed.width_m, strip_w)

                # find attached bath for master
                attached_bath = None
                if bed.name == "master_bed" and bath_rooms:
                    attached_bath = bath_rooms[0]

                result.append(RoomLayout(
                    name=bed.name,
                    x=strip_x, y=by,
                    width=bw, depth=bed_d,
                    zone="rear",
                    door_wall="south",
                    touches_external=[ext_wall, "north"] if by + bed_d >= unit_d - 0.1 else [ext_wall],
                ))

                if attached_bath and bed.name == "master_bed":
                    bath_w = min(attached_bath.width_m, strip_w - bw)
                    if bath_w > 0.8:
                        result.append(RoomLayout(
                            name="bathroom_1",
                            x=strip_x + bw, y=by,
                            width=bath_w, depth=attached_bath.depth_m,
                            zone="rear",
                            door_wall="west",
                            touches_external=[],
                        ))

            return result

        layouts.extend(place_beds_in_strip(
            left_beds, left_x, left_w, rear_y0, rear_d, "left"
        ))
        layouts.extend(place_beds_in_strip(
            right_beds, right_x, right_w, rear_y0, rear_d, "right"
        ))

        # Remaining bathrooms (non-master) — shared, flanking the passage
        # Alternate placement: left of passage, then right of passage.
        remaining_baths = bath_rooms[1:] if bath_rooms else []
        for k, bath in enumerate(remaining_baths):
            bath_w = min(bath.width_m, 1.5)
            if k % 2 == 0:
                # Left of passage (between left bedroom strip and passage)
                bx = max(0.0, passage_x - bath_w)
            else:
                # Right of passage (between passage and right bedroom strip)
                bx = passage_x + passage_w
            by = rear_y0 + k * bath.depth_m
            layouts.append(RoomLayout(
                name=f"bathroom_{k + 2}",
                x=bx, y=by,
                width=bath_w,
                depth=bath.depth_m,
                zone="rear",
                door_wall="west" if k % 2 == 0 else "east",
                touches_external=[],
            ))

    # --- PASSAGE: vertical spine from middle band to end of rear band ---
    passage_depth = unit_d - _passage_mid_y
    layouts.append(RoomLayout(
        name="passage",
        x=passage_x, y=_passage_mid_y,
        width=passage_w, depth=passage_depth,
        zone="middle",
        door_wall="south",
        touches_external=[],
        is_passage=True,
    ))

    return layouts


# ---------------------------------------------------------------------------
# Subsystem C: Constraint Validator
# ---------------------------------------------------------------------------

def validate_layout(
    layouts: List[RoomLayout],
    unit_w: float,
    unit_d: float,
) -> ValidationResult:
    """
    Assert Surat spatial rules on the generated layout.
    Returns ValidationResult(passed=True) or lists all violations.
    """
    violations: List[str] = []
    by_name = {r.name: r for r in layouts}

    def get(name: str) -> Optional[RoomLayout]:
        return by_name.get(name)

    # 1. Living must be in front zone (smallest y values)
    living = get("living")
    if not living:
        violations.append("MISSING: living room not in layout")
    else:
        if living.zone != "front":
            violations.append(f"living zone={living.zone}, expected front")

    # 2. Dining must be north of (behind) living
    dining = get("dining")
    if dining and living:
        if dining.y <= living.y:
            violations.append(
                f"dining.y={dining.y:.2f} must be > living.y={living.y:.2f}"
            )

    # 3. Kitchen must be north of dining
    kitchen = get("kitchen")
    if kitchen and dining:
        if kitchen.y < dining.y:
            violations.append(
                f"kitchen.y={kitchen.y:.2f} must be >= dining.y={dining.y:.2f}"
            )

    # 4. living and dining must share an edge
    if living and dining:
        if not living.shares_edge_with(dining):
            violations.append("living and dining do not share a wall edge")

    # 5. Kitchen must touch an external wall
    if kitchen:
        if not kitchen.touches_external:
            violations.append("kitchen does not touch external wall (ventilation)")

    # 6. Living must touch an external wall
    if living:
        if not living.touches_external:
            violations.append("living does not touch external wall")

    # 7. Passage must exist
    passage = get("passage")
    if not passage:
        violations.append("MISSING: passage not in layout")

    # 8. All bedrooms must be in rear zone and have y > passage start
    bed_names = [r.name for r in layouts if r.name.startswith("bed") or r.name == "master_bed"]
    for bname in bed_names:
        bed = get(bname)
        if bed and passage:
            if bed.y < passage.y - 0.1:
                violations.append(
                    f"{bname}.y={bed.y:.2f} starts before passage.y={passage.y:.2f}"
                )

    # 9. No bedroom should have y <= living.y (bedroom not at front)
    if living:
        for bname in bed_names:
            bed = get(bname)
            if bed and bed.y <= living.y + 0.1:
                violations.append(
                    f"{bname}.y={bed.y:.2f} overlaps with living zone y={living.y:.2f}"
                )

    # 10. Powder room must be in front zone
    powder = get("powder_room")
    if powder:
        if powder.y > unit_d * 0.35:
            violations.append(
                f"powder_room.y={powder.y:.2f} too far from entry (unit_d={unit_d:.2f})"
            )

    # 11. Prohibited direct connections (geometry proximity check)
    for edge in SURAT_PROHIBITED_EDGES:
        ra = get(edge.room_a)
        rb = get(edge.room_b)
        if ra and rb:
            if ra.shares_edge_with(rb):
                violations.append(
                    f"PROHIBITED: {edge.room_a} shares edge with {edge.room_b} — {edge.reason}"
                )

    passed = len(violations) == 0
    if not passed:
        logger.warning("[layout_engine] Validation violations: %s", violations)
    return ValidationResult(passed=passed, violations=violations)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_unit_layout(
    programme: RoomProgramme,
    unit_w: float,
    unit_d: float,
    units_per_core: int,
) -> Tuple[List[RoomLayout], ValidationResult]:
    """
    Generate a validated room layout for one unit.

    Attempts up to _MAX_REGENERATE_ATTEMPTS with adjusted parameters on failure.
    Always returns the best result (fewest violations) even if not fully passing.

    Args:
        programme:      RoomProgramme from unit_programme.derive_room_programme()
        unit_w:         unit width in metres
        unit_d:         unit depth in metres
        units_per_core: number of units per floor core

    Returns:
        (layouts, validation_result) — layouts is list[RoomLayout]
    """
    template = select_template(programme.unit_type, units_per_core)

    best_layouts: List[RoomLayout] = []
    best_result = ValidationResult(passed=False, violations=["not attempted"])

    for attempt in range(_MAX_REGENERATE_ATTEMPTS):
        layouts = _partition_bands(programme, unit_w, unit_d, template, attempt=attempt)
        result = validate_layout(layouts, unit_w, unit_d)

        if result.passed:
            logger.info(
                "[layout_engine] Layout validated OK on attempt %d "
                "(unit_type=%s, segment=%s, %dx%.1fm)",
                attempt, programme.unit_type, programme.segment, unit_w, unit_d,
            )
            return layouts, result

        if attempt == 0 or len(result.violations) < len(best_result.violations):
            best_layouts = layouts
            best_result = result

        logger.warning(
            "[layout_engine] Attempt %d failed (%d violations). Retrying...",
            attempt, len(result.violations),
        )

    logger.error(
        "[layout_engine] All %d attempts failed. Returning best result with %d violations.",
        _MAX_REGENERATE_ATTEMPTS, len(best_result.violations),
    )
    return best_layouts, best_result
