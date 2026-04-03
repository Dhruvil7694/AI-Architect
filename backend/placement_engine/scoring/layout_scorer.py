"""
placement_engine/scoring/layout_scorer.py
------------------------------------------
Layout quality scorer for post-packing strategy comparison.

Evaluates the spatial quality of a completed packing result using five
architectural metrics. Used by packer.py to select the best strategy when
multiple strategies place the same number of towers (n_placed tied).

Score formula (weights sum to 1.0):

    composite = 0.25 * orientation_quality
              + 0.25 * open_space_balance
              + 0.20 * courtyard_quality
              + 0.15 * frontage_exposure
              + 0.15 * tower_separation_bonus

Fire access is a HARD CONSTRAINT (validated in hard_constraints.py) and is
no longer part of the scoring system.

All metrics are in [0, 1], higher = better spatial quality.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from envelope_engine.geometry import METRES_TO_DXF

if TYPE_CHECKING:
    from placement_engine.geometry.packer import PackingResult

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
FIRE_ACCESS_M = 6.0
FIRE_ACCESS_DXF = FIRE_ACCESS_M * METRES_TO_DXF

_WEIGHTS = {
    "orientation_quality":    0.25,
    "open_space_balance":     0.25,
    "courtyard_quality":      0.20,
    "frontage_exposure":      0.15,
    "tower_separation_bonus": 0.15,
}


@dataclass
class LayoutQualityScore:
    """Individual and composite layout quality scores."""
    orientation_quality:    float   # alignment to road ±5° (1.0 = perfect)
    open_space_balance:     float   # open area evenly distributed around towers
    courtyard_quality:      float   # Polsby-Popper of largest leftover component
    frontage_exposure:      float   # unobstructed perimeter fraction
    tower_separation_bonus: float   # actual gap / required gap (capped at 1.0)

    composite: float = field(init=False)

    def __post_init__(self) -> None:
        self.composite = round(sum(
            _WEIGHTS[k] * getattr(self, k) for k in _WEIGHTS
        ), 6)


def score_layout(
    packing_result: "PackingResult",
    envelope_polygon: Polygon,
    road_edge_angles_deg: Optional[List[float]] = None,
) -> LayoutQualityScore:
    """
    Compute the composite spatial quality score for a completed packing.

    Parameters
    ----------
    packing_result        : Completed PackingResult from _run_packing().
    envelope_polygon      : Buildable envelope (DXF feet, SRID=0).
    road_edge_angles_deg  : Road edge direction angles — used to orient the
                            bisect axis for open_space_balance.  None → use
                            envelope's own principal axis.

    Returns
    -------
    LayoutQualityScore with individual metrics and composite.
    """
    footprints = [fc.footprint_polygon for fc in packing_result.footprints
                  if getattr(fc, "footprint_polygon", None) is not None]

    if not footprints:
        return LayoutQualityScore(
            orientation_quality=0.0,
            open_space_balance=0.0,
            courtyard_quality=0.0,
            frontage_exposure=0.0,
            tower_separation_bonus=1.0,
        )

    try:
        from shapely.ops import unary_union
        tower_union = unary_union(footprints)
    except Exception:
        tower_union = footprints[0]

    # Get tower angles from FootprintCandidate objects
    tower_angles = [
        getattr(fc, "orientation_angle_deg", 0.0)
        for fc in packing_result.footprints
    ]

    oq  = _orientation_quality(tower_angles, road_edge_angles_deg)
    osb = _open_space_balance(tower_union, envelope_polygon, road_edge_angles_deg)
    tsb = _tower_separation_bonus(packing_result.spacing_audit)
    cq  = _courtyard_quality(tower_union, envelope_polygon)
    fe  = _frontage_exposure(footprints, tower_union, envelope_polygon)

    score = LayoutQualityScore(
        orientation_quality=oq,
        open_space_balance=osb,
        courtyard_quality=cq,
        frontage_exposure=fe,
        tower_separation_bonus=tsb,
    )
    logger.debug(
        "LayoutScore [%s]: oq=%.3f osb=%.3f cq=%.3f fe=%.3f tsb=%.3f → %.3f",
        packing_result.mode, oq, osb, cq, fe, tsb, score.composite,
    )
    return score


# ── Individual metric functions ────────────────────────────────────────────────

def _open_space_balance(
    tower_union: BaseGeometry,
    envelope: Polygon,
    road_edge_angles_deg: Optional[List[float]],
) -> float:
    """
    Measures how evenly the open space is distributed on each side of the
    towers relative to the envelope's bisect axis.

    1.0 = perfectly balanced; 0.0 = all open space on one side.
    """
    try:
        centroid = envelope.centroid
        cx, cy = centroid.x, centroid.y

        # Determine bisect axis direction
        if road_edge_angles_deg:
            # Road edge angle is the direction of the road — bisect perpendicularly
            avg_road_angle = sum(road_edge_angles_deg) / len(road_edge_angles_deg)
            bisect_angle = math.radians(avg_road_angle + 90.0)
        else:
            # Use the envelope's principal axis (MBR long axis)
            mbr = envelope.minimum_rotated_rectangle
            coords = list(mbr.exterior.coords)
            dx = coords[1][0] - coords[0][0]
            dy = coords[1][1] - coords[0][1]
            bisect_angle = math.atan2(dy, dx)

        # Perpendicular to bisect axis — this is the split direction
        split_nx = -math.sin(bisect_angle)
        split_ny =  math.cos(bisect_angle)

        open_space = envelope.difference(tower_union)
        if open_space.is_empty:
            return 1.0

        open_area = open_space.area
        if open_area <= 0:
            return 1.0

        geoms = (list(open_space.geoms)
                 if hasattr(open_space, "geoms") else [open_space])

        left_area = right_area = 0.0
        for g in geoms:
            gc = g.centroid
            dot = (gc.x - cx) * split_nx + (gc.y - cy) * split_ny
            if dot >= 0:
                left_area += g.area
            else:
                right_area += g.area

        total = left_area + right_area
        if total <= 0:
            return 1.0

        imbalance = abs(left_area - right_area) / total
        return round(max(0.0, 1.0 - imbalance), 6)

    except Exception:
        return 0.5  # neutral if computation fails


def _tower_separation_bonus(spacing_audit: list) -> float:
    """
    Measures whether towers have MORE spacing than required (bonus space = better).

    1.0 = all pairs at 2× required or more; 0.0 = at minimum.
    Single tower: returns 1.0 (no inter-tower concern).
    """
    if not spacing_audit:
        return 1.0

    try:
        bonuses = []
        for entry in spacing_audit:
            gap_m      = float(entry.get("gap_m", 0.0))
            required_m = float(entry.get("required_m", 1.0)) or 1.0
            ratio  = gap_m / required_m          # 1.0 = exactly at minimum
            bonus  = min(1.0, max(0.0, ratio - 1.0))  # 0 at min, 1.0 at 2× required
            bonuses.append(bonus)

        return round(sum(bonuses) / len(bonuses), 6) if bonuses else 1.0
    except Exception:
        return 0.5


def _courtyard_quality(tower_union: BaseGeometry, envelope: Polygon) -> float:
    """
    Polsby-Popper compactness of the largest leftover space component.

    1.0 = circular/compact courtyard; 0.0 = degenerate sliver.
    """
    try:
        leftover = envelope.difference(tower_union)
        if leftover.is_empty or leftover.area < 1.0:
            return 0.0

        geoms = (list(leftover.geoms)
                 if hasattr(leftover, "geoms") else [leftover])
        largest = max(geoms, key=lambda g: g.area)

        perimeter = largest.length
        if perimeter <= 0:
            return 0.0

        pp = (4.0 * math.pi * largest.area) / (perimeter ** 2)
        return round(min(1.0, max(0.0, pp)), 6)
    except Exception:
        return 0.0


def _orientation_quality(
    tower_angles_deg: List[float],
    road_edge_angles_deg: Optional[List[float]],
) -> float:
    """
    Measures how well towers align to road-aligned or orthogonal orientations.

    1.0 = all towers perfectly aligned; 0.0 = all at 45° (worst).
    Returns 0.5 (neutral) if no road info is available.
    """
    if not road_edge_angles_deg or not tower_angles_deg:
        return 0.5

    try:
        scores = []
        for tower_angle in tower_angles_deg:
            best_deviation = 45.0  # worst case
            for road_angle in road_edge_angles_deg:
                diff = abs(tower_angle - road_angle) % 180.0
                deviation = min(diff % 90.0, 90.0 - diff % 90.0)
                best_deviation = min(best_deviation, deviation)
            # 0° deviation → 1.0; 45° deviation → 0.0
            scores.append(max(0.0, 1.0 - best_deviation / 45.0))

        return round(sum(scores) / len(scores), 6) if scores else 0.5
    except Exception:
        return 0.5


def _frontage_exposure(
    footprints: list,
    tower_union: BaseGeometry,
    envelope: Polygon,
) -> float:
    """
    Measures what fraction of each tower's perimeter has an unobstructed
    view (not facing another tower within 6m).

    1.0 = all perimeter unobstructed; 0.0 = fully enclosed.
    """
    if not footprints:
        return 0.5

    try:
        scores = []
        for fp in footprints:
            perimeter = fp.length
            if perimeter <= 0:
                scores.append(0.5)
                continue

            # Buffer the footprint by 6m and check what's blocked by other towers
            buffer_dxf = FIRE_ACCESS_DXF
            buffered = fp.buffer(buffer_dxf)

            # Other towers = tower_union minus this tower
            other_towers = tower_union.difference(fp)
            if other_towers.is_empty:
                scores.append(1.0)
                continue

            # Blocked = intersection of buffered zone with other towers
            blocked = buffered.intersection(other_towers)
            blocked_length = blocked.length if not blocked.is_empty else 0.0

            # Approximate: ratio of blocked boundary to total perimeter
            exposure = max(0.0, 1.0 - blocked_length / (perimeter * 2.0))
            scores.append(min(1.0, exposure))

        return round(sum(scores) / len(scores), 6) if scores else 0.5
    except Exception:
        return 0.5
