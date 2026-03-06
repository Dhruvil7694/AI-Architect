"""
placement_engine/geometry/packer.py
------------------------------------
Sequential multi-tower packing with two competing strategies:

  ROW_WISE  — uses the dual-orientation test on each remaining polygon.
              The inscribed rectangle naturally follows the polygon's own
              principal axis at each iteration.

  COL_WISE  — forces the PERPENDICULAR orientation (secondary angle) for
              EVERY tower.  This biases toward the cross-axis direction,
              exposing layouts that ROW_WISE misses when the envelope is
              wider than it is tall.

Both strategies are run to completion independently.  The winner is selected
by:
  1. More towers placed wins.
  2. Tie: larger total footprint area wins.
  3. Tie: ROW_WISE wins (deterministic fallback).

At each iteration the packer:
  a. Calls find_best_in_components() — handles Polygon and MultiPolygon.
  b. Adds the FULL H/3 exclusion zone (spacing_enforcer.compute_exclusion_zone).
  c. Subtracts the exclusion zone from the remaining envelope.
  d. Extracts valid components for the next iteration.

After the winning strategy is chosen, spacing_enforcer.audit_spacing() runs
an independent post-placement gap check for every pair of placed towers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from placement_engine.geometry import (
    MAX_TOWERS,
    MIN_FOOTPRINT_AREA_SQFT,
    FootprintCandidate,
)
from placement_engine.geometry.multipolygon_handler import find_best_in_components
from placement_engine.geometry.spacing_enforcer import (
    compute_exclusion_zone,
    audit_spacing,
    any_spacing_fail,
)
from placement_engine.geometry.orientation_finder import find_orientation


@dataclass
class PackingResult:
    """Output of pack_towers()."""
    mode:             str                       # "ROW_WISE" | "COL_WISE"
    footprints:       list[FootprintCandidate]  # ordered by placement sequence
    n_placed:         int
    total_area_sqft:  float
    spacing_audit:    list[dict]
    has_spacing_fail: bool


def pack_towers(
    envelope:           Polygon,
    n_towers:           int,
    building_height_m:  float,
    min_width_dxf:      float,
    min_depth_dxf:      float,
) -> PackingResult:
    """
    Place up to *n_towers* buildings inside *envelope* deterministically.

    Runs ROW_WISE and COL_WISE strategies, compares outcomes, returns the winner.

    Parameters
    ----------
    envelope          : Legal buildable envelope polygon (DXF feet, SRID=0).
    n_towers          : Number of buildings requested (capped at MAX_TOWERS).
    building_height_m : Building height in metres (drives H/3 spacing).
    min_width_dxf     : Minimum footprint width (DXF feet).
    min_depth_dxf     : Minimum footprint depth (DXF feet).

    Returns
    -------
    PackingResult — the winning strategy's outcome with spacing audit.
    """
    n_towers = min(n_towers, MAX_TOWERS)

    # Determine the primary/secondary orientations from the envelope once
    orient = find_orientation(envelope)

    row_result = _run_packing(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        force_angle=None,                          # dual-orientation per step
        mode="ROW_WISE",
    )

    col_result = _run_packing(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        force_angle=orient.angle_secondary_deg,    # force perpendicular
        mode="COL_WISE",
    )

    winner = _select_packing_winner(row_result, col_result)

    # Post-placement gap audit on the winner's placed footprints
    placed_polygons = [c.footprint_polygon for c in winner.footprints]
    audit = audit_spacing(placed_polygons, building_height_m)
    fail  = any_spacing_fail(audit)

    return PackingResult(
        mode=winner.mode,
        footprints=winner.footprints,
        n_placed=winner.n_placed,
        total_area_sqft=winner.total_area_sqft,
        spacing_audit=audit,
        has_spacing_fail=fail,
    )


# ── Internal packing loop ──────────────────────────────────────────────────────

def _run_packing(
    envelope:           Polygon,
    n_towers:           int,
    building_height_m:  float,
    min_width_dxf:      float,
    min_depth_dxf:      float,
    force_angle:        Optional[float],
    mode:               str,
) -> PackingResult:
    """Run one complete packing strategy and return its result."""
    remaining: BaseGeometry = envelope
    footprints: list[FootprintCandidate] = []

    for _i in range(n_towers):
        if remaining is None or remaining.is_empty:
            break
        if remaining.area < MIN_FOOTPRINT_AREA_SQFT:
            break

        candidate = find_best_in_components(
            geom=remaining,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            force_angle=force_angle,
            min_area_sqft=MIN_FOOTPRINT_AREA_SQFT,
        )

        if candidate is None:
            break

        footprints.append(candidate)

        # Subtract FULL H/3 exclusion zone so the next tower respects spacing
        exclusion = compute_exclusion_zone(candidate.footprint_polygon, building_height_m)
        remaining = remaining.difference(exclusion)

    total_area = sum(c.area_sqft for c in footprints)

    return PackingResult(
        mode=mode,
        footprints=footprints,
        n_placed=len(footprints),
        total_area_sqft=total_area,
        spacing_audit=[],       # filled in by pack_towers after winner selected
        has_spacing_fail=False,
    )


def _select_packing_winner(a: PackingResult, b: PackingResult) -> PackingResult:
    """
    Select the better packing result using the three-rule priority:
      1. More towers placed wins.
      2. Tie: larger total footprint area wins.
      3. Tie: ROW_WISE wins.
    """
    if a.n_placed != b.n_placed:
        return a if a.n_placed > b.n_placed else b

    if abs(a.total_area_sqft - b.total_area_sqft) > 0.01:
        return a if a.total_area_sqft > b.total_area_sqft else b

    # Absolute tie — ROW_WISE is more conservative and preferred
    return a if a.mode == "ROW_WISE" else b
