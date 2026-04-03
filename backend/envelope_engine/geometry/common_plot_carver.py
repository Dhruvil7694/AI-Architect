"""
geometry/common_plot_carver.py
-------------------------------
Carves the 10% common open-space reservation required by CGDCR 2017.

CGDCR clause
------------
10% of the total plot area must be reserved as a common amenity/open-space
plot.  This area must:
  - Be physically distinct from the buildable envelope
  - Be located in the least-valuable zone (closest to the rear boundary)
  - Not be counted in FSI calculations

Carving strategy
----------------
1. Identify the REAR EdgeSpec from the classified list.
2. Project all plot vertices onto the inward normal of the rear edge to find
   the "depth axis" of the plot (distance from rear boundary into the plot).
3. Target: strip_area = 0.10 × plot.area
4. Using bisection, find a depth `d` (in DXF feet along the rear normal) such
   that the strip between the rear edge and the depth-d offset line has area
   ≈ strip_area.
5. The common plot polygon is the intersection of:
       (original plot) ∩ (half-plane of rear boundary) – (envelope region)
   i.e. it occupies the rear margin zone already required by GDCR.

"NO_CARVE_NEEDED" detection
---------------------------
If the rear margin already provides sufficient area (margin_area ≥ strip_area),
the common plot is considered already embedded in the margin zone and no
additional carving is required.  We still return the rear-strip polygon so
it can be stored for audit.

Returns
-------
(common_plot_geom: Polygon | None, common_area_sqft: float, status: str)

status values:
    "CARVED"          — strip carved and returned
    "NO_CARVE_NEEDED" — rear margin zone already satisfies 10% requirement
    "NO_REAR_EDGE"    — no REAR edge found in edge_specs (edge_specs empty /
                        all edges are ROAD — unusual geometry)
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box

from envelope_engine.geometry.edge_classifier import REAR, ROAD, SIDE, EdgeSpec
from architecture.regulatory_accessors import get_cop_required_fraction
from rules_engine.rules.loader import get_gdcr_config
from common.units import dxf_plane_area_to_sqm, metres_to_dxf

logger = logging.getLogger(__name__)

COMMON_PLOT_FRACTION = get_cop_required_fraction()

_BISECT_ITERATIONS = 25
_BISECT_TOLERANCE  = 1e-4   # DXF feet


def _rear_strip_polygon(
    plot_polygon: Polygon,
    rear_spec: EdgeSpec,
    depth_dxf: float,
) -> Polygon:
    """
    Return the polygon representing the strip within `depth_dxf` DXF feet of
    the rear edge (i.e. the region between the rear boundary and the
    depth-d offset line).

    This is constructed as:
        original_plot  INTERSECT  complement_of_keep_half_plane(depth_dxf)

    The "complement" of the keep half-plane is the strip on the EXTERIOR side
    of the offset rear edge — which, intersected with the plot, gives us the
    rear strip.
    """
    import math as _math

    nx, ny = rear_spec.inward_normal
    ex = -ny   # edge unit vector (perpendicular to inward normal)
    ey =  nx

    # Offset the rear edge outward by depth_dxf (inward into the plot)
    p1_off = (rear_spec.p1[0] + nx * depth_dxf,
              rear_spec.p1[1] + ny * depth_dxf)
    p2_off = (rear_spec.p2[0] + nx * depth_dxf,
              rear_spec.p2[1] + ny * depth_dxf)

    E = 1e7   # safe extent larger than any plot
    # The "excluded" half-plane (inward side of offset line):
    c1 = (p1_off[0] - ex * E, p1_off[1] - ey * E)
    c2 = (p2_off[0] + ex * E, p2_off[1] + ey * E)
    c3 = (c2[0] + nx * E,     c2[1] + ny * E)
    c4 = (c1[0] + nx * E,     c1[1] + ny * E)
    inward_half_plane = Polygon([c1, c2, c3, c4])

    # Rear strip = plot minus the inward half-plane
    rear_strip = plot_polygon.difference(inward_half_plane)
    return rear_strip


def carve_common_plot(
    plot_polygon: Polygon,
    envelope: Polygon,
    edge_specs: List[EdgeSpec],
    cop_strategy: str = "edge",
) -> Tuple[Optional[Polygon], float, str]:
    """
    Carve the 10% common open-space strip from the rear of the plot.

    Parameters
    ----------
    plot_polygon : original plot (DXF feet)
    envelope     : final buildable envelope (DXF feet)
    edge_specs   : classified + margin-resolved EdgeSpec list

    Returns
    -------
    (common_geom, common_area_sqft, status)
    """
    # ── COP applicability check (plot size threshold) ──────────────────────────
    try:
        gdcr = get_gdcr_config()
        cop_cfg = gdcr.get("common_open_plot", {}) or {}
        applies_threshold_sqm = float(
            cop_cfg.get("applies_if_plot_area_above_sqm", 0.0)
        )
        min_total_area_sqm = float(cop_cfg.get("minimum_total_area_sqm", 0.0))
    except Exception:
        cop_cfg = {}
        applies_threshold_sqm = 0.0
        min_total_area_sqm = 0.0

    plot_area_sqm = dxf_plane_area_to_sqm(plot_polygon.area)

    if applies_threshold_sqm > 0.0 and plot_area_sqm < applies_threshold_sqm:
        logger.info(
            "Plot area %.1f sqm < COP threshold %.1f sqm — no common plot required.",
            plot_area_sqm,
            applies_threshold_sqm,
        )
        return None, 0.0, "NO_CARVE_NEEDED"

    # Required COP area in DXF plane units² (m² when using metre DXF).
    required_area = max(
        COMMON_PLOT_FRACTION * plot_area_sqm,
        min_total_area_sqm,
    )

    strategy = (cop_strategy or "edge").lower()

    # ── INTELLIGENT strategy: adaptive COP placement ─────────────────────────
    if strategy == "intelligent":
        return _carve_intelligent_cop(
            plot_polygon, envelope, edge_specs, required_area, cop_cfg,
        )

    # ── CENTER strategy: axis-aligned rectangle around plot centroid ───────────
    if strategy == "center":
        geometry_cfg = (cop_cfg.get("geometry_constraints") or {}) if cop_cfg else {}
        min_width_m = float(geometry_cfg.get("minimum_width_m", 0.0) or 0.0)
        min_depth_m = float(geometry_cfg.get("minimum_depth_m", 0.0) or 0.0)

        min_width_dxf = metres_to_dxf(min_width_m) if min_width_m > 0.0 else 0.0
        min_depth_dxf = metres_to_dxf(min_depth_m) if min_depth_m > 0.0 else 0.0

        minx, miny, maxx, maxy = plot_polygon.bounds
        bbox_width = maxx - minx
        bbox_depth = maxy - miny
        if bbox_width <= 0.0 or bbox_depth <= 0.0:
            logger.warning("Degenerate plot bounds for CENTER COP — skipping carve.")
            return None, 0.0, "NO_CARVE_NEEDED"

        # Initial rectangle dimensions: honour minimums, target required area.
        base_width = max(min_width_dxf, math.sqrt(required_area)) if required_area > 0 else min_width_dxf
        base_depth = max(
            min_depth_dxf,
            required_area / base_width if base_width > 0 else min_depth_dxf,
        )

        # Clamp to bounding box.
        base_width = min(base_width, bbox_width)
        base_depth = min(base_depth, bbox_depth)

        cx, cy = plot_polygon.centroid.x, plot_polygon.centroid.y

        def _build_center_rect(width: float, depth: float) -> Polygon:
            return box(
                cx - width / 2.0,
                cy - depth / 2.0,
                cx + width / 2.0,
                cy + depth / 2.0,
            )

        rect = _build_center_rect(base_width, base_depth)
        common_geom = rect.intersection(plot_polygon)
        common_area = common_geom.area if not common_geom.is_empty else 0.0

        # If area is below requirement and we still have room inside the bbox,
        # scale rectangle up uniformly (deterministic binary search).
        if common_area + 1e-6 < required_area and base_width > 0.0 and base_depth > 0.0:
            max_scale_w = bbox_width / base_width if base_width > 0 else 1.0
            max_scale_d = bbox_depth / base_depth if base_depth > 0 else 1.0
            max_scale = max(1.0, min(max_scale_w, max_scale_d))

            lo, hi = 1.0, max_scale
            best_geom: Optional[Polygon] = common_geom
            best_area = common_area

            for _ in range(_BISECT_ITERATIONS):
                mid = (lo + hi) / 2.0
                width_mid = base_width * mid
                depth_mid = base_depth * mid
                rect_mid = _build_center_rect(width_mid, depth_mid)
                geom_mid = rect_mid.intersection(plot_polygon)
                area_mid = geom_mid.area if not geom_mid.is_empty else 0.0

                if area_mid < required_area:
                    lo = mid
                else:
                    hi = mid
                    best_geom = geom_mid
                    best_area = area_mid

                if hi - lo < _BISECT_TOLERANCE:
                    break

            common_geom = best_geom
            common_area = best_area

        if common_geom is None or common_geom.is_empty or common_area <= 0.0:
            logger.warning("CENTER COP carving failed — returning None.")
            return None, 0.0, "NO_CARVE_NEEDED"

        # Handle MultiPolygon (pick largest contiguous COP block).
        if isinstance(common_geom, MultiPolygon):
            common_geom = max(common_geom.geoms, key=lambda g: g.area)
            common_area = common_geom.area

        logger.info(
            "CENTER common plot carved: %.1f sq.ft (%.1f%% of plot area %.1f sq.ft).",
            common_area,
            common_area / plot_polygon.area * 100 if plot_polygon.area > 0 else 0.0,
            plot_polygon.area,
        )
        return common_geom, round(common_area, 2), "CARVED"

    # ── EDGE strategy (existing rear-strip behaviour) ──────────────────────────
    rear_specs = [s for s in edge_specs if s.edge_type == REAR]
    if not rear_specs:
        logger.warning("No REAR edge found — common plot carving skipped.")
        return None, 0.0, "NO_REAR_EDGE"

    rear_spec = rear_specs[0]   # use the first REAR edge (typically only one)

    # GDCR minimum perpendicular depth of the COP strip (7.5 m per GDCR.yaml).
    # The depth is measured perpendicular to the rear edge — it IS the minimum
    # dimension of the strip.  We enforce it so the COP is always usable open
    # space (not just a thin ribbon that satisfies area but fails dimension).
    try:
        gdcr_min_dim_m = float(
            (get_gdcr_config().get("common_open_plot", {}) or {}).get("minimum_dimension_m", 7.5)
        )
    except Exception:
        gdcr_min_dim_m = 7.5
    min_depth_dxf = metres_to_dxf(gdcr_min_dim_m)

    # ── Check if rear margin already covers the required area ──────────────────
    # The rear margin zone is the strip from the rear edge to depth = margin_dxf.
    # We only use it as COP when its depth also meets the minimum dimension.
    rear_margin_dxf = rear_spec.required_margin_dxf
    if rear_margin_dxf > 0 and rear_margin_dxf >= min_depth_dxf:
        margin_strip = _rear_strip_polygon(plot_polygon, rear_spec, rear_margin_dxf)
        margin_area = margin_strip.area
        if margin_area >= required_area:
            logger.info(
                "Rear margin zone %.1f sq.ft >= required common plot %.1f sq.ft "
                "(depth %.2f dxf >= min %.2f dxf). NO_CARVE_NEEDED.",
                margin_area, required_area, rear_margin_dxf, min_depth_dxf,
            )
            common_geom = margin_strip if not margin_strip.is_empty else None
            return common_geom, round(margin_area, 2), "NO_CARVE_NEEDED"

    # ── Bisect to find the carving depth ──────────────────────────────────────
    # Maximum depth: half the plot's extent along the rear normal direction.
    nx, ny = rear_spec.inward_normal
    xs = [c[0] for c in plot_polygon.exterior.coords]
    ys = [c[1] for c in plot_polygon.exterior.coords]
    projections = [x * nx + y * ny for x, y in zip(xs, ys)]
    max_depth = (max(projections) - min(projections)) * 0.9  # 90% of plot depth

    lo, hi = 0.0, max_depth
    best_strip: Optional[Polygon] = None

    for _ in range(_BISECT_ITERATIONS):
        mid = (lo + hi) / 2.0
        strip = _rear_strip_polygon(plot_polygon, rear_spec, mid)
        strip_area = strip.area if not strip.is_empty else 0.0

        if strip_area < required_area:
            lo = mid
        else:
            hi = mid
            best_strip = strip

        if (hi - lo) < _BISECT_TOLERANCE:
            break

    # Enforce minimum dimension: if the bisected depth < min_depth_dxf, re-carve
    # at min_depth_dxf.  This guarantees the strip is at least 7.5 m deep and
    # satisfies GDCR usability (even if area ends up slightly above 10%).
    if hi < min_depth_dxf:
        deeper_strip = _rear_strip_polygon(plot_polygon, rear_spec, min_depth_dxf)
        if not deeper_strip.is_empty:
            best_strip = deeper_strip
            logger.info(
                "COP depth %.2f dxf < min %.2f dxf; re-carved at minimum dimension.",
                hi, min_depth_dxf,
            )

    if best_strip is None or best_strip.is_empty:
        logger.warning("Common plot bisection failed — returning None.")
        return None, 0.0, "NO_REAR_EDGE"

    # Handle MultiPolygon (irregular rear boundary)
    if isinstance(best_strip, MultiPolygon):
        best_strip = max(best_strip.geoms, key=lambda g: g.area)

    common_area = best_strip.area
    logger.info(
        "Common plot carved: %.1f sq.ft (%.1f%% of plot area %.1f sq.ft).",
        common_area,
        common_area / plot_polygon.area * 100,
        plot_polygon.area,
    )
    return best_strip, round(common_area, 2), "CARVED"


# ── Intelligent COP strategy ─────────────────────────────────────────────────


def _polsby_popper(polygon: Polygon) -> float:
    """Compactness score: 1.0 = circle, 0.0 = degenerate."""
    if polygon.is_empty or polygon.length == 0:
        return 0.0
    return (4.0 * math.pi * polygon.area) / (polygon.length ** 2)


def _cop_candidate_score(
    candidate: Polygon,
    plot_polygon: Polygon,
    envelope: Polygon,
) -> float:
    """
    Score a COP candidate location by:
      - centrality   (0.35): proximity of COP centroid to plot centroid
      - compactness  (0.35): Polsby-Popper shape quality
      - accessibility (0.30): fraction of COP boundary touching plot boundary
    """
    diag = math.sqrt(
        (plot_polygon.bounds[2] - plot_polygon.bounds[0]) ** 2 +
        (plot_polygon.bounds[3] - plot_polygon.bounds[1]) ** 2
    )
    if diag == 0:
        return 0.0

    # Centrality: 1.0 if COP centroid is at plot centroid
    cop_cx, cop_cy = candidate.centroid.x, candidate.centroid.y
    plot_cx, plot_cy = plot_polygon.centroid.x, plot_polygon.centroid.y
    dist = math.sqrt((cop_cx - plot_cx) ** 2 + (cop_cy - plot_cy) ** 2)
    centrality = 1.0 - min(dist / diag, 1.0)

    # Compactness: Polsby-Popper
    compactness = _polsby_popper(candidate)

    # Accessibility: fraction of COP perimeter touching plot boundary
    try:
        shared_boundary = candidate.intersection(plot_polygon.boundary)
        accessibility = shared_boundary.length / candidate.length if candidate.length > 0 else 0.0
    except Exception:
        accessibility = 0.0

    return 0.35 * centrality + 0.35 * compactness + 0.30 * accessibility


def _carve_intelligent_cop(
    plot_polygon: Polygon,
    envelope: Polygon,
    edge_specs: list,
    required_area: float,
    cop_cfg: dict,
) -> tuple:
    """
    Intelligent COP placement: evaluates multiple candidate positions
    and selects the best one based on centrality, compactness, and
    accessibility.

    Candidate strategies:
    1. Rear strip (proven, always generated)
    2. Central courtyard box (for multi-tower layouts)
    3. Side-strip candidates (for irregular plots)

    Returns
    -------
    (common_geom, common_area_sqft, status)
    """
    geometry_cfg = cop_cfg.get("geometry_constraints", {}) or {}
    min_width_m = float(geometry_cfg.get("minimum_width_m", 10.0) or 10.0)
    min_depth_m = float(geometry_cfg.get("minimum_depth_m", 10.0) or 10.0)
    min_width_dxf = metres_to_dxf(min_width_m)
    min_depth_dxf = metres_to_dxf(min_depth_m)

    candidates: list[tuple[Polygon, float, str]] = []  # (geom, score, label)

    # ── Candidate 1: Rear strip (existing EDGE logic) ────────────────────────
    rear_specs = [s for s in edge_specs if s.edge_type == REAR]
    if rear_specs:
        rear_spec = rear_specs[0]
        try:
            gdcr_min_dim_m = float(
                cop_cfg.get("minimum_dimension_m", 7.5)
            )
        except Exception:
            gdcr_min_dim_m = 7.5
        edge_min_depth_dxf = metres_to_dxf(gdcr_min_dim_m)

        # Bisect for correct depth
        nx, ny = rear_spec.inward_normal
        xs = [c[0] for c in plot_polygon.exterior.coords]
        ys = [c[1] for c in plot_polygon.exterior.coords]
        projections = [x * nx + y * ny for x, y in zip(xs, ys)]
        max_depth = (max(projections) - min(projections)) * 0.9

        lo, hi = 0.0, max_depth
        best_strip = None
        for _ in range(_BISECT_ITERATIONS):
            mid = (lo + hi) / 2.0
            strip = _rear_strip_polygon(plot_polygon, rear_spec, mid)
            strip_area = strip.area if not strip.is_empty else 0.0
            if strip_area < required_area:
                lo = mid
            else:
                hi = mid
                best_strip = strip
            if (hi - lo) < _BISECT_TOLERANCE:
                break

        if hi < edge_min_depth_dxf:
            deeper = _rear_strip_polygon(plot_polygon, rear_spec, edge_min_depth_dxf)
            if not deeper.is_empty:
                best_strip = deeper

        if best_strip is not None and not best_strip.is_empty:
            if isinstance(best_strip, MultiPolygon):
                best_strip = max(best_strip.geoms, key=lambda g: g.area)
            score = _cop_candidate_score(best_strip, plot_polygon, envelope)
            candidates.append((best_strip, score, "REAR_STRIP"))

    # ── Candidate 2: Central courtyard box ────────────────────────────────────
    minx, miny, maxx, maxy = plot_polygon.bounds
    bbox_w = maxx - minx
    bbox_d = maxy - miny

    if bbox_w > 0 and bbox_d > 0:
        cx, cy = plot_polygon.centroid.x, plot_polygon.centroid.y

        # Target a square-ish COP with required area
        side = max(min_width_dxf, math.sqrt(required_area))
        depth = max(min_depth_dxf, required_area / side if side > 0 else min_depth_dxf)
        side = min(side, bbox_w * 0.6)   # don't exceed 60% of plot width
        depth = min(depth, bbox_d * 0.6)

        center_rect = box(cx - side / 2, cy - depth / 2, cx + side / 2, cy + depth / 2)
        center_cop = center_rect.intersection(plot_polygon)

        if not center_cop.is_empty:
            # Scale up if area insufficient
            if center_cop.area < required_area:
                for scale in [1.2, 1.5, 1.8, 2.0]:
                    scaled = box(
                        cx - side * scale / 2, cy - depth * scale / 2,
                        cx + side * scale / 2, cy + depth * scale / 2,
                    ).intersection(plot_polygon)
                    if not scaled.is_empty and scaled.area >= required_area:
                        center_cop = scaled
                        break

            if isinstance(center_cop, MultiPolygon):
                center_cop = max(center_cop.geoms, key=lambda g: g.area)

            if center_cop.area >= required_area * 0.95:
                score = _cop_candidate_score(center_cop, plot_polygon, envelope)
                candidates.append((center_cop, score, "CENTER_COURTYARD"))

    # ── Candidate 3: Side strips (for irregular plots) ────────────────────────
    side_specs = [s for s in edge_specs if s.edge_type == SIDE]
    for side_spec in side_specs[:2]:  # try up to 2 side edges
        try:
            nx, ny = side_spec.inward_normal
            xs = [c[0] for c in plot_polygon.exterior.coords]
            ys = [c[1] for c in plot_polygon.exterior.coords]
            projections = [x * nx + y * ny for x, y in zip(xs, ys)]
            max_side_depth = (max(projections) - min(projections)) * 0.4

            lo, hi = 0.0, max_side_depth
            best_side = None
            for _ in range(_BISECT_ITERATIONS):
                mid = (lo + hi) / 2.0
                strip = _rear_strip_polygon(plot_polygon, side_spec, mid)
                strip_area = strip.area if not strip.is_empty else 0.0
                if strip_area < required_area:
                    lo = mid
                else:
                    hi = mid
                    best_side = strip
                if (hi - lo) < _BISECT_TOLERANCE:
                    break

            if best_side is not None and not best_side.is_empty:
                if isinstance(best_side, MultiPolygon):
                    best_side = max(best_side.geoms, key=lambda g: g.area)
                score = _cop_candidate_score(best_side, plot_polygon, envelope)
                candidates.append((best_side, score, "SIDE_STRIP"))
        except Exception:
            continue

    # ── Select best candidate ─────────────────────────────────────────────────
    if not candidates:
        logger.warning("Intelligent COP: no viable candidates — returning None.")
        return None, 0.0, "NO_REAR_EDGE"

    # Sort by score descending
    candidates.sort(key=lambda c: c[1], reverse=True)
    best_geom, best_score, best_label = candidates[0]

    common_area = best_geom.area
    logger.info(
        "INTELLIGENT COP selected: %s (score=%.3f), %.1f sq.ft "
        "(%.1f%% of plot area %.1f sq.ft). Evaluated %d candidates.",
        best_label, best_score, common_area,
        common_area / plot_polygon.area * 100 if plot_polygon.area > 0 else 0.0,
        plot_polygon.area,
        len(candidates),
    )
    return best_geom, round(common_area, 2), "CARVED"
