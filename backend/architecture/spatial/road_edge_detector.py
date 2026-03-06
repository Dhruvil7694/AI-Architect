"""
architecture.spatial.road_edge_detector
---------------------------------------

Detect ROAD-facing edges on a TP plot polygon by intersecting with a
road layer, with a deterministic geometric fallback when no road
geometry is available.

API
---
detect_road_edges(plot_geom, road_layer_queryset) -> list[int]
    Returns 0-based indices of exterior edges classified as ROAD.
    When no road intersection is found or no road layer is provided,
    falls back to the longest exterior edge (index of max-length edge).

detect_road_edges_with_meta(plot_geom, road_layer_queryset)
    -> tuple[list[int], bool]
    Returns (edges, fallback_used). fallback_used=True when the
    longest-edge heuristic was used instead of an explicit road match.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Tuple

from django.contrib.gis.geos import GEOSGeometry, LineString, Polygon

logger = logging.getLogger(__name__)


def _edge_segments(poly: GEOSGeometry) -> List[LineString]:
    """
    Return list of LineString segments for the exterior ring of a polygon.
    """
    if not isinstance(poly, Polygon):
        poly = Polygon(poly)
    coords = list(poly.coords[0]) if hasattr(poly, "coords") else list(poly[0].coords)
    segments: List[LineString] = []
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        segments.append(LineString(p1, p2))
    return segments


def _iter_road_geoms(road_layer_queryset: Iterable) -> Iterable[GEOSGeometry]:
    """
    Yield GEOSGeometry objects from a road layer queryset or iterable.
    Accepts models with a 'geom' field or bare GEOSGeometry instances.
    """
    if road_layer_queryset is None:
        return []
    for obj in road_layer_queryset:
        geom = getattr(obj, "geom", None)
        if geom is None and isinstance(obj, GEOSGeometry):
            geom = obj
        if isinstance(geom, GEOSGeometry):
            yield geom


def detect_road_edges_with_meta(
    plot_geom: GEOSGeometry,
    road_layer_queryset: Iterable | None,
    *,
    buffer_tolerance: float = 0.01,
) -> Tuple[List[int], bool]:
    """
    Detect ROAD-facing edges and whether a fallback heuristic was used.

    Parameters
    ----------
    plot_geom : GEOSGeometry Polygon (SRID=0, DXF feet)
    road_layer_queryset : iterable of models with .geom or GEOSGeometry, or None
    buffer_tolerance : small buffer (same unit as DXF feet) to catch near-misses

    Returns
    -------
    (edges, fallback_used)
        edges         : list of 0-based edge indices
        fallback_used : True if no road geometry intersection was found and
                        the longest-edge heuristic was applied.
    """
    segments = _edge_segments(plot_geom)
    road_geoms = list(_iter_road_geoms(road_layer_queryset))

    if road_geoms:
        road_edges: List[int] = []
        for idx, seg in enumerate(segments):
            seg_buf = seg.buffer(buffer_tolerance)
            if any(seg_buf.intersects(r) or seg_buf.touches(r) for r in road_geoms):
                road_edges.append(idx)
        if road_edges:
            logger.info(
                "Detected %d road-facing edges from road layer (indices=%s).",
                len(road_edges),
                road_edges,
            )
            return road_edges, False

    # Fallback: longest exterior edge
    longest_idx = max(range(len(segments)), key=lambda i: segments[i].length) if segments else None
    if longest_idx is None:
        logger.warning("Road edge detection fallback failed: no segments found on plot geometry.")
        return [], True

    logger.warning(
        "Road edge detection using fallback: longest exterior edge index=%d used as ROAD.",
        longest_idx,
    )
    return [longest_idx], True


def detect_road_edges(plot_geom: GEOSGeometry, road_layer_queryset) -> List[int]:
    """
    Detect ROAD-facing edges; compatibility wrapper returning only indices.

    See detect_road_edges_with_meta for details. This function always allows
    the fallback heuristic (longest exterior edge) and logs when used.
    """
    edges, _ = detect_road_edges_with_meta(plot_geom, road_layer_queryset)
    return edges

