"""
rules/nbc_rules.py
------------------
Evaluator functions for every NBC 2016 (Part 4) rule defined in loader.py.

Each function signature:
    evaluate_nbc_<rule_slug>(inputs: dict, rule: Rule) -> RuleResult

The `inputs` dict is built by the evaluator from BuildingProposal + Plot.
"""

from __future__ import annotations

from rules_engine.rules.base import (
    FAIL, INFO, MISSING_DATA, NA, PASS, Rule, RuleResult,
)
from rules_engine.rules.loader import get_nbc_config


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


def _is_high_rise(building_height: float, nbc: dict) -> bool:
    threshold = nbc["nbc"]["building_classification"]["high_rise"]["threshold_height_m"]
    return building_height >= threshold


# ── NBC evaluators ────────────────────────────────────────────────────────────

def evaluate_nbc_classification(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    threshold = nbc["nbc"]["building_classification"]["high_rise"]["threshold_height_m"]   # 15 m

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    classification = "High-rise" if bh >= threshold else "Low-rise"
    return _result(rule, INFO, required=float(threshold), actual=float(bh), unit="m",
                   note=f"Building classified as {classification} "
                        f"(threshold {threshold} m). All {classification.lower()} "
                        "provisions of NBC 2016 Part 4 apply.")


def evaluate_nbc_egress_exits(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    min_exits = nbc["nbc"]["egress"]["minimum_number_of_exits"]["residential"]   # 2

    exits = inputs.get("num_exits")
    if exits is None:
        return _result(rule, INFO, required=float(min_exits),
                       note=f"Number of exits not provided. Minimum required: {min_exits}.")

    status = PASS if exits >= min_exits else FAIL
    return _result(rule, status, required=float(min_exits), actual=float(exits),
                   note="" if status == PASS else
                   f"Only {exits} exit(s) declared; minimum {min_exits} required.")


def evaluate_nbc_egress_travel_distance(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    td_cfg = nbc["nbc"]["egress"]["travel_distance"]["max_distance_m"]

    sprinklered = inputs.get("is_sprinklered", False)
    max_td = td_cfg["sprinklered"] if sprinklered else td_cfg["non_sprinklered"]

    td = inputs.get("travel_distance")
    if td is None:
        return _result(rule, INFO, required=float(max_td), unit="m",
                       note=f"Travel distance not provided. "
                            f"Maximum allowed ({'sprinklered' if sprinklered else 'non-sprinklered'}): {max_td} m.")

    status = PASS if td <= max_td else FAIL
    return _result(rule, status, required=float(max_td), actual=float(td), unit="m",
                   note="" if status == PASS else
                   f"Travel distance {td} m exceeds maximum {max_td} m "
                   f"({'sprinklered' if sprinklered else 'non-sprinklered'}).")


def evaluate_nbc_egress_corridor_width(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    min_cw = nbc["nbc"]["egress"]["corridor_width"]["minimum_m"]   # 1.0 m

    cw = inputs.get("corridor_width")
    if cw is None:
        return _result(rule, INFO, required=float(min_cw), unit="m",
                       note=f"Corridor width not provided. Minimum required: {min_cw} m.")

    status = PASS if cw >= min_cw else FAIL
    return _result(rule, status, required=float(min_cw), actual=float(cw), unit="m")


def evaluate_nbc_staircase_width(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    sc_cfg = nbc["nbc"]["egress"]["staircase"]["minimum_width_m"]

    bh = inputs.get("building_height")
    sw = inputs.get("stair_width")

    if bh is None:
        return _missing(rule, "building_height")

    high_rise = _is_high_rise(bh, nbc)
    min_sw = sc_cfg["high_rise"] if high_rise else sc_cfg["low_rise"]
    tier = "high-rise" if high_rise else "low-rise"

    if sw is None:
        return _result(rule, INFO, required=float(min_sw), unit="m",
                       note=f"Staircase width not provided. "
                            f"Required for {tier} building ({bh} m): {min_sw} m.")

    status = PASS if sw >= min_sw else FAIL
    return _result(rule, status, required=float(min_sw), actual=float(sw), unit="m",
                   note="" if status == PASS else
                   f"Staircase width {sw} m < required {min_sw} m for {tier} building.")


def evaluate_nbc_staircase_tread_riser(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    sc = nbc["nbc"]["egress"]["staircase"]
    min_tread = sc["minimum_tread_mm"]   # 250 mm
    max_riser = sc["maximum_riser_mm"]   # 190 mm

    tread = inputs.get("tread_mm")
    riser = inputs.get("riser_mm")

    if tread is None and riser is None:
        return _result(rule, INFO,
                       note=f"Tread/riser not provided. Required: tread >= {min_tread} mm, riser <= {max_riser} mm.")

    fails = []
    if tread is not None and tread < min_tread:
        fails.append(f"tread {tread} mm < min {min_tread} mm")
    if riser is not None and riser > max_riser:
        fails.append(f"riser {riser} mm > max {max_riser} mm")

    if fails:
        return _result(rule, FAIL, note="; ".join(fails))
    return _result(rule, PASS, note=f"Tread {tread} mm and riser {riser} mm satisfy NBC requirements.")


def evaluate_nbc_staircase_headroom(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    min_hr = nbc["nbc"]["egress"]["staircase"]["minimum_headroom_m"]   # 2.2 m

    hr = inputs.get("stair_headroom")
    if hr is None:
        return _result(rule, INFO, required=float(min_hr), unit="m",
                       note=f"Staircase headroom not provided. Minimum required: {min_hr} m.")

    status = PASS if hr >= min_hr else FAIL
    return _result(rule, status, required=float(min_hr), actual=float(hr), unit="m")


def evaluate_nbc_door_width(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    min_dw = nbc["nbc"]["egress"]["door"]["minimum_width_m"]   # 0.9 m

    dw = inputs.get("door_width")
    if dw is None:
        return _result(rule, INFO, required=float(min_dw), unit="m",
                       note=f"Exit door width not provided. Minimum required: {min_dw} m.")

    status = PASS if dw >= min_dw else FAIL
    return _result(rule, status, required=float(min_dw), actual=float(dw), unit="m")


def evaluate_nbc_high_rise_fire_lift(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    trigger_h = nbc["nbc"]["high_rise_requirements"]["fire_lift"]["required_above_height_m"]   # 15 m

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    if bh < trigger_h:
        return _result(rule, NA, note=f"Height {bh} m < {trigger_h} m; fire lift not required.")

    has_fire_lift = inputs.get("has_fire_lift")
    if has_fire_lift is None:
        return _result(rule, INFO,
                       note=f"Building height {bh} m >= {trigger_h} m: "
                            "Fire lift is mandatory (NBC 2016 Part 4). Declare in proposal.")

    status = PASS if has_fire_lift else FAIL
    return _result(rule, status, required=1.0, actual=1.0 if has_fire_lift else 0.0,
                   note="" if has_fire_lift else "Fire lift is required but not declared.")


def evaluate_nbc_high_rise_firefighting_shaft(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    trigger_h = nbc["nbc"]["high_rise_requirements"]["firefighting_shaft"]["required_above_height_m"]   # 15 m
    frr       = nbc["nbc"]["high_rise_requirements"]["firefighting_shaft"]["fire_resistance_rating_minutes"]

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    if bh < trigger_h:
        return _result(rule, NA, note=f"Height {bh} m < {trigger_h} m; firefighting shaft not required.")

    has_shaft = inputs.get("has_firefighting_shaft")
    if has_shaft is None:
        return _result(rule, INFO,
                       note=f"Building height {bh} m >= {trigger_h} m: "
                            f"Firefighting shaft ({frr}-minute FRR) is mandatory. Declare in proposal.")

    status = PASS if has_shaft else FAIL
    return _result(rule, status, required=1.0, actual=1.0 if has_shaft else 0.0,
                   note="" if has_shaft else f"Firefighting shaft ({frr}-min FRR) required but not declared.")


def evaluate_nbc_high_rise_refuge_area(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    trigger_h  = nbc["nbc"]["high_rise_requirements"]["refuge_area"]["required_above_height_m"]   # 60 m
    min_pct    = nbc["nbc"]["high_rise_requirements"]["refuge_area"]["minimum_area_percent_of_floor"]  # 4 %

    bh = inputs.get("building_height")
    if bh is None:
        return _missing(rule, "building_height")

    if bh <= trigger_h:
        return _result(rule, NA, note=f"Height {bh} m <= {trigger_h} m; NBC refuge area not triggered.")

    pct = inputs.get("refuge_area_pct")
    if pct is None:
        return _result(rule, INFO, required=float(min_pct), unit="%",
                       note=f"Building height {bh} m > {trigger_h} m: "
                            f"Refuge area of minimum {min_pct} % of floor area is required (NBC).")

    status = PASS if pct >= min_pct else FAIL
    return _result(rule, status, required=float(min_pct), actual=float(pct), unit="%")


def evaluate_nbc_fire_separation(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    min_sep = nbc["nbc"]["fire_separation"]["minimum_separation_distance_m"]   # 6 m

    sep = inputs.get("fire_separation_distance")
    if sep is None:
        return _result(rule, INFO, required=float(min_sep), unit="m",
                       note=f"Fire separation distance not provided. Minimum required: {min_sep} m.")

    status = PASS if sep >= min_sep else FAIL
    return _result(rule, status, required=float(min_sep), actual=float(sep), unit="m")


def evaluate_nbc_compartmentation(inputs: dict, rule: Rule) -> RuleResult:
    nbc = get_nbc_config()
    min_rating = nbc["nbc"]["compartmentation"]["fire_door_rating_minutes"]   # 120 min

    rating = inputs.get("fire_door_rating")
    if rating is None:
        return _result(rule, INFO, required=float(min_rating), unit="min",
                       note=f"Fire door rating not provided. "
                            f"Required minimum: {min_rating} minutes (NBC 2016 Part 4).")

    status = PASS if rating >= min_rating else FAIL
    return _result(rule, status, required=float(min_rating), actual=float(rating), unit="min")


# ── Dispatch table ────────────────────────────────────────────────────────────

NBC_EVALUATORS = {
    "nbc.classification":                evaluate_nbc_classification,
    "nbc.egress.exits":                  evaluate_nbc_egress_exits,
    "nbc.egress.travel_distance":        evaluate_nbc_egress_travel_distance,
    "nbc.egress.corridor_width":         evaluate_nbc_egress_corridor_width,
    "nbc.staircase.width":               evaluate_nbc_staircase_width,
    "nbc.staircase.tread_riser":         evaluate_nbc_staircase_tread_riser,
    "nbc.staircase.headroom":            evaluate_nbc_staircase_headroom,
    "nbc.door.width":                    evaluate_nbc_door_width,
    "nbc.high_rise.fire_lift":           evaluate_nbc_high_rise_fire_lift,
    "nbc.high_rise.firefighting_shaft":  evaluate_nbc_high_rise_firefighting_shaft,
    "nbc.high_rise.refuge_area":         evaluate_nbc_high_rise_refuge_area,
    "nbc.fire_separation":               evaluate_nbc_fire_separation,
    "nbc.compartmentation":              evaluate_nbc_compartmentation,
}
