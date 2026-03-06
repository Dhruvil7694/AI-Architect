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

from envelope_engine.geometry.edge_classifier import REAR, EdgeSpec
from architecture.regulatory_accessors import get_cop_required_fraction
from rules_engine.rules.loader import get_gdcr_config
from common.units import sqft_to_sqm, sqm_to_sqft, metres_to_dxf

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

    plot_area_sqft = plot_polygon.area
    plot_area_sqm = sqft_to_sqm(plot_area_sqft)

    if applies_threshold_sqm > 0.0 and plot_area_sqm < applies_threshold_sqm:
        logger.info(
            "Plot area %.1f sqm < COP threshold %.1f sqm — no common plot required.",
            plot_area_sqm,
            applies_threshold_sqm,
        )
        return None, 0.0, "NO_CARVE_NEEDED"

    # Required COP area in sq.ft: max(fraction × plot_area, minimum_total_area_sqm).
    min_total_area_sqft = (
        sqm_to_sqft(min_total_area_sqm) if min_total_area_sqm > 0.0 else 0.0
    )
    required_area = max(COMMON_PLOT_FRACTION * plot_area_sqft, min_total_area_sqft)

    strategy = (cop_strategy or "edge").lower()

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

    # ── Check if rear margin already covers the required area ──────────────────
    # The rear margin zone is the strip from the rear edge to depth = margin_dxf
    rear_margin_dxf = rear_spec.required_margin_dxf
    if rear_margin_dxf > 0:
        margin_strip = _rear_strip_polygon(plot_polygon, rear_spec, rear_margin_dxf)
        margin_area = margin_strip.area
        if margin_area >= required_area:
            logger.info(
                "Rear margin zone %.1f sq.ft >= required common plot %.1f sq.ft. "
                "NO_CARVE_NEEDED.",
                margin_area,
                required_area,
            )
            # Return the margin strip itself as the common plot polygon
            common_geom = margin_strip if not margin_strip.is_empty else None
            return common_geom, round(margin_area, 2), "NO_CARVE_NEEDED"

    # ── Bisect to find the carving depth ──────────────────────────────────────
    # Maximum depth: half the plot's extent along the rear normal direction
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
