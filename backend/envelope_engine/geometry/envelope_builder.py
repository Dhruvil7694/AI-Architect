"""
geometry/envelope_builder.py
-----------------------------
Core spatial algorithm: per-edge half-plane intersection.
"""

from __future__ import annotations

import logging
from typing import List

from shapely.geometry import MultiPolygon, Polygon

from envelope_engine.geometry import (
    MIN_BUILDABLE_AREA_SQFT,
    EnvelopeCollapseError,
    EnvelopeTooSmallError,
    InvalidGeometryError,
)
from envelope_engine.geometry.edge_classifier import EdgeSpec, ROAD

logger = logging.getLogger(__name__)

_HALF_PLANE_EXTENT = 1e7
# Ignore tiny non-road edge stubs that can over-constrain clipping on
# digitized irregular boundaries.
_MICRO_EDGE_CLIP_RATIO = 0.50


def _build_keep_half_plane(spec: EdgeSpec) -> Polygon:
    """Build a large inward keep half-plane for a single edge."""
    nx, ny = spec.inward_normal
    margin = spec.required_margin_dxf

    p1_off = (spec.p1[0] + nx * margin, spec.p1[1] + ny * margin)
    p2_off = (spec.p2[0] + nx * margin, spec.p2[1] + ny * margin)

    import math

    dx = spec.p2[0] - spec.p1[0]
    dy = spec.p2[1] - spec.p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-10:
        return Polygon(
            [
                (-_HALF_PLANE_EXTENT, -_HALF_PLANE_EXTENT),
                (_HALF_PLANE_EXTENT, -_HALF_PLANE_EXTENT),
                (_HALF_PLANE_EXTENT, _HALF_PLANE_EXTENT),
                (-_HALF_PLANE_EXTENT, _HALF_PLANE_EXTENT),
            ]
        )

    ex, ey = dx / length, dy / length
    e = _HALF_PLANE_EXTENT
    c1 = (p1_off[0] - ex * e, p1_off[1] - ey * e)
    c2 = (p2_off[0] + ex * e, p2_off[1] + ey * e)
    c3 = (c2[0] + nx * e, c2[1] + ny * e)
    c4 = (c1[0] + nx * e, c1[1] + ny * e)
    return Polygon([c1, c2, c3, c4])


def build_envelope(plot_polygon: Polygon, edge_specs: List[EdgeSpec]) -> Polygon:
    """
    Apply per-edge setback margins and return the legal buildable footprint.
    """
    if not plot_polygon.is_valid:
        logger.warning("Plot polygon is not valid; attempting buffer(0) repair.")
        repaired = plot_polygon.buffer(0)
        if not repaired.is_valid or repaired.is_empty:
            raise InvalidGeometryError(
                "Plot polygon is degenerate and could not be repaired with "
                "buffer(0). Check the source DXF geometry."
            )
        plot_polygon = repaired

    result: Polygon = plot_polygon
    skipped_micro_edges = 0

    for spec in edge_specs:
        if spec.required_margin_dxf <= 0:
            continue

        if (
            spec.edge_type != ROAD
            and spec.length > 0
            and spec.length < (spec.required_margin_dxf * _MICRO_EDGE_CLIP_RATIO)
        ):
            skipped_micro_edges += 1
            logger.debug(
                "Skipping micro edge %d (%s): length=%.3f dxf, margin=%.3f dxf",
                spec.index,
                spec.edge_type,
                spec.length,
                spec.required_margin_dxf,
            )
            continue

        keep_plane = _build_keep_half_plane(spec)
        clipped = result.intersection(keep_plane)

        if clipped.is_empty:
            raise EnvelopeCollapseError(
                f"Envelope collapsed after applying {spec.required_margin_m:.2f} m "
                f"({spec.required_margin_dxf:.4f} DXF ft) margin on edge {spec.index} "
                f"({spec.edge_type}, {spec.gdcr_clause}). "
                "The plot is too narrow to accommodate the required setback."
            )

        if isinstance(clipped, MultiPolygon):
            logger.warning(
                "Edge %d margin produced a MultiPolygon (non-convex plot). Using the largest component.",
                spec.index,
            )
            clipped = max(clipped.geoms, key=lambda g: g.area)

        result = clipped

    if result.is_empty:
        raise EnvelopeCollapseError("Envelope is empty after all margin intersections.")

    if result.area < MIN_BUILDABLE_AREA_SQFT:
        raise EnvelopeTooSmallError(
            f"Resulting envelope area {result.area:.1f} sq.ft is below the "
            f"minimum buildable threshold of {MIN_BUILDABLE_AREA_SQFT} sq.ft "
            f"(~20 sq.m). The plot is too small for the proposed margins."
        )

    logger.info(
        "Envelope built: %.1f sq.ft (plot was %.1f sq.ft, coverage %.1f%%, skipped_micro_edges=%d)",
        result.area,
        plot_polygon.area,
        result.area / plot_polygon.area * 100,
        skipped_micro_edges,
    )
    return result
