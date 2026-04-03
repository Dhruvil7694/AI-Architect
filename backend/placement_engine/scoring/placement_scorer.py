"""
placement_engine/scoring/placement_scorer.py
--------------------------------------------
Lightweight architectural scoring layer that ranks rectangle candidates
produced by the inscribed-rectangle solver.

The solver already finds a high-quality maximum rectangle; this module
selects the best one when multiple candidates exist using spatial heuristics.

Score formula (weights sum to 1.0):

    score = 0.50 * area_ratio
          + 0.20 * edge_contact_score
          + 0.10 * road_alignment_score
          + 0.10 * open_space_compactness_score
          + 0.10 * open_space_consolidation

Definitions
-----------
area_ratio
    candidate.area_sqft / max_area_sqft  (largest candidate in the pool = 1.0)

edge_contact_score
    1.0 when the footprint touches the available polygon boundary.
    Decreases linearly as the footprint moves further inside.
    Normalised by half the diagonal of the available polygon bounding box.

road_alignment_score
    1.0 when the rectangle long axis is perpendicular to the road edge.
    0.0 when parallel.  Returns 0.5 (neutral) when road info is absent.

open_space_compactness_score
    Polsby-Popper score (4*pi*A / P^2) of the leftover polygon after
    placing the candidate inside the available space.  1.0 = circle (ideal),
    0.0 = degenerate sliver.

Tie-breaking rule (Step 6)
--------------------------
If the top two scores differ by less than TIE_THRESHOLD (0.02), the
candidate with larger area is preferred.  This prevents a minor heuristic
advantage from overriding significantly more floor area.
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional

from shapely.geometry.base import BaseGeometry

from placement_engine.geometry import FootprintCandidate

logger = logging.getLogger(__name__)

# ── Score weights ──────────────────────────────────────────────────────────────
W_AREA            = 0.25  # Reduced from 0.35 to make room for COP
W_EDGE            = 0.15  # Reduced from 0.20
W_ROAD            = 0.10
W_COMPACTNESS     = 0.10
W_CONSOLIDATION   = 0.10
W_PLATE           = 0.05
W_DEPTH           = 0.05  # Reduced from 0.10
W_COP             = 0.20  # NEW: COP proximity weight

# Small bonus applied when the tower shares a meaningful edge with the envelope
EDGE_ALIGNMENT_THRESHOLD = 0.20   # 20% of perimeter
EDGE_ALIGNMENT_BONUS     = 0.03   # small additive bump

# Near-tie threshold — if two top scores are within this margin, prefer area
TIE_THRESHOLD = 0.02


# ── Helper functions ───────────────────────────────────────────────────────────


def _cop_proximity_score(
    footprint_polygon: BaseGeometry,
    cop_centroid: tuple,
    available_polygon: BaseGeometry,
) -> float:
    """
    Score tower proximity to COP: 1.0 = adjacent/touching, 0.0 = far away.
    
    This encourages towers to face or be near the COP, making it a functional
    amenity space rather than a disconnected leftover.
    """
    try:
        fp_cx, fp_cy = footprint_polygon.centroid.x, footprint_polygon.centroid.y
        cop_cx, cop_cy = cop_centroid
        
        # Distance from footprint centroid to COP centroid
        dist = math.sqrt((fp_cx - cop_cx)**2 + (fp_cy - cop_cy)**2)
        
        # Normalize by available polygon diagonal
        bounds = available_polygon.bounds
        diag = math.sqrt((bounds[2] - bounds[0])**2 + (bounds[3] - bounds[1])**2)
        
        if diag == 0:
            return 0.5
        
        # Score: 1.0 at distance=0, 0.0 at distance=diag
        score = 1.0 - min(dist / diag, 1.0)
        
        return score
    except Exception:
        return 0.5  # neutral default on error


# ── Public API ─────────────────────────────────────────────────────────────────

def score_candidate(
    candidate: FootprintCandidate,
    available_polygon: BaseGeometry,
    max_area_sqft: float,
    road_edge_angles_deg: Optional[List[float]],
    target_plate_area_sqft: Optional[float] = None,
    preferred_depth_m: Optional[float] = None,
    cop_polygon: Optional[BaseGeometry] = None,  # NEW
    cop_centroid: Optional[tuple] = None,  # NEW
) -> float:
    """
    Compute the composite architectural score for a single candidate footprint.

    Parameters
    ----------
    candidate            : Footprint candidate from the inscribed-rectangle solver.
    available_polygon    : Current remaining buildable polygon (Polygon or MultiPolygon).
    max_area_sqft        : Area of the largest candidate in the pool (for normalisation).
    road_edge_angles_deg : Road-edge direction angles in degrees, or None/[] if unknown.
    cop_polygon          : COP polygon for proximity scoring (optional).
    cop_centroid         : COP centroid (x, y) for distance calculation (optional).

    Returns
    -------
    Float score in approximately [0.0, 1.0].
    """
    fp = candidate.footprint_polygon

    # 1. Area ratio — primary driver
    area_ratio = candidate.area_sqft / max_area_sqft if max_area_sqft > 0 else 0.0

    # 2. Edge contact — prefer rectangles touching the available space boundary
    edge_score = _edge_contact_score(fp, available_polygon)

    # 3. Road alignment — prefer long axis perpendicular to road
    road_score = _road_alignment_score(candidate, road_edge_angles_deg)

    # 4. Open space compactness — compact leftover means cleaner open space
    compact_score = _open_space_compactness_score(fp, available_polygon)

    # 5. Open space consolidation — prefer one dominant open space component
    consolidation_score = _open_space_consolidation_score(fp, available_polygon)

    # 6. Plate area score — prefer candidates close to the target plate area.
    plate_score = 0.0
    if target_plate_area_sqft and target_plate_area_sqft > 0:
        plate_score = _plate_area_score(candidate.area_sqft, target_plate_area_sqft)

    # 7. Depth score — prefer candidates whose shorter side matches preferred depth.
    depth_score = 0.0
    if preferred_depth_m and preferred_depth_m > 0.0:
        depth_score = _depth_score(candidate, preferred_depth_m)

    # 8. COP proximity score — prefer towers close to COP (NEW)
    cop_score = 0.5  # neutral default
    if cop_centroid is not None:
        cop_score = _cop_proximity_score(fp, cop_centroid, available_polygon)

    # 9. Edge alignment ratio — share of footprint perimeter lying on envelope
    edge_alignment_ratio = _edge_alignment_ratio(fp, available_polygon)
    edge_bonus = EDGE_ALIGNMENT_BONUS if edge_alignment_ratio > EDGE_ALIGNMENT_THRESHOLD else 0.0

    total = (
        W_AREA          * area_ratio
        + W_EDGE        * edge_score
        + W_ROAD        * road_score
        + W_COMPACTNESS * compact_score
        + W_CONSOLIDATION * consolidation_score
        + W_PLATE       * plate_score
        + W_DEPTH       * depth_score
        + W_COP         * cop_score  # NEW
        + edge_bonus
    )

    logger.debug(
        "  Candidate angle=%6.1f° %-14s "
        "area=%.0f area_ratio=%.3f edge=%.3f road=%.3f "
        "compact=%.3f consolidate=%.3f plate=%.3f depth=%.3f cop=%.3f edge_align=%.3f bonus=%.3f → score=%.4f",
        candidate.orientation_angle_deg,
        f"({candidate.orientation_label})",
        candidate.area_sqft,
        area_ratio, edge_score, road_score,
        compact_score, consolidation_score, plate_score, depth_score, cop_score,
        edge_alignment_ratio, edge_bonus,
        total,
    )

    return round(total, 6)


def select_best_candidate(
    candidates: List[FootprintCandidate],
    available_polygon: BaseGeometry,
    road_edge_angles_deg: Optional[List[float]] = None,
    target_plate_area_sqft: Optional[float] = None,
    preferred_depth_m: Optional[float] = None,
    cop_polygon: Optional[BaseGeometry] = None,  # NEW
    cop_centroid: Optional[tuple] = None,  # NEW
) -> Optional[FootprintCandidate]:
    """
    Score all candidates and return the one with the highest composite score.

    Parameters
    ----------
    candidates           : Candidates sorted by area descending (Step 1 output).
    available_polygon    : Current remaining buildable polygon.
    road_edge_angles_deg : Road-edge direction angles in degrees (optional).
    cop_polygon          : COP polygon for proximity scoring (optional).
    cop_centroid         : COP centroid (x, y) for distance calculation (optional).

    Returns
    -------
    Best FootprintCandidate, or None if *candidates* is empty.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    max_area = candidates[0].area_sqft   # first is largest (sorted desc)

    logger.debug(
        "[Scorer] Evaluating %d candidates (max_area=%.0f sqft, road_angles=%s, target_plate_sqft=%s, preferred_depth_m=%s, cop=%s)",
        len(candidates), max_area,
        [round(a, 1) for a in (road_edge_angles_deg or [])],
        f"{target_plate_area_sqft:.0f}" if target_plate_area_sqft else "None",
        f"{preferred_depth_m:.2f}" if preferred_depth_m else "None",
        "YES" if cop_centroid else "NO",
    )

    scored: list[tuple[FootprintCandidate, float]] = [
        (
            c,
            score_candidate(
                c,
                available_polygon,
                max_area,
                road_edge_angles_deg,
                target_plate_area_sqft=target_plate_area_sqft,
                preferred_depth_m=preferred_depth_m,
                cop_polygon=cop_polygon,  # NEW
                cop_centroid=cop_centroid,  # NEW
            ),
        )
        for c in candidates
    ]
    scored.sort(key=lambda x: -x[1])

    best, best_score = scored[0]
    runner, runner_score = scored[1]

    # Near-tie: prefer larger footprint area (Step 6 rule)
    if abs(best_score - runner_score) < TIE_THRESHOLD and runner.area_sqft > best.area_sqft:
        logger.debug(
            "[Scorer] Near-tie (Δ=%.4f < %.2f) — prefer larger area "
            "candidate: %.0f vs %.0f sqft",
            abs(best_score - runner_score), TIE_THRESHOLD,
            runner.area_sqft, best.area_sqft,
        )
        return runner

    logger.debug(
        "[Scorer] Winner: angle=%.1f° area=%.0f sqft score=%.4f",
        best.orientation_angle_deg, best.area_sqft, best_score,
    )
    return best


# ── Private heuristic helpers ──────────────────────────────────────────────────

def _edge_contact_score(footprint, available: BaseGeometry) -> float:
    """
    Score in [0, 1]: 1.0 when footprint touches the available polygon boundary;
    decreases as the footprint moves further inside.

    Normalisation: distance / (0.5 * longest diagonal of bounding box).
    """
    try:
        boundary = available.boundary
        dist = footprint.distance(boundary)
        if dist <= 1e-6:              # touching — perfect score
            return 1.0
        minx, miny, maxx, maxy = available.bounds
        diagonal = math.hypot(maxx - minx, maxy - miny)
        if diagonal <= 0:
            return 0.0
        return round(max(0.0, 1.0 - dist / (diagonal * 0.5)), 6)
    except Exception:   # noqa: BLE001
        return 0.5      # neutral on geometry failure


def _road_alignment_score(
    candidate: FootprintCandidate,
    road_edge_angles_deg: Optional[List[float]],
) -> float:
    """
    Score in [0, 1]: 1.0 when rectangle long axis is perpendicular to the road.
    Returns 0.5 (neutral) when no road information is available.

    The rectangle's orientation_angle_deg is the direction of its long axis
    (or the angle at which the MBR was rotated for the grid solve).
    Preferred: long axis ⊥ road → angle_diff ≈ 90° from the road edge direction.
    """
    if not road_edge_angles_deg:
        return 0.5

    rect_angle = candidate.orientation_angle_deg % 180.0
    best = 0.0
    for road_angle in road_edge_angles_deg:
        road_angle = road_angle % 180.0
        diff = abs(rect_angle - road_angle) % 180.0
        # Deviation from 90° (perfect perpendicular); range [0°, 90°]
        deviation = abs(diff - 90.0)
        score = 1.0 - deviation / 90.0
        best = max(best, score)

    return round(best, 6)


def _open_space_compactness_score(footprint, available: BaseGeometry) -> float:
    """
    Polsby–Popper compactness (4*pi*A / P^2) of the leftover after placing
    *footprint* inside *available*.  1.0 = perfect circle, 0 = thin sliver.
    """
    try:
        leftover = available.difference(footprint)
        if leftover.is_empty:
            return 0.0
        area = leftover.area
        perimeter = leftover.length
        if perimeter <= 0:
            return 0.0
        pp = (4.0 * math.pi * area) / (perimeter ** 2)
        return round(min(1.0, max(0.0, pp)), 6)
    except Exception:   # noqa: BLE001
        return 0.0


def _open_space_consolidation_score(footprint, available: BaseGeometry) -> float:
    """
    Ratio of the largest leftover component area to the total leftover area
    after placing *footprint* inside *available*.

    1.0 → single dominant open space
    <0.5 → fragmented open spaces
    """
    try:
        leftover = available.difference(footprint)
        if leftover.is_empty:
            return 0.0

        # Collect polygon components
        geoms = []
        if getattr(leftover, "geom_type", None) == "Polygon":
            geoms = [leftover]
        else:
            geoms = [g for g in getattr(leftover, "geoms", []) if g.area > 0]

        if not geoms:
            return 0.0

        areas = [float(g.area) for g in geoms]
        total = sum(areas)
        if total <= 0.0:
            return 0.0
        largest = max(areas)
        ratio = largest / total
        return round(min(1.0, max(0.0, ratio)), 6)
    except Exception:  # noqa: BLE001
        return 0.0


def _edge_alignment_ratio(footprint, available: BaseGeometry) -> float:
    """
    Fraction of the footprint perimeter that lies on the available boundary.
    """
    try:
        perim = float(footprint.length)
        if perim <= 0.0:
            return 0.0
        boundary = available.boundary
        inter = footprint.boundary.intersection(boundary)
        overlap_len = float(inter.length)
        ratio = overlap_len / perim
        return round(min(1.0, max(0.0, ratio)), 6)
    except Exception:  # noqa: BLE001
        return 0.0


def _plate_area_score(candidate_area_sqft: float, target_area_sqft: float) -> float:
    """
    Score in [0, 1], highest when candidate area is close to target area.

    ratio = candidate / target
    score = 1 - abs(1 - ratio)
    """
    try:
        if target_area_sqft <= 0.0 or candidate_area_sqft <= 0.0:
            return 0.0
        ratio = candidate_area_sqft / target_area_sqft
        score = 1.0 - abs(1.0 - ratio)
        return round(max(0.0, min(1.0, score)), 6)
    except Exception:  # noqa: BLE001
        return 0.0


def _depth_score(candidate: FootprintCandidate, preferred_depth_m: float) -> float:
    """
    Score in [0, 1], highest when the shorter side of the footprint
    is close to the preferred band depth in metres.
    """
    try:
        if preferred_depth_m <= 0.0:
            return 0.0
        # candidate.width_m and depth_m are in metres.
        candidate_depth = min(float(candidate.width_m), float(candidate.depth_m))
        if candidate_depth <= 0.0:
            return 0.0
        ratio = candidate_depth / preferred_depth_m
        score = 1.0 - abs(1.0 - ratio)
        return round(max(0.0, min(1.0, score)), 6)
    except Exception:  # noqa: BLE001
        return 0.0
