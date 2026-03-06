"""
detailed_layout/geometry_utils.py — low-level geometry helpers for Phase D.

These helpers work on Shapely primitives and are designed to be deterministic
and tolerant to floating-point noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

from shapely.geometry import LineString, Polygon


Point2D = Tuple[float, float]
EdgeKey = Tuple[Point2D, Point2D]


@dataclass(frozen=True)
class ClassifiedEdge:
    """Edge with snapped endpoints and original geometry."""

    key: EdgeKey
    segment: LineString


def snap_coord(value: float, tol: float) -> float:
    """Snap a scalar coordinate to a grid of size tol."""
    if tol <= 0:
        return value
    return round(value / tol) * tol


def snap_point(pt: Point2D, tol: float) -> Point2D:
    """Snap a 2D point to the tolerance grid."""
    x, y = pt
    return (snap_coord(x, tol), snap_coord(y, tol))


def snap_linestring(ls: LineString, tol: float) -> LineString:
    """Return a new LineString with endpoints snapped to the tolerance grid."""
    if ls.is_empty:
        return ls
    coords = list(ls.coords)
    if len(coords) < 2:
        return ls
    p0 = snap_point((coords[0][0], coords[0][1]), tol)
    p1 = snap_point((coords[-1][0], coords[-1][1]), tol)
    return LineString([p0, p1])


def edge_key(p1: Point2D, p2: Point2D, tol: float) -> EdgeKey:
    """
    Directionless edge key: endpoints snapped and sorted lexicographically.

    Ensures (P1→P2) and (P2→P1) normalize to the same key.
    """
    sp1 = snap_point(p1, tol)
    sp2 = snap_point(p2, tol)
    return (sp1, sp2) if sp1 <= sp2 else (sp2, sp1)


def extract_edges(poly: Polygon) -> List[LineString]:
    """Extract exterior edges of a polygon as LineStrings (no duplicates)."""
    if poly.is_empty:
        return []
    coords = list(poly.exterior.coords)
    segments: List[LineString] = []
    for i in range(len(coords) - 1):
        p0 = coords[i]
        p1 = coords[i + 1]
        if (p0[0], p0[1]) == (p1[0], p1[1]):
            continue
        segments.append(LineString([(p0[0], p0[1]), (p1[0], p1[1])]))
    return segments


def merge_collinear_segments(segments: Iterable[LineString], tol: float) -> List[LineString]:
    """
    Simple collinearity-based merge for sets of segments.

    This is deliberately conservative: it only merges segments that share an
    endpoint and whose direction vectors are nearly identical.
    """
    snapped = [snap_linestring(s, tol) for s in segments if not s.is_empty]
    # Index by endpoint for quick adjacency
    by_start: dict[Point2D, List[LineString]] = {}
    for s in snapped:
        p0 = (s.coords[0][0], s.coords[0][1])
        by_start.setdefault(p0, []).append(s)
    # In this initial version we simply return snapped segments; more advanced
    # merging can be added when needed.
    return snapped

