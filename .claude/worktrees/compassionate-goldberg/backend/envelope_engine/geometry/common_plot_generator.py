"""
geometry/common_plot_generator.py
----------------------------------
GDCR-compliant Common Open Plot (COP) generation.

Implements generate_common_plot(plot_polygon, envelope_polygon, required_area)
returning a valid COP polygon that:
  - area >= required_area
  - minimum dimension >= 7.5 m (configurable)
  - does not overlap building envelope or required setbacks
  - prefers placement near road-facing edge when possible
  - uses simple (rectangular) geometry

All geometry in DXF feet unless noted.
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple, Union

from shapely.geometry import Polygon, box, LineString

from common.units import sqft_to_sqm, sqm_to_sqft, metres_to_dxf, dxf_to_metres
from rules_engine.rules.loader import get_gdcr_config

logger = logging.getLogger(__name__)

# Tolerance for overlap checks (sq.ft)
_COP_OVERLAP_TOLERANCE_SQFT = 0.01

# Default minimum dimension per GDCR 2017 (metres)
DEFAULT_MIN_DIMENSION_M = 7.5


def _get_cop_min_dimension_m() -> float:
    """Read minimum COP dimension from GDCR (metres). Prefer minimum_dimension_m else min of width/depth."""
    try:
        gdcr = get_gdcr_config()
        cop = gdcr.get("common_open_plot", {}) or {}
        min_dim = cop.get("minimum_dimension_m")
        if min_dim is None:
            geom = cop.get("geometry_constraints") or {}
            min_dim = geom.get("minimum_dimension_m")
        if min_dim is not None:
            return float(min_dim)
        w = float(geom.get("minimum_width_m", 0) or 0)
        d = float(geom.get("minimum_depth_m", 0) or 0)
        if w > 0 and d > 0:
            return min(w, d)
        return DEFAULT_MIN_DIMENSION_M
    except Exception:
        return DEFAULT_MIN_DIMENSION_M


def _rectangle_dimensions_for_area(
    required_area_sqft: float,
    min_side_dxf: float,
) -> Tuple[float, float]:
    """
    Return (width_dxf, depth_dxf) for a rectangle with area ≈ required_area_sqft
    (at least required) and both sides >= min_side_dxf. Prefer minimal area (≈ required).
    """
    if required_area_sqft <= 0 or min_side_dxf <= 0:
        return min_side_dxf, min_side_dxf
    # Minimize area while meeting: w >= min_side, d >= min_side, w*d >= required.
    s = max(min_side_dxf, math.sqrt(required_area_sqft))
    # Use square so area is not oversized
    w = max(min_side_dxf, s)
    d = max(min_side_dxf, required_area_sqft / w if w > 0 else min_side_dxf)
    if w * d < required_area_sqft:
        d = required_area_sqft / w
    return w, d


def _minimum_rectangle_with_area_and_min_side(
    min_area_sqft: float,
    min_side_dxf: float,
) -> Tuple[float, float]:
    """Alias for backward compatibility; targets area ≈ required."""
    return _rectangle_dimensions_for_area(min_area_sqft, min_side_dxf)


def _rect_inside_polygon(
    poly: Polygon,
    cx: float,
    cy: float,
    width_dxf: float,
    depth_dxf: float,
    angle_rad: float = 0.0,
) -> Optional[Polygon]:
    """Build axis-aligned or rotated rectangle centered at (cx, cy) and intersect with poly."""
    hw, hd = width_dxf / 2.0, depth_dxf / 2.0
    if angle_rad == 0:
        r = box(cx - hw, cy - hd, cx + hw, cy + hd)
    else:
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        dx1, dy1 = hw * cos_a - hd * sin_a, hw * sin_a + hd * cos_a
        dx2, dy2 = -hw * cos_a - hd * sin_a, -hw * sin_a + hd * cos_a
        dx3, dy3 = -dx1, -dy1
        dx4, dy4 = -dx2, -dy2
        r = Polygon([
            (cx + dx1, cy + dy1),
            (cx + dx2, cy + dy2),
            (cx + dx3, cy + dy3),
            (cx + dx4, cy + dy4),
        ])
    inter = poly.intersection(r)
    if inter.is_empty:
        return None
    if isinstance(inter, Polygon) and inter.is_valid and inter.area >= 1e-6:
        return inter
    if hasattr(inter, "geoms"):
        best = max(inter.geoms, key=lambda g: g.area if hasattr(g, "area") else 0)
        if isinstance(best, Polygon) and best.is_valid and best.area >= 1e-6:
            return best
    return None


def _min_dimension_dxf(poly: Polygon) -> float:
    """Approximate minimum dimension of a polygon (shortest side of minimum rotated rectangle)."""
    try:
        mrr = poly.minimum_rotated_rectangle
        if mrr is None or mrr.is_empty:
            return 0.0
        coords = list(mrr.exterior.coords)
        if len(coords) < 4:
            return 0.0
        sides = []
        for i in range(len(coords) - 1):
            a = coords[i]
            b = coords[i + 1]
            sides.append(math.hypot(b[0] - a[0], b[1] - a[1]))
        return min(sides) if sides else 0.0
    except Exception:
        return 0.0


def _available_zone_near_road(
    plot_polygon: Polygon,
    envelope_polygon: Polygon,
    road_facing_edge_indices: List[int],
    depth_from_road_dxf: float = 50.0,
) -> Optional[Polygon]:
    """
    Return the part of (plot - envelope) that is near the road-facing edge,
    as a polygon (or largest component). Used to place COP near road.
    """
    try:
        available = plot_polygon.difference(envelope_polygon)
        if available.is_empty:
            return None
        if isinstance(available, Polygon):
            parts = [available]
        else:
            parts = list(available.geoms) if hasattr(available, "geoms") else []
        if not parts:
            return None
        coords = list(plot_polygon.exterior.coords)[:-1]
        n = len(coords)
        if n < 3 or not road_facing_edge_indices:
            return max(parts, key=lambda p: getattr(p, "area", 0))
        # Build a strip along the first road edge: edge + inward buffer
        idx = road_facing_edge_indices[0] % n
        i2 = (idx + 1) % n
        p1 = coords[idx]
        p2 = coords[i2]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-10:
            return max(parts, key=lambda p: getattr(p, "area", 0))
        nx = -dy / length
        ny = dx / length
        edge_linestring = LineString([p1, p2])
        strip = edge_linestring.buffer(depth_from_road_dxf, cap_style=2, join_style=2)
        zone_near_road = strip.intersection(plot_polygon).difference(envelope_polygon)
        if zone_near_road.is_empty:
            return max(parts, key=lambda p: getattr(p, "area", 0))
        if isinstance(zone_near_road, Polygon) and zone_near_road.area >= 1e-6:
            return zone_near_road
        if hasattr(zone_near_road, "geoms"):
            return max(zone_near_road.geoms, key=lambda g: getattr(g, "area", 0))
        return max(parts, key=lambda p: getattr(p, "area", 0))
    except Exception:
        return None


def _cop_touches_road(cop: Polygon, road_linestrings: List[LineString], buffer_dxf: float = 0.5) -> bool:
    """Return True if COP touches or is within buffer_dxf of any road centreline."""
    if not cop or not road_linestrings:
        return True
    try:
        cop_buf = cop.buffer(buffer_dxf)
        for ls in road_linestrings:
            if ls is None or ls.is_empty:
                continue
            if cop_buf.intersects(ls):
                return True
        return False
    except Exception:
        return False


def generate_common_plot(
    plot_polygon: Polygon,
    envelope_polygon: Polygon,
    required_area_sqft: float,
    *,
    min_width_m: Optional[float] = None,
    road_facing_edge_indices: Optional[List[int]] = None,
    setback_polygon: Optional[Polygon] = None,
    internal_road_linestrings: Optional[List[LineString]] = None,
) -> Optional[Polygon]:
    """
    Generate a valid COP polygon: area ≈ required minimum, near road when possible,
    rectangular, optionally touching internal road. Validates: inside plot, no overlap setbacks.

    Constraints:
      - COP area >= required_area_sqft (target ≈ required to avoid oversized COP)
      - Minimum dimension >= min_width_m (default from GDCR, else 7.5 m)
      - COP does not overlap envelope or setbacks
      - Prefers placement near road-facing edge
      - Rectangular when possible
      - If internal_road_linestrings given, COP must touch at least one
    """
    if plot_polygon is None or plot_polygon.is_empty or envelope_polygon is None:
        return None
    if required_area_sqft <= 0:
        return None

    min_dim_m = min_width_m if min_width_m is not None else _get_cop_min_dimension_m()
    min_side_dxf = metres_to_dxf(min_dim_m)
    width_dxf, depth_dxf = _rectangle_dimensions_for_area(required_area_sqft, min_side_dxf)

    def _valid_cop(cop: Polygon) -> bool:
        if cop is None or cop.is_empty or not cop.is_valid:
            return False
        if cop.area < required_area_sqft * 0.99:
            return False
        if _min_dimension_dxf(cop) < min_side_dxf * 0.99:
            return False
        if not plot_polygon.contains(cop) and not cop.within(plot_polygon):
            try:
                if plot_polygon.intersection(cop).area < cop.area * 0.99:
                    return False
            except Exception:
                return False
        if setback_polygon is not None and not setback_polygon.is_empty:
            try:
                overlap = cop.intersection(setback_polygon).area
                if overlap > _COP_OVERLAP_TOLERANCE_SQFT:
                    return False
            except Exception:
                return False
        if internal_road_linestrings and not _cop_touches_road(cop, internal_road_linestrings):
            return False
        return True

    def _try_place(part: Polygon) -> Optional[Polygon]:
        if part.is_empty or part.area < required_area_sqft * 0.99 or not part.is_valid:
            return None
        part = part.buffer(0) if not part.is_valid else part
        try:
            c = part.centroid
            cx, cy = float(c.x), float(c.y)
        except Exception:
            return None
        for w, d in [(width_dxf, depth_dxf), (depth_dxf, width_dxf)]:
            rect = _rect_inside_polygon(part, cx, cy, w, d, 0.0)
            if rect is not None and _valid_cop(rect):
                return rect
        return None

    # 1) Try zone near road first (when road_facing_edge_indices given)
    best_cop: Optional[Polygon] = None
    near_road_zone = _available_zone_near_road(
        plot_polygon, envelope_polygon, road_facing_edge_indices or [], depth_from_road_dxf=min(100.0, max(30.0, math.sqrt(required_area_sqft) * 2)),
    )
    if near_road_zone is not None:
        best_cop = _try_place(near_road_zone)
        if best_cop is not None:
            logger.info(
                "generate_common_plot: COP placed near road, area %.1f sq.ft (required %.1f).",
                best_cop.area, required_area_sqft,
            )
            return best_cop

    # 2) Try all available parts (plot - envelope)
    try:
        available = plot_polygon.difference(envelope_polygon)
    except Exception:
        available = plot_polygon
    if available.is_empty:
        return None
    parts = [available] if isinstance(available, Polygon) else (list(available.geoms) if hasattr(available, "geoms") else [])
    for part in parts:
        cand = _try_place(part)
        if cand is not None:
            if best_cop is None or cand.area <= best_cop.area:
                best_cop = cand
            break
    if best_cop is not None:
        logger.info(
            "generate_common_plot: COP area %.1f sq.ft (required %.1f), min dim %.2f m.",
            best_cop.area, required_area_sqft, min_dim_m,
        )
        return best_cop

    logger.warning(
        "generate_common_plot: no valid COP (required %.1f sq.ft, min side %.2f m).",
        required_area_sqft, min_dim_m,
    )
    return None
