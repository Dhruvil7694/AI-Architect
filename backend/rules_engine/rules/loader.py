"""
rules/loader.py
---------------
Loads GDCR.yaml and NBC.yaml from the project root and returns:
  - gdcr_config : the raw parsed GDCR dict  (used by gdcr_rules.py)
  - nbc_config  : the raw parsed NBC dict   (used by nbc_rules.py)
  - ALL_RULES   : Dict[rule_id, Rule]       (used by the evaluator)

The YAML files are resolved relative to Django's BASE_DIR so the loader
works regardless of where manage.py is invoked from.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict

import yaml

from rules_engine.rules.base import Rule

logger = logging.getLogger(__name__)

# ── YAML file resolution ──────────────────────────────────────────────────────
# BASE_DIR = backend/   →  project root = backend/../  = /code
def _project_root() -> Path:
    from django.conf import settings
    return Path(settings.BASE_DIR).parent


def _load_yaml(filename: str) -> dict:
    path = _project_root() / filename
    if not path.exists():
        raise FileNotFoundError(f"Rules YAML not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    logger.info("Loaded %s (%d top-level keys)", path.name, len(data))
    return data


# ── Public cached accessors ───────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_gdcr_config() -> dict:
    return _load_yaml("GDCR.yaml")


@lru_cache(maxsize=1)
def get_nbc_config() -> dict:
    return _load_yaml("NBC.yaml")


@lru_cache(maxsize=1)
def get_all_rules() -> Dict[str, Rule]:
    """
    Build and return the complete catalogue of Rule descriptors,
    one per evaluable clause in GDCR + NBC.
    """
    rules: Dict[str, Rule] = {}

    # ── GDCR rules ────────────────────────────────────────────────────────────
    _gdcr = [
        Rule("gdcr.access.road_width",
             "GDCR", "access",
             "Minimum road width for DW3 (Apartments) is 9 m.",
             ["road_width"]),

        Rule("gdcr.fsi.base",
             "GDCR", "fsi",
             "Proposed FSI must not exceed the base FSI of 1.8.",
             ["plot_area", "total_bua"]),

        Rule("gdcr.fsi.max",
             "GDCR", "fsi",
             "Proposed FSI (including chargeable component) must not exceed maximum FSI of 2.7.",
             ["plot_area", "total_bua"]),

        Rule("gdcr.fsi.incentive_eligibility",
             "GDCR", "fsi",
             "FSI incentive up to 4.0 is available if plot is within 200 m of a 36 m or 45 m road.",
             ["road_width", "distance_to_wide_road"]),

        Rule("gdcr.height.max",
             "GDCR", "height",
             "Maximum permissible building height is determined by adjacent road width (Table 6.23).",
             ["road_width", "building_height"]),

        Rule("gdcr.height.road_dw3",
             "GDCR", "height",
             "If road width < 9 m, DW3 is not permitted and maximum height is capped at 10 m.",
             ["road_width", "building_height"]),

        Rule("gdcr.margin.road_side",
             "GDCR", "margins",
             "Minimum road-side (front) margin = max(H/5, Table 6.24 value, 1.5 m).",
             ["road_width", "building_height"]),

        Rule("gdcr.margin.side_rear",
             "GDCR", "margins",
             "Minimum side and rear margins are determined by building height (Table 6.26).",
             ["building_height"]),

        Rule("gdcr.gc.max",
             "GDCR", "ground_coverage",
             "Maximum ground coverage for DW3 residential is 40% of plot area (Table 6.22).",
             ["plot_area", "ground_coverage"]),

        Rule("gdcr.cop.required",
             "GDCR", "cop",
             "Common Open Plot required >= 10% of plot area (or 200 sq.m) when plot > 2000 sq.m.",
             ["plot_area"]),

        Rule("gdcr.lift.required",
             "GDCR", "lift",
             "Lift is mandatory for buildings exceeding 10 m height.",
             ["building_height", "has_lift"]),

        Rule("gdcr.staircase.width",
             "GDCR", "staircase",
             "Minimum staircase width for residential apartments is 1.0 m (Table 13.2).",
             ["stair_width"]),

        Rule("gdcr.staircase.tread_riser",
             "GDCR", "staircase",
             "Minimum tread 250 mm, maximum riser 190 mm.",
             ["tread_mm", "riser_mm"]),

        Rule("gdcr.ventilation.window_ratio",
             "GDCR", "ventilation",
             "Habitable room window area must be at least 1/6 (16.67 %) of the floor area.",
             ["window_area", "floor_area"]),

        Rule("gdcr.clearance.habitable",
             "GDCR", "clearance",
             "Minimum floor-to-ceiling height for habitable rooms is 2.75 m.",
             ["room_height"]),

        Rule("gdcr.clearance.bathroom",
             "GDCR", "clearance",
             "Minimum floor-to-ceiling height for bathrooms is 2.1 m.",
             ["bathroom_height"]),

        Rule("gdcr.fire.refuge_area",
             "GDCR", "fire",
             "Refuge area is mandatory for buildings exceeding 25 m height.",
             ["building_height"]),

        Rule("gdcr.fire.noc",
             "GDCR", "fire",
             "Fire NOC from competent authority is required for buildings exceeding 15 m height.",
             ["building_height"]),

        Rule("gdcr.boundary_wall.road_side",
             "GDCR", "architectural",
             "Boundary wall on road side must not exceed 1.5 m height.",
             ["wall_height_road_side"]),

        Rule("gdcr.boundary_wall.other_side",
             "GDCR", "architectural",
             "Boundary wall on non-road sides must not exceed 1.8 m height.",
             ["wall_height_other_side"]),

        Rule("gdcr.env.solar",
             "GDCR", "environmental",
             "Solar water heating is mandatory if total built-up area exceeds 500 sq.m.",
             ["total_bua_sqm"]),

        Rule("gdcr.env.rainwater_harvesting",
             "GDCR", "environmental",
             "Rainwater harvesting system is mandatory.",
             []),

        Rule("gdcr.basement.height",
             "GDCR", "basement",
             "Minimum basement clear height is 2.4 m.",
             ["basement_height"]),
    ]
    for r in _gdcr:
        rules[r.rule_id] = r

    # ── NBC rules ─────────────────────────────────────────────────────────────
    _nbc = [
        Rule("nbc.classification",
             "NBC", "classification",
             "Building is classified as high-rise if height >= 15 m (NBC 2016 Part 4).",
             ["building_height"]),

        Rule("nbc.egress.exits",
             "NBC", "egress",
             "Minimum 2 exits are required for residential occupancy.",
             ["num_exits"]),

        Rule("nbc.egress.travel_distance",
             "NBC", "egress",
             "Maximum travel distance to exit: 30 m (sprinklered) or 22.5 m (non-sprinklered).",
             ["travel_distance", "is_sprinklered"]),

        Rule("nbc.egress.corridor_width",
             "NBC", "egress",
             "Minimum corridor width is 1.0 m.",
             ["corridor_width"]),

        Rule("nbc.staircase.width",
             "NBC", "staircase",
             "Minimum staircase width: 1.0 m (low-rise, height < 15 m) or 1.5 m (high-rise).",
             ["building_height", "stair_width"]),

        Rule("nbc.staircase.tread_riser",
             "NBC", "staircase",
             "Minimum tread 250 mm, maximum riser 190 mm.",
             ["tread_mm", "riser_mm"]),

        Rule("nbc.staircase.headroom",
             "NBC", "staircase",
             "Minimum headroom on staircase is 2.2 m.",
             ["stair_headroom"]),

        Rule("nbc.door.width",
             "NBC", "egress",
             "Minimum exit door width is 0.9 m.",
             ["door_width"]),

        Rule("nbc.high_rise.fire_lift",
             "NBC", "fire",
             "Fire lift is mandatory for buildings with height >= 15 m.",
             ["building_height", "has_fire_lift"]),

        Rule("nbc.high_rise.firefighting_shaft",
             "NBC", "fire",
             "Firefighting shaft (120 min FRR) is required for buildings >= 15 m.",
             ["building_height", "has_firefighting_shaft"]),

        Rule("nbc.high_rise.refuge_area",
             "NBC", "fire",
             "Refuge area (min 4 % of floor area) is required for buildings exceeding 60 m.",
             ["building_height", "refuge_area_pct"]),

        Rule("nbc.fire_separation",
             "NBC", "fire",
             "Minimum fire separation distance between buildings is 6 m.",
             ["fire_separation_distance"]),

        Rule("nbc.compartmentation",
             "NBC", "fire",
             "Fire barrier and fire door rating must be minimum 120 minutes.",
             ["fire_door_rating"]),
    ]
    for r in _nbc:
        rules[r.rule_id] = r

    logger.info("Rule catalogue built: %d GDCR + %d NBC = %d total rules",
                len(_gdcr), len(_nbc), len(rules))
    return rules
