"""
geometry_utils.py
-----------------
Geometry utilities for GIS-grade cartographic rendering.

Provides:
  - Optimal label placement using true polylabel
  - Road centerline extraction from polygon geometries
  - Multi-layer geometry processing
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union

try:
    # Mapbox polylabel port.
    from polylabel import polylabel as _polylabel
except Exception:  # pragma: no cover - handled in get_label_point fallback
    _polylabel = None

logger = logging.getLogger(__name__)


def get_label_point(polygon: Polygon | MultiPolygon, *, tolerance: float = 1.0) -> Point:
    """
    Compute optimal label placement point for a polygon using polylabel.

    polylabel finds the "pole of inaccessibility" (point farthest from the
    polygon boundary), which matches label behavior on irregular shapes.

    This is superior to centroid for:
      - L-shaped plots
      - Narrow/elongated plots
      - Irregular polygons
    
    Parameters
    ----------
    polygon : Shapely Polygon or MultiPolygon
    tolerance : polylabel precision (smaller = more accurate, slower)
    
    Returns
    -------
    Point : Optimal label placement point (guaranteed inside polygon)
    """
    if isinstance(polygon, MultiPolygon):
        # For MultiPolygon, use the largest component
        polygon = max(polygon.geoms, key=lambda p: p.area)

    if _polylabel is None:
        # Dependency missing: keep behavior deterministic and inside the polygon.
        return polygon.representative_point()

    try:
        # polylabel expects: [outerRing, hole1, hole2, ...]
        outer_ring = [[x, y] for (x, y) in polygon.exterior.coords]
        rings = [outer_ring] + [
            [[x, y] for (x, y) in interior.coords] for interior in polygon.interiors
        ]

        x, y = _polylabel(rings, precision=float(tolerance))
        return Point(float(x), float(y))
    except Exception as e:
        logger.warning("polylabel failed; falling back to representative_point: %s", e)
        return polygon.representative_point()


def extract_road_centerline(
    road_polygon: Polygon | MultiPolygon,
    *,
    simplify_tolerance: float = 0.5,
) -> Optional[LineString]:
    """
    Extract centerline from a road polygon.
    
    Strategy:
      1. Find the longest axis of the polygon (approximation)
      2. Use medial axis / skeleton if available
      3. Fallback: longest edge or bounding box diagonal
    
    Parameters
    ----------
    road_polygon        : Road polygon geometry
    simplify_tolerance  : Tolerance for line simplification (DXF units)
    
    Returns
    -------
    LineString or None : Road centerline, or None if extraction fails
    """
    if isinstance(road_polygon, MultiPolygon):
        # Use largest component for multi-part roads
        road_polygon = max(road_polygon.geoms, key=lambda p: p.area)
    
    if not isinstance(road_polygon, Polygon):
        return None
    
    # Strategy 1: use polygon skeleton if available
    try:
        from shapely.ops import skeletonize as shapely_skeletonize  # shapely>=2

        try:
            skel = shapely_skeletonize(road_polygon)
            candidate_lines: list[LineString] = []
            if hasattr(skel, "geoms"):
                for g in skel.geoms:
                    if isinstance(g, LineString):
                        candidate_lines.append(g)
            elif isinstance(skel, LineString):
                candidate_lines.append(skel)

            if candidate_lines:
                centerline = max(candidate_lines, key=lambda l: l.length)
                if simplify_tolerance > 0:
                    centerline = centerline.simplify(
                        simplify_tolerance, preserve_topology=True
                    )
                return centerline
        except Exception as e:
            logger.warning("skeletonize road centerline failed; fallback used: %s", e)
    except Exception:
        # skeletonize not available; fallback to rotated-rectangle approximation
        pass

    # Strategy 2: Use minimum rotated rectangle to find longest axis
    try:
        # Get minimum rotated rectangle
        min_rect = road_polygon.minimum_rotated_rectangle
        
        if min_rect.is_empty or not isinstance(min_rect, Polygon):
            return None
        
        # Extract corners of the rectangle
        coords = list(min_rect.exterior.coords)[:-1]  # Remove duplicate last point
        
        if len(coords) < 4:
            return None
        
        # Find the two longest opposite edges
        edges = []
        for i in range(len(coords)):
            p1 = coords[i]
            p2 = coords[(i + 1) % len(coords)]
            length = ((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)**0.5
            edges.append((length, p1, p2))
        
        edges.sort(reverse=True, key=lambda x: x[0])
        
        # Take the longest edge pair (opposite sides of rectangle)
        if len(edges) >= 2:
            _, p1, p2 = edges[0]
            _, p3, p4 = edges[1]
            
            # Centerline connects midpoints of opposite edges
            mid1 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
            mid2 = ((p3[0] + p4[0]) / 2, (p3[1] + p4[1]) / 2)
            
            centerline = LineString([mid1, mid2])
            
            # Simplify if needed
            if simplify_tolerance > 0:
                centerline = centerline.simplify(simplify_tolerance, preserve_topology=True)
            
            return centerline
    
    except Exception as e:
        logger.warning(f"Failed to extract road centerline: {e}")
        return None
    
    return None


def compute_road_width_from_polygon(road_polygon: Polygon | MultiPolygon) -> float:
    """
    Estimate road width from polygon geometry.
    
    Uses minimum rotated rectangle to find the shorter dimension.
    
    Parameters
    ----------
    road_polygon : Road polygon geometry
    
    Returns
    -------
    float : Estimated road width in DXF units (typically feet)
    """
    if isinstance(road_polygon, MultiPolygon):
        road_polygon = max(road_polygon.geoms, key=lambda p: p.area)
    
    if not isinstance(road_polygon, Polygon):
        return 0.0
    
    try:
        min_rect = road_polygon.minimum_rotated_rectangle
        
        if min_rect.is_empty or not isinstance(min_rect, Polygon):
            return 0.0
        
        coords = list(min_rect.exterior.coords)[:-1]
        
        if len(coords) < 4:
            return 0.0
        
        # Calculate edge lengths
        lengths = []
        for i in range(len(coords)):
            p1 = coords[i]
            p2 = coords[(i + 1) % len(coords)]
            length = ((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)**0.5
            lengths.append(length)
        
        lengths.sort()
        
        # Width is the shorter dimension
        return lengths[0] if lengths else 0.0
    
    except Exception as e:
        logger.warning(f"Failed to compute road width: {e}")
        return 0.0
