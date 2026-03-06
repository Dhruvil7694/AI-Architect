"""
geometry/margin_resolver.py
----------------------------
Resolves the required GDCR setback margin for each EdgeSpec in-place.

Rules applied
-------------
ROAD edges — Table 6.24 (CGDCR 2017):
    margin = max(road_width_based_lookup(road_width), building_height / 5)
    floor at minimum_road_side_margin (1.5 m)

SIDE / REAR edges — Table 6.26:
    margin = height_margin_map lookup (3 / 4 / 6 / 8 m by height bracket)

All margins are resolved in metres and then converted to DXF units:
    margin_dxf = margin_m * METRES_TO_DXF

Each EdgeSpec is updated in-place with:
    gdcr_clause        — the GDCR table reference for audit
    required_margin_m  — margin in metres
    required_margin_dxf — margin in DXF feet
"""

from __future__ import annotations

from typing import List

from envelope_engine.geometry import METRES_TO_DXF
from envelope_engine.geometry.edge_classifier import REAR, ROAD, SIDE, EdgeSpec
from rules_engine.rules.loader import get_gdcr_config


def _road_margin_from_width(road_width: float, gdcr: dict) -> float:
    """
    Look up the road-side margin from Table 6.24 based on road width (metres).
    Returns the tabulated value (before comparing with H/5).
    """
    margin_map = gdcr["road_side_margin"]["road_width_margin_map"]
    for entry in margin_map:
        if road_width <= entry["road_max"]:
            return float(entry["margin"])
    return float(margin_map[-1]["margin"])


def _side_rear_margin_from_height(building_height: float, gdcr: dict) -> float:
    """
    Look up the side / rear margin from Table 6.26 based on building height (metres).
    """
    margin_map = gdcr["side_rear_margin"]["height_margin_map"]
    for entry in margin_map:
        if building_height <= entry["height_max"]:
            return float(entry["side"])   # side == rear in CGDCR 2017
    return float(margin_map[-1]["side"])


def resolve_margins(
    edge_specs: List[EdgeSpec],
    building_height: float,
) -> List[EdgeSpec]:
    """
    Populate `gdcr_clause`, `required_margin_m`, and `required_margin_dxf`
    on every EdgeSpec in the list.  Modifies in-place and also returns the
    list for convenient chaining.

    Parameters
    ----------
    edge_specs      : classified list from edge_classifier.classify_edges()
    building_height : proposed building height in metres

    Returns
    -------
    The same list with margin fields filled in.
    """
    gdcr = get_gdcr_config()
    min_road_margin = float(gdcr["road_side_margin"]["minimum_road_side_margin"])

    for spec in edge_specs:
        if spec.edge_type == ROAD:
            road_width = spec.road_width or 9.0   # fallback if not declared
            table_margin = _road_margin_from_width(road_width, gdcr)
            height_margin = building_height / 5.0
            margin_m = max(table_margin, height_margin, min_road_margin)
            spec.gdcr_clause = "GDCR Table 6.24"

        else:   # SIDE or REAR — same lookup table in CGDCR 2017
            margin_m = _side_rear_margin_from_height(building_height, gdcr)
            spec.gdcr_clause = "GDCR Table 6.26"

        spec.required_margin_m   = round(margin_m, 4)
        spec.required_margin_dxf = round(margin_m * METRES_TO_DXF, 6)

    return edge_specs


def margin_audit_log(edge_specs: List[EdgeSpec]) -> list:
    """
    Return a serialisable list of dicts describing every edge margin.
    Stored in PlotEnvelope.edge_margin_audit (JSONField).
    """
    return [
        {
            "edge_index":        spec.index,
            "edge_type":         spec.edge_type,
            "p1":                list(spec.p1),
            "p2":                list(spec.p2),
            "length_dxf":        round(spec.length, 4),
            "road_width_m":      spec.road_width,
            "margin_m":          spec.required_margin_m,
            "margin_dxf":        spec.required_margin_dxf,
            "gdcr_clause":       spec.gdcr_clause,
        }
        for spec in edge_specs
    ]
