"""
services/evaluator.py
---------------------
Orchestrates the full compliance evaluation for a BuildingProposal.

Flow
----
1. Build an `inputs` dict from the BuildingProposal + its linked Plot.
2. Retrieve every Rule from the catalogue (loader.get_all_rules).
3. Call the appropriate GDCR or NBC evaluator for each rule.
4. Return a list of RuleResult objects, one per rule.

The evaluator is intentionally free of Django ORM writes — persistence is
handled by the management command so the evaluator can be unit-tested
standalone.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from rules_engine.rules.base import MISSING_DATA, RuleResult
from rules_engine.rules.gdcr_rules import GDCR_EVALUATORS
from rules_engine.rules.loader import get_all_rules
from rules_engine.rules.nbc_rules import NBC_EVALUATORS
from architecture.regulatory.fsi_policy import infer_authority, infer_zone_from_plot

logger = logging.getLogger(__name__)

# Combined dispatch: rule_id → evaluator callable
_ALL_EVALUATORS = {**GDCR_EVALUATORS, **NBC_EVALUATORS}


def build_inputs(proposal) -> Dict:
    """
    Flatten a BuildingProposal (Django model instance) + its linked Plot
    into a plain dict that every evaluator can consume.

    All area values stored in the DB are in sq.ft (same unit as the DXF).
    Heights and widths are in metres.
    """
    plot = proposal.plot

    inputs: Dict = {
        # ── From Plot ────────────────────────────────────────────────────────
        "plot_area":       plot.area_geometry,       # sq.ft (DXF unit)
        "plot_area_excel": plot.area_excel,          # sq.ft (Excel stated)
        "fp_number":       plot.fp_number,

        # ── From BuildingProposal ────────────────────────────────────────────
        "road_width":       proposal.road_width,          # m
        "building_height":  proposal.building_height,     # m
        "total_bua":        proposal.total_bua,           # sq.ft
        "num_floors":       proposal.num_floors,
        "ground_coverage":  proposal.ground_coverage,     # sq.ft
        "has_basement":     proposal.has_basement,
        "is_sprinklered":   proposal.is_sprinklered,
        "has_lift":         proposal.has_lift,
        "authority":        infer_authority(),
        "zone":             infer_zone_from_plot(plot),
    }

    # Optional fields — only add when not None so evaluators can distinguish
    # "provided but zero" from "not provided at all"
    _optional = {
        "side_margin":              proposal.side_margin,
        "rear_margin":              proposal.rear_margin,
        "stair_width":              proposal.stair_width,
        "tread_mm":                 proposal.tread_mm,
        "riser_mm":                 proposal.riser_mm,
        "stair_headroom":           proposal.stair_headroom,
        "window_area":              proposal.window_area,
        "floor_area":               proposal.floor_area,
        "room_height":              proposal.room_height,
        "bathroom_height":          proposal.bathroom_height,
        "basement_height":          proposal.basement_height,
        "wall_height_road_side":    proposal.wall_height_road_side,
        "wall_height_other_side":   proposal.wall_height_other_side,
        "num_exits":                proposal.num_exits,
        "corridor_width":           proposal.corridor_width,
        "door_width":               proposal.door_width,
        "travel_distance":          proposal.travel_distance,
        "fire_separation_distance": proposal.fire_separation_distance,
        "fire_door_rating":         proposal.fire_door_rating,
        "has_fire_lift":            proposal.has_fire_lift,
        "has_firefighting_shaft":   proposal.has_firefighting_shaft,
        "refuge_area_pct":          proposal.refuge_area_pct,
        "distance_to_wide_road":    proposal.distance_to_wide_road,
    }
    for key, val in _optional.items():
        if val is not None:
            inputs[key] = val

    return inputs


def build_inputs_from_dict(plot_area: float, params: Dict) -> Dict:
    """
    Build an inputs dict directly from a plain parameter dict (used by the
    management command when no DB record is involved yet).

    Parameters
    ----------
    plot_area : geometry area of the FP plot in sq.ft
    params    : all other proposal parameters as key-value pairs
    """
    inputs = {"plot_area": plot_area}
    inputs.update(params)
    return inputs


def evaluate_all(inputs: Dict) -> List[RuleResult]:
    """
    Evaluate every rule in the catalogue against the given inputs dict.

    Returns
    -------
    List[RuleResult] — one result per rule, in catalogue order.
    """
    rules     = get_all_rules()
    results: List[RuleResult] = []

    for rule_id, rule in rules.items():
        evaluator = _ALL_EVALUATORS.get(rule_id)
        if evaluator is None:
            logger.warning("No evaluator registered for rule '%s' — skipping.", rule_id)
            continue
        try:
            result = evaluator(inputs, rule)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error evaluating rule '%s': %s", rule_id, exc)
            results.append(RuleResult(
                rule_id=rule_id, source=rule.source, category=rule.category,
                description=rule.description, status=MISSING_DATA,
                note=f"Evaluation error: {exc}",
            ))

    logger.info(
        "Evaluated %d rules — PASS: %d, FAIL: %d, INFO: %d, NA: %d, MISSING_DATA: %d",
        len(results),
        sum(1 for r in results if r.status == "PASS"),
        sum(1 for r in results if r.status == "FAIL"),
        sum(1 for r in results if r.status == "INFO"),
        sum(1 for r in results if r.status == "NA"),
        sum(1 for r in results if r.status == "MISSING_DATA"),
    )
    return results
