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
from typing import Iterable, List, Tuple, Dict, Any

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


def _load_multi_road_policy() -> tuple[int, str]:
    """
    Read multi-road governance defaults from GDCR.yaml.

    Keys:
      access_rules.multi_road_governance.max_road_edges_considered (default 1)
      access_rules.multi_road_governance.governing_edge_selection  (default longest_length)
    """
    try:
        from rules_engine.rules.loader import get_gdcr_config

        gdcr = get_gdcr_config() or {}
        cfg = (gdcr.get("access_rules", {}) or {}).get("multi_road_governance", {}) or {}
        max_edges = int(cfg.get("max_road_edges_considered", 1) or 1)
        selection = str(cfg.get("governing_edge_selection", "longest_length") or "longest_length")
        return max(1, max_edges), selection
    except Exception:
        return 1, "longest_length"


def select_governing_road_edges(
    plot_geom: GEOSGeometry,
    candidate_road_edges: List[int],
    *,
    max_edges: int | None = None,
    selection_policy: str | None = None,
) -> tuple[List[int], Dict[str, Any]]:
    """
    Select governing road edges for regulatory calculations.

    For plots with multiple attached roads, this keeps deterministic behavior:
    - rank candidate road edges by geometric length (descending)
    - retain only top-N (default from GDCR policy; typically N=1)
    - return selected indices sorted in descending-length order
    """
    segments = _edge_segments(plot_geom)
    total_edges = len(candidate_road_edges or [])
    if not candidate_road_edges:
        return [], {
            "total_road_edges_detected": 0,
            "governing_road_edges": [],
            "selection_policy": selection_policy or "longest_length",
            "max_road_edges_considered": max_edges or 1,
        }

    cfg_max, cfg_policy = _load_multi_road_policy()
    keep_n = max(1, int(max_edges if max_edges is not None else cfg_max))
    policy = (selection_policy or cfg_policy or "longest_length").strip().lower()

    # Validate indices and compute lengths.
    pairs: List[tuple[int, float]] = []
    for idx in candidate_road_edges:
        try:
            i = int(idx)
        except (TypeError, ValueError):
            continue
        if i < 0 or i >= len(segments):
            continue
        pairs.append((i, float(segments[i].length)))
    if not pairs:
        return [], {
            "total_road_edges_detected": total_edges,
            "governing_road_edges": [],
            "selection_policy": policy,
            "max_road_edges_considered": keep_n,
        }

    if policy == "longest_length":
        pairs.sort(key=lambda x: x[1], reverse=True)
    else:
        # Unknown policy -> deterministic fallback to longest.
        pairs.sort(key=lambda x: x[1], reverse=True)
        policy = "longest_length"

    selected = [idx for idx, _ in pairs[:keep_n]]
    return selected, {
        "total_road_edges_detected": total_edges,
        "governing_road_edges": selected,
        "selection_policy": policy,
        "max_road_edges_considered": keep_n,
    }

