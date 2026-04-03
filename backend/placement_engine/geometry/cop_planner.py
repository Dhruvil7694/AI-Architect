"""
placement_engine/geometry/cop_planner.py
-----------------------------------------
COP-FIRST planning module: generates and scores COP candidate regions
BEFORE tower placement, making COP a spatial planning driver rather than
a post-placement geometry artifact.

This module replaces the post-hoc COP carving approach with proactive
COP region selection that influences zoning and tower placement.

Algorithm
---------
1. Generate candidate COP regions (rear strip, central courtyard, side strips)
2. Score each candidate by: centrality, accessibility, compactness, residual buildability
3. Validate geometry: minimum dimension, aspect ratio (reject strips)
4. Return ranked list of viable COP candidates

Unit contract
-------------
All geometry in DXF feet (SRID=0), consistent with placement engine.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import LineString, MultiPolygon, Polygon, box

from envelope_engine.geometry.edge_classifier import REAR, ROAD, SIDE, EdgeSpec
from placement_engine.geometry import DXF_TO_METRES, METRES_TO_DXF
from common.units import metres_to_dxf

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class CopCandidate:
    """A candidate COP region with quality score."""
    polygon: Polygon
    area_sqft: float
    min_dimension_m: float
    aspect_ratio: float
    score: float
    label: str  # "REAR_STRIP" | "CENTER_COURTYARD" | "SIDE_STRIP"
    centroid: Tuple[float, float]


# ── Geometry validation ───────────────────────────────────────────────────────


def validate_cop_geometry(
    cop_polygon: Polygon,
    min_dimension_dxf: float,
    max_aspect_ratio: float = 3.0,
) -> Tuple[bool, str]:
    """
    Hard validation of COP geometry quality.

    Parameters
    ----------
    cop_polygon       : COP polygon to validate (DXF feet).
    min_dimension_dxf : Minimum bounding box dimension (DXF feet).
    max_aspect_ratio  : Maximum width/depth ratio (reject strips).

    Returns
    -------
    (is_valid, failure_reason)
    """
    if cop_polygon is None or cop_polygon.is_empty:
        return False, "COP polygon is empty"

    # Check minimum dimension (bounding box)
    minx, miny, maxx, maxy = cop_polygon.bounds
    width_dxf = maxx - minx
    depth_dxf = maxy - miny
    min_dim_dxf = min(width_dxf, depth_dxf)

    if min_dim_dxf < min_dimension_dxf:
        min_dim_m = min_dim_dxf * DXF_TO_METRES
        required_m = min_dimension_dxf * DXF_TO_METRES
        return False, f"COP min dimension {min_dim_m:.1f}m < required {required_m:.1f}m"

    # Check aspect ratio (reject strip-like shapes)
    if width_dxf > 0 and depth_dxf > 0:
        aspect = max(width_dxf, depth_dxf) / min(width_dxf, depth_dxf)
        if aspect > max_aspect_ratio:
            return False, f"COP aspect ratio {aspect:.1f} > max {max_aspect_ratio:.1f} (strip-like)"

    return True, ""


# ── COP candidate scoring ─────────────────────────────────────────────────────


def score_cop_region(
    cop_polygon: Polygon,
    buildable_core: Polygon,
    plot_polygon: Polygon,
    edge_specs: List[EdgeSpec],
) -> float:
    """
    Score COP candidate by architectural quality metrics.

    Scoring components
    ------------------
    - centrality (0.4)        : Proximity of COP centroid to buildable_core centroid
    - accessibility (0.3)     : Fraction of COP perimeter touching buildable_core
    - compactness (0.2)       : Aspect ratio quality (1.0 = square, 0.0 = strip)
    - residual_buildability (0.1) : Remaining core area after COP subtraction

    Parameters
    ----------
    cop_polygon      : Candidate COP polygon (DXF feet).
    buildable_core   : Buildable core polygon (DXF feet).
    plot_polygon     : Original plot polygon (DXF feet).
    edge_specs       : Classified edge specs.

    Returns
    -------
    score : float in [0.0, 1.0], higher is better.
    """
    if cop_polygon.is_empty or buildable_core.is_empty:
        return 0.0

    # ── Centrality: COP centroid proximity to buildable_core centroid ─────────
    cop_cx, cop_cy = cop_polygon.centroid.x, cop_polygon.centroid.y
    core_cx, core_cy = buildable_core.centroid.x, buildable_core.centroid.y

    diag = math.sqrt(
        (buildable_core.bounds[2] - buildable_core.bounds[0]) ** 2 +
        (buildable_core.bounds[3] - buildable_core.bounds[1]) ** 2
    )
    if diag == 0:
        centrality = 0.0
    else:
        dist = math.sqrt((cop_cx - core_cx) ** 2 + (cop_cy - core_cy) ** 2)
        centrality = 1.0 - min(dist / diag, 1.0)

    # ── Accessibility: fraction of COP perimeter touching buildable_core ──────
    try:
        # COP should be accessible from buildable area
        shared_boundary = cop_polygon.boundary.intersection(buildable_core.buffer(1.0))
        accessibility = shared_boundary.length / cop_polygon.length if cop_polygon.length > 0 else 0.0
        accessibility = min(accessibility, 1.0)
    except Exception:
        accessibility = 0.0

    # ── Compactness: aspect ratio quality (prefer square over strip) ──────────
    minx, miny, maxx, maxy = cop_polygon.bounds
    width = maxx - minx
    depth = maxy - miny
    if width > 0 and depth > 0:
        aspect = max(width, depth) / min(width, depth)
        # Map aspect ratio to [0, 1]: 1.0 → 1.0 (square), 3.0 → 0.5, 5.0+ → 0.0
        compactness = max(0.0, 1.0 - (aspect - 1.0) / 4.0)
    else:
        compactness = 0.0

    # ── Residual buildability: remaining core area after COP ─────────────────
    try:
        residual = buildable_core.difference(cop_polygon)
        residual_area = residual.area if not residual.is_empty else 0.0
        residual_ratio = residual_area / buildable_core.area if buildable_core.area > 0 else 0.0
        # Prefer COP that leaves 60-80% of core buildable
        if 0.6 <= residual_ratio <= 0.8:
            residual_score = 1.0
        elif residual_ratio > 0.8:
            residual_score = 0.8  # COP too small
        else:
            residual_score = residual_ratio / 0.6  # COP too large
    except Exception:
        residual_score = 0.0

    # ── Weighted final score ──────────────────────────────────────────────────
    score = (
        0.4 * centrality +
        0.3 * accessibility +
        0.2 * compactness +
        0.1 * residual_score
    )

    return score


# ── COP candidate generation ──────────────────────────────────────────────────


def _generate_rear_strip_candidate(
    plot_polygon: Polygon,
    buildable_core: Polygon,
    edge_specs: List[EdgeSpec],
    required_area_sqft: float,
    min_dimension_dxf: float,
) -> Optional[CopCandidate]:
    """Generate rear strip COP candidate (proven strategy)."""
    rear_specs = [s for s in edge_specs if s.edge_type == REAR]
    if not rear_specs:
        return None

    rear_spec = rear_specs[0]
    nx, ny = rear_spec.inward_normal

    # Project vertices to find max depth
    xs = [c[0] for c in plot_polygon.exterior.coords]
    ys = [c[1] for c in plot_polygon.exterior.coords]
    projections = [x * nx + y * ny for x, y in zip(xs, ys)]
    max_depth = (max(projections) - min(projections)) * 0.9

    # Bisect to find depth that gives required area
    from envelope_engine.geometry.common_plot_carver import _rear_strip_polygon

    lo, hi = 0.0, max_depth
    best_strip = None

    for _ in range(25):  # bisection iterations
        mid = (lo + hi) / 2.0
        strip = _rear_strip_polygon(plot_polygon, rear_spec, mid)
        strip_area = strip.area if not strip.is_empty else 0.0

        if strip_area < required_area_sqft:
            lo = mid
        else:
            hi = mid
            best_strip = strip

        if (hi - lo) < 1e-4:
            break

    # Enforce minimum dimension
    if hi < min_dimension_dxf:
        deeper = _rear_strip_polygon(plot_polygon, rear_spec, min_dimension_dxf)
        if not deeper.is_empty:
            best_strip = deeper

    if best_strip is None or best_strip.is_empty:
        return None

    if isinstance(best_strip, MultiPolygon):
        best_strip = max(best_strip.geoms, key=lambda g: g.area)

    # Clip to buildable_core (COP should be inside or adjacent to core)
    cop_geom = best_strip.intersection(plot_polygon)
    if cop_geom.is_empty:
        return None

    if isinstance(cop_geom, MultiPolygon):
        cop_geom = max(cop_geom.geoms, key=lambda g: g.area)

    # Compute metrics
    minx, miny, maxx, maxy = cop_geom.bounds
    width = maxx - minx
    depth = maxy - miny
    min_dim_m = min(width, depth) * DXF_TO_METRES
    aspect = max(width, depth) / min(width, depth) if min(width, depth) > 0 else 999.0

    score = score_cop_region(cop_geom, buildable_core, plot_polygon, edge_specs)

    return CopCandidate(
        polygon=cop_geom,
        area_sqft=cop_geom.area,
        min_dimension_m=min_dim_m,
        aspect_ratio=aspect,
        score=score,
        label="REAR_STRIP",
        centroid=(cop_geom.centroid.x, cop_geom.centroid.y),
    )


def _generate_center_courtyard_candidate(
    plot_polygon: Polygon,
    buildable_core: Polygon,
    edge_specs: List[EdgeSpec],
    required_area_sqft: float,
    min_dimension_dxf: float,
) -> Optional[CopCandidate]:
    """Generate central courtyard COP candidate (multi-tower layouts)."""
    minx, miny, maxx, maxy = buildable_core.bounds
    bbox_w = maxx - minx
    bbox_d = maxy - miny

    if bbox_w <= 0 or bbox_d <= 0:
        return None

    cx, cy = buildable_core.centroid.x, buildable_core.centroid.y

    # Target square-ish COP with required area
    side = max(min_dimension_dxf, math.sqrt(required_area_sqft))
    depth = max(min_dimension_dxf, required_area_sqft / side if side > 0 else min_dimension_dxf)

    # Don't exceed 60% of core dimensions
    side = min(side, bbox_w * 0.6)
    depth = min(depth, bbox_d * 0.6)

    center_rect = box(cx - side / 2, cy - depth / 2, cx + side / 2, cy + depth / 2)
    center_cop = center_rect.intersection(buildable_core)

    if center_cop.is_empty:
        return None

    # Scale up if area insufficient
    if center_cop.area < required_area_sqft:
        for scale in [1.2, 1.5, 1.8, 2.0]:
            scaled = box(
                cx - side * scale / 2, cy - depth * scale / 2,
                cx + side * scale / 2, cy + depth * scale / 2,
            ).intersection(buildable_core)
            if not scaled.is_empty and scaled.area >= required_area_sqft:
                center_cop = scaled
                break

    if isinstance(center_cop, MultiPolygon):
        center_cop = max(center_cop.geoms, key=lambda g: g.area)

    if center_cop.area < required_area_sqft * 0.95:
        return None

    # Compute metrics
    minx, miny, maxx, maxy = center_cop.bounds
    width = maxx - minx
    depth = maxy - miny
    min_dim_m = min(width, depth) * DXF_TO_METRES
    aspect = max(width, depth) / min(width, depth) if min(width, depth) > 0 else 999.0

    score = score_cop_region(center_cop, buildable_core, plot_polygon, edge_specs)

    return CopCandidate(
        polygon=center_cop,
        area_sqft=center_cop.area,
        min_dimension_m=min_dim_m,
        aspect_ratio=aspect,
        score=score,
        label="CENTER_COURTYARD",
        centroid=(center_cop.centroid.x, center_cop.centroid.y),
    )


# ── Main entry point ──────────────────────────────────────────────────────────


def find_cop_candidate_regions(
    buildable_core: Polygon,
    plot_polygon: Polygon,
    edge_specs: List[EdgeSpec],
    required_area_sqft: float,
    min_dimension_dxf: float,
    max_aspect_ratio: float = 3.0,
) -> List[CopCandidate]:
    """
    Generate and rank COP candidate regions BEFORE tower placement.

    This is the core COP-FIRST planning function that replaces post-hoc
    COP carving with proactive region selection.

    Parameters
    ----------
    buildable_core       : Buildable core after fire loop (DXF feet).
    plot_polygon         : Original plot polygon (DXF feet).
    edge_specs           : Classified edge specs.
    required_area_sqft   : Minimum COP area (sq.ft).
    min_dimension_dxf    : Minimum COP dimension (DXF feet).
    max_aspect_ratio     : Maximum width/depth ratio (reject strips).

    Returns
    -------
    List[CopCandidate] — ranked by score (descending), filtered by geometry validation.
    """
    candidates: List[CopCandidate] = []

    # ── Generate candidate 1: Rear strip ──────────────────────────────────────
    rear_candidate = _generate_rear_strip_candidate(
        plot_polygon, buildable_core, edge_specs, required_area_sqft, min_dimension_dxf,
    )
    if rear_candidate is not None:
        is_valid, reason = validate_cop_geometry(
            rear_candidate.polygon, min_dimension_dxf, max_aspect_ratio,
        )
        if is_valid:
            candidates.append(rear_candidate)
        else:
            logger.debug("Rear strip COP rejected: %s", reason)

    # ── Generate candidate 2: Center courtyard ────────────────────────────────
    center_candidate = _generate_center_courtyard_candidate(
        plot_polygon, buildable_core, edge_specs, required_area_sqft, min_dimension_dxf,
    )
    if center_candidate is not None:
        is_valid, reason = validate_cop_geometry(
            center_candidate.polygon, min_dimension_dxf, max_aspect_ratio,
        )
        if is_valid:
            candidates.append(center_candidate)
        else:
            logger.debug("Center courtyard COP rejected: %s", reason)

    # ── Sort by score (descending) ────────────────────────────────────────────
    candidates.sort(key=lambda c: c.score, reverse=True)

    if candidates:
        logger.info(
            "COP candidates generated: %d viable options. Best: %s (score=%.3f, area=%.0f sqft)",
            len(candidates), candidates[0].label, candidates[0].score, candidates[0].area_sqft,
        )
    else:
        logger.warning("No viable COP candidates found — all rejected by geometry validation.")

    return candidates
