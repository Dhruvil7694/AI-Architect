"""
detailed_layout/config.py — Configuration for Phase D detailing.

All tunables are explicit here to keep the detailing layer deterministic
and testable. No global magic constants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DetailingConfig:
    # Wall system
    external_wall_thickness_m: float = 0.23
    internal_wall_thickness_m: float = 0.115
    shaft_wall_thickness_m: float = 0.23

    # Structure
    column_size_m: tuple[float, float] = (0.3, 0.3)
    # Preferred module width used for grid spacing; must be passed in from the
    # same engine config / presets that drive repetition. Phase D does not
    # attempt to infer this value.
    grid_module_width_m: Optional[float] = None

    # Doors
    door_widths_m: Dict[str, float] = field(
        default_factory=lambda: {
            "ENTRY": 1.0,
            "BEDROOM": 0.9,
            "TOILET": 0.75,
            "KITCHEN": 0.9,
        }
    )
    door_clearances_m: Dict[str, float] = field(
        default_factory=lambda: {
            "from_corner_min": 0.2,
            "between_doors_min": 0.2,
        }
    )

    # Windows
    window_widths_m: Dict[str, float] = field(
        default_factory=lambda: {
            "LIVING": 1.5,
            "BEDROOM": 1.2,
            "TOILET_VENT": 0.6,
        }
    )
    window_sill_heights_m: Dict[str, float] = field(
        default_factory=lambda: {
            "LIVING": 0.9,
            "BEDROOM": 0.9,
            "TOILET_VENT": 1.8,
            "KITCHEN": 1.0,
        }
    )
    window_clearance_min_m: float = 0.2

    # Feature toggles
    furniture_enabled: bool = True
    annotation_enabled: bool = True
    grid_enabled: bool = True
    hatch_enabled: bool = True

    # Annotation sizes
    room_text_height_m: float = 0.3
    title_text_height_m: float = 0.35
    scale_text_height_m: float = 0.25

    # DXF styling hints (detailing layer does not depend on these for geometry)
    lineweight_map: Dict[str, float] = field(default_factory=dict)
    linetype_map: Dict[str, str] = field(default_factory=dict)
    hatch_patterns: Dict[str, str] = field(
        default_factory=lambda: {
            "wet_area": "ANSI31",
            "core": "SOLID",
        }
    )

    # Geometry tolerances
    snap_tol_m: float = 1e-3
    min_segment_length_m: float = 1e-3

