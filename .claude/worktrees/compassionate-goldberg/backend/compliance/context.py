from __future__ import annotations

"""
backend.compliance.context
--------------------------

Defines the flattened, numeric/boolean-only ComplianceContext DTO that Phase E
uses as the single source of derived metrics for deterministic rule evaluation.

Schema constraints:
  - Flat namespace: no nested DTOs, no dynamic dict keys.
  - Only scalar leaf types: float, int, bool, str identifiers.
  - Geometry-agnostic: no polygons, coordinates, or DXF artefacts.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ComplianceContext:
    """
    Flattened, geometry-free snapshot of all metrics required for
    deterministic CGDCR residential compliance evaluation.

    All numeric fields are expected to be:
      - expressed in SI units (metres, square metres, unitless ratios)
      - pre-normalised to fixed precision by the metric extractor
    """

    # === GLOBAL / ADMINISTRATIVE ==================================================

    ruleset_id: str
    ruleset_version: str
    development_category_code: int  # e.g. 1–10 for D1–D10

    # === PLOT DOMAIN ==============================================================

    plot_area_sqm: float
    plot_frontage_m: float
    road_width_m: float
    plot_is_corner: bool

    # === BUILDING DOMAIN ==========================================================

    building_height_m: float
    building_height_limit_m: float

    building_total_bua_sqm: float
    building_fsi: float
    building_fsi_limit: float

    building_ground_coverage_pct: Optional[float]
    building_ground_coverage_present: bool
    building_ground_coverage_limit_pct: float

    building_number_of_floors: int
    building_number_of_basements: int
    building_has_stilt: bool

    # === STRUCTURE DOMAIN (CORES, STAIRS, LIFTS) =================================

    structure_number_of_stairs: int
    structure_required_min_stairs: int

    structure_stair_min_width_m: float
    structure_stair_max_riser_m: float
    structure_stair_min_tread_m: float

    structure_lift_count: int
    structure_lift_required: bool

    # === SAFETY DOMAIN ============================================================

    safety_has_fire_stair: bool
    safety_has_external_stair: bool

    safety_fire_sprinkler_required: bool
    safety_fire_sprinkler_provided: bool

    safety_fire_detection_required: bool
    safety_fire_detection_provided: bool

    safety_refuge_required: bool
    safety_refuge_provided: bool

    # === PARKING DOMAIN ===========================================================

    parking_required_total: int
    parking_provided_total: int

    # === FIRE DOMAIN (TRIGGERS / NOC) ============================================

    fire_requires_refuge: bool
    fire_requires_noc: bool

    # === ENVIRONMENT DOMAIN =======================================================

    environment_requires_rainwater_harvesting: bool
    environment_has_rainwater_harvesting: bool

    environment_requires_solar_hot_water: bool
    environment_has_solar_hot_water: bool

    # === ACCESSIBILITY DOMAIN (RESERVED FOR FUTURE) ==============================

    accessibility_lift_reaches_all_floors: bool
    accessibility_basic_compliant: bool


