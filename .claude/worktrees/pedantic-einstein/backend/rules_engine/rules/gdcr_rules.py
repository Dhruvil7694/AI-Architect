"""
rules/gdcr_rules.py
-------------------
Evaluator functions for every GDCR rule defined in loader.py.

Each function signature:
    evaluate_<rule_slug>(inputs: dict, gdcr: dict) -> RuleResult

The `inputs` dict is built by the evaluator from a BuildingProposal + Plot.
The `gdcr` dict is the raw parsed GDCR.yaml content.

Convention
----------
- Convert all areas to sq.m. internally for comparison when the GDCR
  threshold is expressed in metres.  Plot/BUA data from the DB is in sq.ft;
  1 sq.ft = 0.0929030 sq.m.
- Heights and road widths are always in metres.
- Return NA when the rule is not triggered for this building configuration.
- Return MISSING_DATA when a required input key is absent.
"""

from __future__ import annotations

from typing import Optional

from rules_engine.rules.base import (
    FAIL, INFO, MISSING_DATA, NA, PASS, Rule, RuleResult,
)
from rules_engine.rules.loader import get_gdcr_config
from common.units import sqft_to_sqm


def _missing(rule: Rule, key: str) -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id, source=rule.source, category=rule.category,
        description=rule.description, status=MISSING_DATA,
        note=f"Required input '{key}' was not provided.",
    )


def _result(rule: Rule, status: str, required=None, actual=None,
            unit: str = "", note: str = "") -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id, source=rule.source, category=rule.category,
        description=rule.description, status=status,
        required_value=required, actual_value=actual, unit=unit, note=note,
    )


# ── GDCR evaluators ───────────────────────────────────────────────────────────

def evaluate_gdcr_access_road_width(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_rw = gdcr["access_rules"]["minimum_road_width_for_dw3"]   # 9 m

    rw = inputs.get("road_width")
    if rw is None:
        return _missing(rule, "road_width")

    status = PASS if rw >= min_rw else FAIL
    return _result(rule, status, required=float(min_rw), actual=float(rw), unit="m",
                   note="" if status == PASS else
                   "DW3 Apartments not permitted on this road width.")


def evaluate_gdcr_fsi_base(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    base_fsi = gdcr["fsi_rules"]["base_fsi"]   # 1.8

    pa  = inputs.get("plot_area")
    bua = inputs.get("total_bua")
    if pa is None: return _missing(rule, "plot_area")
    if bua is None: return _missing(rule, "total_bua")

    # Both in sq.ft; FSI is dimensionless
    actual_fsi = round(bua / pa, 4) if pa > 0 else 0.0
    status = PASS if actual_fsi <= base_fsi else FAIL
    return _result(rule, status, required=float(base_fsi), actual=actual_fsi,
                   note="" if status == PASS else
                   f"Proposed FSI {actual_fsi:.2f} exceeds base FSI {base_fsi}.")


def evaluate_gdcr_fsi_max(inputs: dict, rule: Rule) -> RuleResult:
    """
    Evaluate maximum permissible FSI with support for premium tiers and
    corridor-based caps.
    """
    gdcr = get_gdcr_config()
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}

    pa = inputs.get("plot_area")
    bua = inputs.get("total_bua")
    if pa is None:
        return _missing(rule, "plot_area")
    if bua is None:
        return _missing(rule, "total_bua")

    # Compute achieved FSI once (dimensionless).
    actual_fsi = round(bua / pa, 4) if pa > 0 else 0.0

    # Dynamic cap from premium_tiers + corridor_rule when present.
    tiers = fsi_cfg.get("premium_tiers") or []
    corridor_rule = fsi_cfg.get("corridor_rule") or {}
    eligible_if = corridor_rule.get("eligible_if") or {}

    rw = inputs.get("road_width")
    road_width_min = float(eligible_if.get("road_width_min_m", 36.0))
    corridor_eligible = rw is not None and float(rw) >= road_width_min

    max_fsi: float
    if tiers:
        try:
            highest_cap = max(float(t.get("resulting_cap", 0.0)) for t in tiers)
        except Exception:
            highest_cap = 0.0
        try:
            first_cap = float(tiers[0].get("resulting_cap", 0.0))
        except Exception:
            first_cap = highest_cap
        max_fsi = highest_cap if corridor_eligible else first_cap
    else:
        max_fsi = float(fsi_cfg.get("maximum_fsi", 2.7))

    status = PASS if actual_fsi <= max_fsi else FAIL
    return _result(
        rule,
        status,
        required=float(max_fsi),
        actual=actual_fsi,
        note="" if status == PASS else f"Proposed FSI {actual_fsi:.2f} exceeds maximum FSI {max_fsi}.",
    )


def evaluate_gdcr_fsi_incentive_eligibility(inputs: dict, rule: Rule) -> RuleResult:
    """
    Eligibility for corridor-based FSI incentive near 36m / 45m roads.

    This rule is intentionally soft and must never raise if the incentive
    block is absent from GDCR.yaml. When not configured, it returns NA.
    """
    gdcr = get_gdcr_config()
    fsi_cfg = gdcr.get("fsi_rules", {}) or {}
    incentive = fsi_cfg.get("incentive_if_near_36m_or_45m_road")

    if not incentive:
        # No incentive configuration present; treat as not applicable instead of
        # raising a KeyError that would pollute logs and mark the group ERROR.
        return _result(
            rule,
            NA,
            note="No incentive_if_near_36m_or_45m_road configured in GDCR.yaml; incentive FSI not applicable.",
        )

    within_dist = incentive.get("within_distance", 0.0)   # e.g. 200 m
    max_fsi = incentive.get("max_fsi", 0.0)               # e.g. 4.0

    dist = inputs.get("distance_to_wide_road")
    if dist is None:
        return _result(rule, NA, note="Distance to wide road not provided; incentive FSI not evaluated.")

    if dist <= within_dist:
        return _result(rule, INFO, required=float(max_fsi),
                       note=f"Plot is {dist:.0f} m from a 36/45 m road. "
                            f"Incentive FSI up to {max_fsi} may be applicable subject to authority approval.")
    return _result(rule, NA,
                   note=f"Plot is {dist:.0f} m from nearest wide road (threshold {within_dist} m). "
                        "Incentive FSI not applicable.")


def evaluate_gdcr_height_max(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    height_map = gdcr["height_rules"]["road_width_height_map"]

    rw = inputs.get("road_width")
    bh = inputs.get("building_height")
    if rw is None: return _missing(rule, "road_width")
    if bh is None: return _missing(rule, "building_height")

    max_h = None
    for entry in height_map:
        if rw <= entry["road_max"]:
            max_h = entry["max_height"]
            break
    if max_h is None:
        max_h = height_map[-1]["max_height"]

    status = PASS if bh <= max_h else FAIL
    return _result(rule, status, required=float(max_h), actual=float(bh), unit="m",
                   note="" if status == PASS else
                   f"Height {bh} m exceeds limit {max_h} m for road width {rw} m.")


def evaluate_gdcr_height_road_dw3(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_rw = gdcr["access_rules"]["minimum_road_width_for_dw3"]          # 9 m
    cap_h  = gdcr["access_rules"]["if_road_width_less_than_9"]["max_height"]  # 10 m

    rw = inputs.get("road_width")
    bh = inputs.get("building_height")
    if rw is None: return _missing(rule, "road_width")
    if bh is None: return _missing(rule, "building_height")

    if rw >= min_rw:
        return _result(rule, NA, note=f"Road width {rw} m >= {min_rw} m; DW3 height cap not triggered.")

    status = PASS if bh <= cap_h else FAIL
    return _result(rule, status, required=float(cap_h), actual=float(bh), unit="m",
                   note=f"Road width {rw} m < 9 m: DW3 is not permitted and height is capped at {cap_h} m.")


def evaluate_gdcr_margin_side_rear(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    margin_map = gdcr["side_rear_margin"]["height_margin_map"]

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    required_margin = None
    for entry in margin_map:
        if bh <= entry["height_max"]:
            required_margin = entry["side"]   # side == rear for all entries
            break
    if required_margin is None:
        required_margin = margin_map[-1]["side"]

    # If actual side/rear margins were provided, validate; otherwise report INFO
    side = inputs.get("side_margin")
    rear = inputs.get("rear_margin")

    if side is None and rear is None:
        return _result(rule, INFO, required=float(required_margin), unit="m",
                       note=f"Required side and rear margin for height {bh} m is {required_margin} m. "
                            "Confirm in the drawing.")

    fails = []
    if side is not None and side < required_margin:
        fails.append(f"side margin {side} m < required {required_margin} m")
    if rear is not None and rear < required_margin:
        fails.append(f"rear margin {rear} m < required {required_margin} m")

    if fails:
        return _result(rule, FAIL, required=float(required_margin),
                       actual=min(v for v in [side, rear] if v is not None),
                       unit="m", note="; ".join(fails))
    return _result(rule, PASS, required=float(required_margin),
                   actual=min(v for v in [side, rear] if v is not None), unit="m")


def evaluate_gdcr_lift_required(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    trigger_h = gdcr["lift_requirement"]["if_height_above"]   # 10 m

    bh       = inputs.get("building_height")
    has_lift = inputs.get("has_lift")
    if bh is None:
        return _missing(rule, "building_height")

    if bh <= trigger_h:
        return _result(rule, NA, note=f"Height {bh} m <= {trigger_h} m; lift not mandatory.")

    if has_lift is None:
        return _result(rule, INFO, required=1.0,
                       note=f"Building height {bh} m > {trigger_h} m: lift is mandatory. "
                            "Declare lift provision in the proposal.")

    status = PASS if has_lift else FAIL
    return _result(rule, status, required=1.0, actual=1.0 if has_lift else 0.0,
                   note="" if has_lift else "Lift is required but not declared in proposal.")


def evaluate_gdcr_staircase_width(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_w = gdcr["staircase"]["minimum_width"]["residential_apartment"]   # 1.0 m

    sw = inputs.get("stair_width")
    if sw is None:
        return _result(rule, INFO, required=float(min_w), unit="m",
                       note=f"Staircase width not provided. Required minimum: {min_w} m.")

    status = PASS if sw >= min_w else FAIL
    return _result(rule, status, required=float(min_w), actual=float(sw), unit="m")


def evaluate_gdcr_staircase_tread_riser(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_tread = gdcr["staircase"]["tread_min"]   # 250 mm
    max_riser = gdcr["staircase"]["riser_max"]   # 190 mm

    tread = inputs.get("tread_mm")
    riser = inputs.get("riser_mm")

    fails = []
    if tread is not None and tread < min_tread:
        fails.append(f"tread {tread} mm < min {min_tread} mm")
    if riser is not None and riser > max_riser:
        fails.append(f"riser {riser} mm > max {max_riser} mm")

    if tread is None and riser is None:
        return _result(rule, INFO, note=f"Staircase tread/riser not provided. "
                       f"Required: tread >= {min_tread} mm, riser <= {max_riser} mm.")

    if fails:
        return _result(rule, FAIL, note="; ".join(fails))
    return _result(rule, PASS, note=f"Tread {tread} mm OK, riser {riser} mm OK.")


def evaluate_gdcr_ventilation_window_ratio(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_ratio = gdcr["ventilation"]["habitable_room_window_ratio"]   # 0.1667

    wa = inputs.get("window_area")
    fa = inputs.get("floor_area")

    if wa is None or fa is None:
        return _result(rule, INFO, required=round(min_ratio * 100, 2),
                       unit="%", note=f"Window and floor areas not provided. "
                       f"Required: window area >= {min_ratio * 100:.1f} % of floor area.")

    if fa <= 0:
        return _result(rule, MISSING_DATA, note="Floor area is zero or negative.")

    actual_ratio = wa / fa
    status = PASS if actual_ratio >= min_ratio else FAIL
    return _result(rule, status,
                   required=round(min_ratio * 100, 2),
                   actual=round(actual_ratio * 100, 2),
                   unit="%",
                   note="" if status == PASS else
                   f"Window ratio {actual_ratio * 100:.1f} % < required {min_ratio * 100:.1f} %.")


def evaluate_gdcr_clearance_habitable(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_h = gdcr["minimum_clearance_height"]["habitable_room"]   # 2.75 m

    rh = inputs.get("room_height")
    if rh is None:
        return _result(rule, INFO, required=float(min_h), unit="m",
                       note=f"Room height not provided. Required minimum: {min_h} m.")
    status = PASS if rh >= min_h else FAIL
    return _result(rule, status, required=float(min_h), actual=float(rh), unit="m")


def evaluate_gdcr_clearance_bathroom(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    min_h = gdcr["minimum_clearance_height"]["bathroom"]   # 2.1 m

    bh = inputs.get("bathroom_height")
    if bh is None:
        return _result(rule, INFO, required=float(min_h), unit="m",
                       note=f"Bathroom height not provided. Required minimum: {min_h} m.")
    status = PASS if bh >= min_h else FAIL
    return _result(rule, status, required=float(min_h), actual=float(bh), unit="m")


def evaluate_gdcr_fire_refuge_area(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    trigger_h = gdcr["fire_safety"]["refuge_area_if_height_above"]   # 25 m

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    if bh <= trigger_h:
        return _result(rule, NA, note=f"Height {bh} m <= {trigger_h} m; refuge area not triggered.")

    return _result(rule, INFO, note=f"Building height {bh} m > {trigger_h} m: "
                   "Refuge area is mandatory. Confirm provision in the proposal.")


def evaluate_gdcr_fire_noc(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    trigger_h = gdcr["fire_safety"]["fire_noc_required_if_height_above"]   # 15 m

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    if bh <= trigger_h:
        return _result(rule, NA, note=f"Height {bh} m <= {trigger_h} m; fire NOC not required.")

    return _result(rule, INFO, note=f"Building height {bh} m > {trigger_h} m: "
                   "Fire NOC from the competent authority is required before construction.")


def evaluate_gdcr_boundary_wall_road_side(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    max_h = gdcr["architectural_elements"]["boundary_wall"]["road_side_max_height"]   # 1.5 m

    wh = inputs.get("wall_height_road_side")
    if wh is None:
        return _result(rule, INFO, required=float(max_h), unit="m",
                       note=f"Road-side boundary wall height not provided. Maximum allowed: {max_h} m.")
    status = PASS if wh <= max_h else FAIL
    return _result(rule, status, required=float(max_h), actual=float(wh), unit="m")


def evaluate_gdcr_boundary_wall_other_side(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    max_h = gdcr["architectural_elements"]["boundary_wall"]["other_side_max_height"]   # 1.8 m

    wh = inputs.get("wall_height_other_side")
    if wh is None:
        return _result(rule, INFO, required=float(max_h), unit="m",
                       note=f"Non-road-side boundary wall height not provided. Maximum allowed: {max_h} m.")
    status = PASS if wh <= max_h else FAIL
    return _result(rule, status, required=float(max_h), actual=float(wh), unit="m")


def evaluate_gdcr_env_solar(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    trigger_bua = gdcr["environmental"]["solar_water_heating_required_if_builtup_above"]   # 500 sq.m

    # Accept sq.m directly (total_bua_sqm) or convert from sq.ft (total_bua)
    bua_sqm = inputs.get("total_bua_sqm")
    if bua_sqm is None:
        bua_sqft = inputs.get("total_bua")
        if bua_sqft is not None:
            bua_sqm = sqft_to_sqm(bua_sqft)
        else:
            return _result(rule, INFO, required=float(trigger_bua), unit="sq.m",
                           note=f"BUA not provided. Solar heating mandatory if total BUA > {trigger_bua} sq.m.")

    if bua_sqm <= trigger_bua:
        return _result(rule, NA, actual=round(bua_sqm, 1), unit="sq.m",
                       note=f"Total BUA {bua_sqm:.1f} sq.m <= {trigger_bua} sq.m; solar heating not mandatory.")

    return _result(rule, INFO, required=float(trigger_bua), actual=round(bua_sqm, 1), unit="sq.m",
                   note=f"Total BUA {bua_sqm:.1f} sq.m > {trigger_bua} sq.m: "
                        "Solar water heating system is mandatory.")


def evaluate_gdcr_env_rainwater_harvesting(inputs: dict, rule: Rule) -> RuleResult:
    return _result(rule, INFO,
                   note="Rainwater harvesting system is mandatory for all buildings under GDCR 2017. "
                        "Confirm provision in the proposal.")


def evaluate_gdcr_basement_height(inputs: dict, rule: Rule) -> RuleResult:
    gdcr = get_gdcr_config()
    has_basement = inputs.get("has_basement", False)

    if not has_basement:
        return _result(rule, NA, note="No basement declared in proposal.")

    min_h = gdcr["basement"]["height_min"]   # 2.4 m
    bh = inputs.get("basement_height")
    if bh is None:
        return _result(rule, INFO, required=float(min_h), unit="m",
                       note=f"Basement declared but height not provided. Required minimum: {min_h} m.")
    status = PASS if bh >= min_h else FAIL
    return _result(rule, status, required=float(min_h), actual=float(bh), unit="m")


# ── Dispatch table ────────────────────────────────────────────────────────────

GDCR_EVALUATORS = {
    "gdcr.access.road_width":            evaluate_gdcr_access_road_width,
    "gdcr.fsi.base":                     evaluate_gdcr_fsi_base,
    "gdcr.fsi.max":                      evaluate_gdcr_fsi_max,
    "gdcr.fsi.incentive_eligibility":    evaluate_gdcr_fsi_incentive_eligibility,
    "gdcr.height.max":                   evaluate_gdcr_height_max,
    "gdcr.height.road_dw3":              evaluate_gdcr_height_road_dw3,
    "gdcr.margin.side_rear":             evaluate_gdcr_margin_side_rear,
    "gdcr.lift.required":                evaluate_gdcr_lift_required,
    "gdcr.staircase.width":              evaluate_gdcr_staircase_width,
    "gdcr.staircase.tread_riser":        evaluate_gdcr_staircase_tread_riser,
    "gdcr.ventilation.window_ratio":     evaluate_gdcr_ventilation_window_ratio,
    "gdcr.clearance.habitable":          evaluate_gdcr_clearance_habitable,
    "gdcr.clearance.bathroom":           evaluate_gdcr_clearance_bathroom,
    "gdcr.fire.refuge_area":             evaluate_gdcr_fire_refuge_area,
    "gdcr.fire.noc":                     evaluate_gdcr_fire_noc,
    "gdcr.boundary_wall.road_side":      evaluate_gdcr_boundary_wall_road_side,
    "gdcr.boundary_wall.other_side":     evaluate_gdcr_boundary_wall_other_side,
    "gdcr.env.solar":                    evaluate_gdcr_env_solar,
    "gdcr.env.rainwater_harvesting":     evaluate_gdcr_env_rainwater_harvesting,
    "gdcr.basement.height":              evaluate_gdcr_basement_height,
}
