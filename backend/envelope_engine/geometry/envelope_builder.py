"""
geometry/envelope_builder.py
-----------------------------
Core spatial algorithm: per-edge half-plane intersection.

Algorithm
---------
For each EdgeSpec (with `required_margin_dxf` already populated by
MarginResolver):

  1. Compute the inward unit normal for the edge (pre-computed in EdgeSpec).
  2. Offset both endpoints inward by `required_margin_dxf`.
  3. Construct a "keep half-plane": a very large rectangle that covers the
     entire inward side of the offset edge.
  4. Intersect the running result polygon with this half-plane.

After all edges the result is the legal buildable footprint.

Why this works for irregular polygons
--------------------------------------
Unlike `polygon.buffer(-d)`, which sets every edge to the same offset,
this algorithm applies a different offset distance to each edge independently.
The half-plane intersection is correct for both convex and non-convex
polygons — the only edge case is when a non-convex indentation causes
the result to become a MultiPolygon (handled: we take the largest component
and log a warning).

Unit contract
-------------
All coordinates and margin values must be in the SAME unit before calling
this function.  The `edge_specs` produced by MarginResolver already have
`required_margin_dxf` in DXF feet.  The `plot_polygon` must also be in
DXF feet.  Do NOT mix units here.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from shapely.geometry import MultiPolygon, Polygon

from envelope_engine.geometry import (
    MIN_BUILDABLE_AREA_SQFT,
    EnvelopeCollapseError,
    EnvelopeTooSmallError,
    InvalidGeometryError,
)
from envelope_engine.geometry.edge_classifier import EdgeSpec

logger = logging.getLogger(__name__)

# Half-plane rectangle size: must be larger than any conceivable DXF coordinate.
# TP14 coordinates are in the order of 0–5000 feet, so 1e7 is safely infinite.
_HALF_PLANE_EXTENT = 1e7


def _build_keep_half_plane(spec: EdgeSpec) -> Polygon:
    """
    Build a large rectangle representing the "keep zone" for a single edge:
    everything that is AT LEAST `required_margin_dxf` inward from this edge.

    The rectangle is constructed as:
        • Start from the offset edge (p1_off, p2_off)
        • Extend far (±_HALF_PLANE_EXTENT) along the edge direction
        • Extend far (+_HALF_PLANE_EXTENT) inward from the offset edge
    """
    nx, ny = spec.inward_normal
    margin = spec.required_margin_dxf

    # Offset endpoints
    p1_off = (spec.p1[0] + nx * margin, spec.p1[1] + ny * margin)
    p2_off = (spec.p2[0] + nx * margin, spec.p2[1] + ny * margin)

    # Edge direction unit vector (p1→p2)
    import math
    dx = spec.p2[0] - spec.p1[0]
    dy = spec.p2[1] - spec.p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-10:
        # Degenerate zero-length edge — no clipping needed, return huge polygon
        return Polygon([
            (-_HALF_PLANE_EXTENT, -_HALF_PLANE_EXTENT),
            ( _HALF_PLANE_EXTENT, -_HALF_PLANE_EXTENT),
            ( _HALF_PLANE_EXTENT,  _HALF_PLANE_EXTENT),
            (-_HALF_PLANE_EXTENT,  _HALF_PLANE_EXTENT),
        ])
    ex, ey = dx / length, dy / length   # edge unit vector

    # Four corners of the keep rectangle:
    #   extend backwards and forwards along edge direction
    #   then extend inward (along normal)
    E = _HALF_PLANE_EXTENT
    c1 = (p1_off[0] - ex * E, p1_off[1] - ey * E)
    c2 = (p2_off[0] + ex * E, p2_off[1] + ey * E)
    c3 = (c2[0] + nx * E,     c2[1] + ny * E)
    c4 = (c1[0] + nx * E,     c1[1] + ny * E)

    return Polygon([c1, c2, c3, c4])


def build_envelope(
    plot_polygon: Polygon,
    edge_specs: List[EdgeSpec],
) -> Polygon:
    """
    Apply per-edge setback margins and return the legal buildable footprint.

    Parameters
    ----------
    plot_polygon : Shapely Polygon in DXF coordinate units (feet)
    edge_specs   : list of EdgeSpec with `required_margin_dxf` populated

    Returns
    -------
    Shapely Polygon — the buildable envelope

    Raises
    ------
    InvalidGeometryError   if the plot polygon cannot be repaired
    EnvelopeCollapseError  if all margins together collapse the polygon to empty
    EnvelopeTooSmallError  if the result is smaller than MIN_BUILDABLE_AREA_SQFT
    """
    # ── 1. Validate and repair input geometry ─────────────────────────────────
    if not plot_polygon.is_valid:
        logger.warning("Plot polygon is not valid; attempting buffer(0) repair.")
        repaired = plot_polygon.buffer(0)
        if not repaired.is_valid or repaired.is_empty:
            raise InvalidGeometryError(
                "Plot polygon is degenerate and could not be repaired with "
                "buffer(0). Check the source DXF geometry."
            )
        plot_polygon = repaired

    # ── 2. Per-edge half-plane intersection ────────────────────────────────────
    result: Polygon = plot_polygon

    for spec in edge_specs:
        if spec.required_margin_dxf <= 0:
            continue   # zero margin → no clipping for this edge

        keep_plane = _build_keep_half_plane(spec)
        clipped = result.intersection(keep_plane)

        if clipped.is_empty:
            raise EnvelopeCollapseError(
                f"Envelope collapsed after applying {spec.required_margin_m:.2f} m "
                f"({spec.required_margin_dxf:.4f} DXF ft) margin on edge {spec.index} "
                f"({spec.edge_type}, {spec.gdcr_clause}). "
                "The plot is too narrow to accommodate the required setback."
            )

        # Handle MultiPolygon: take the largest component with a warning
        if isinstance(clipped, MultiPolygon):
            logger.warning(
                "Edge %d margin produced a MultiPolygon (non-convex plot). "
                "Using the largest component.",
                spec.index,
            )
            clipped = max(clipped.geoms, key=lambda g: g.area)

        result = clipped

    # ── 3. Final size check ────────────────────────────────────────────────────
    if result.is_empty:
        raise EnvelopeCollapseError(
            "Envelope is empty after all margin intersections."
        )

    if result.area < MIN_BUILDABLE_AREA_SQFT:
        raise EnvelopeTooSmallError(
            f"Resulting envelope area {result.area:.1f} sq.ft is below the "
            f"minimum buildable threshold of {MIN_BUILDABLE_AREA_SQFT} sq.ft "
            f"(~20 sq.m). The plot is too small for the proposed margins."
        )

    logger.info(
        "Envelope built: %.1f sq.ft (plot was %.1f sq.ft, coverage %.1f%%)",
        result.area,
        plot_polygon.area,
        result.area / plot_polygon.area * 100,
    )
    return result
