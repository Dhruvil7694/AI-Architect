"""
architecture.feasibility.plot_metrics
-------------------------------------

Deterministic plot-level metrics used in feasibility reports.

This module does NOT run the envelope engine.  It assumes the caller
already has:
  - plot_geom_wkt      : Plot polygon in DXF feet (SRID=0).
  - plot_area_sqft     : Plot area in sq.ft (DXF native).
  - edge_margin_audit  : List[dict] from margin_audit_log()
                         (contains edge_type, p1, p2, length_dxf, ...).

All heavy lifting (setbacks, coverage, common plot carving) remains in
the envelope engine.  Here we only perform O(N) arithmetic on existing
vertices and audit logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import Iterable, List, Optional
import logging

from shapely import wkt as shapely_wkt

from common.units import dxf_to_metres
from architecture.regulatory_accessors import get_height_band


logger = logging.getLogger(__name__)


@dataclass
class PlotMetrics:
    """Scalar plot metrics in mixed units (explicitly documented)."""

    # Areas
    plot_area_sqft: float
    plot_area_sqm: float

    # Linear plot characteristics
    frontage_length_m: float
    plot_depth_m: Optional[float]
    n_road_edges: int
    is_corner_plot: bool

    # Shape & height classification
    shape_class: str          # "RECTANGULAR" | "IRREGULAR"
    height_band_label: str    # "LOW_RISE" | "MID_RISE" | "HIGH_RISE"


def compute_plot_metrics(
    *,
    plot_geom_wkt: str,
    plot_area_sqft: float,
    plot_area_sqm: float,
    edge_margin_audit: Iterable[dict],
    building_height_m: float,
) -> PlotMetrics:
    """
    Compute deterministic plot metrics from existing geometry artefacts.

    Parameters
    ----------
    plot_geom_wkt      : WKT for Plot.geom (DXF feet).
    plot_area_sqft     : Plot area in sq.ft (canonical stored unit).
    plot_area_sqm      : Same area in sq.m (pre-converted for convenience).
    edge_margin_audit  : Output of margin_audit_log(), one dict per edge.
    building_height_m  : Proposed building height in metres.
    """
    audit_list = list(edge_margin_audit)
    frontage_m = _compute_frontage_length_m(audit_list)
    n_road = _count_road_edges(audit_list)
    is_corner = n_road >= 2

    poly = shapely_wkt.loads(plot_geom_wkt)
    depth_m = _compute_plot_depth_m(poly, audit_list)
    shape = _classify_shape(poly)
    height_band = _height_band_for_height(building_height_m)

    return PlotMetrics(
        plot_area_sqft=plot_area_sqft,
        plot_area_sqm=plot_area_sqm,
        frontage_length_m=frontage_m,
        plot_depth_m=depth_m,
        n_road_edges=n_road,
        is_corner_plot=is_corner,
        shape_class=shape,
        height_band_label=height_band,
    )


def _compute_frontage_length_m(edge_margin_audit: List[dict]) -> float:
    """
    Sum ROAD edge lengths from edge_margin_audit and convert to metres.
    """
    total_dxf = 0.0
    for e in edge_margin_audit:
        if e.get("edge_type") == "ROAD":
            total_dxf += float(e.get("length_dxf", 0.0))
    return dxf_to_metres(total_dxf)


def _count_road_edges(edge_margin_audit: List[dict]) -> int:
    """Count how many edges are tagged as ROAD."""
    return sum(1 for e in edge_margin_audit if e.get("edge_type") == "ROAD")


def _compute_plot_depth_m(poly, edge_margin_audit: List[dict]) -> Optional[float]:
    """
    Compute plot depth in metres, measured perpendicular to primary road edge.

    We take the first ROAD edge from edge_margin_audit as the primary road.
    The depth is the thickness of the polygon along the unit normal to this edge
    (projection of all exterior vertices onto that normal; span = t_max - t_min).

    We do NOT use minimum bounding rectangle (MBR) or any fallback axis. For
    L-shaped, trapezoidal, or corner-skewed plots, depth is strictly "extent
    along the road normal"; if the architect uses a different convention (e.g.
    MBR depth), values may differ — see feasibility RISKS.md.
    Returns None if no ROAD edge is declared or geometry is degenerate.
    """
    # Find primary ROAD edge
    primary = None
    for e in edge_margin_audit:
        if e.get("edge_type") == "ROAD":
            primary = e
            break
    if primary is None:
        return None

    p1 = primary.get("p1")
    p2 = primary.get("p2")
    if not (isinstance(p1, (list, tuple)) and isinstance(p2, (list, tuple))):
        return None

    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    dx = x2 - x1
    dy = y2 - y1
    length = hypot(dx, dy)
    if length <= 0:
        return None

    # Unit normal (any perpendicular direction — sign does not matter)
    nx = -dy / length
    ny = dx / length

    # Project all exterior vertices onto this normal
    coords = list(poly.exterior.coords)
    if not coords:
        return None

    ts = [c[0] * nx + c[1] * ny for c in coords]
    t_min = min(ts)
    t_max = max(ts)
    depth_dxf = max(0.0, t_max - t_min)
    depth_m = dxf_to_metres(depth_dxf)
    if depth_m <= 0.0:
        logger.warning("Plot depth computation returned non-positive value (depth_m=%.3f).", depth_m)
    return depth_m


def _classify_shape(poly) -> str:
    """
    Classify plot shape as RECTANGULAR or IRREGULAR.

    Criteria:
      - area_ratio = area(plot) / area(minimum_rotated_rectangle) >= 0.98
      - all edges of the minimum_rotated_rectangle are within 2° of 0/90°.
    """
    try:
        mbr = poly.minimum_rotated_rectangle
    except Exception:
        return "IRREGULAR"

    area_poly = float(poly.area or 0.0)
    area_mbr = float(mbr.area or 0.0)
    if area_mbr <= 0.0:
        return "IRREGULAR"

    area_ratio = area_poly / area_mbr

    # Check orthogonality of MBR edges
    coords = list(mbr.exterior.coords)
    # Shapely repeats first vertex at end
    if len(coords) < 4:
        return "IRREGULAR"
    edges = []
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        if hypot(dx, dy) <= 0:
            continue
        angle = abs(_normalize_angle_deg(degrees(atan2(dy, dx))))
        # Reduce to [0, 90]
        angle = min(angle, 180.0 - angle)
        edges.append(angle)

    # All edges should be close to 0° or 90° in this reduced space
    angle_ok = all(abs(a) <= 2.0 or abs(a - 90.0) <= 2.0 for a in edges)

    if area_ratio >= 0.98 and angle_ok:
        return "RECTANGULAR"
    return "IRREGULAR"


def _normalize_angle_deg(angle: float) -> float:
    """Normalize angle to range [0, 180)."""
    a = angle % 180.0
    if a < 0:
        a += 180.0
    return a


def _height_band_for_height(height_m: float) -> str:
    """
    Map building height to LOW_RISE / MID_RISE / HIGH_RISE.

    Delegates to the GDCR.yaml-driven accessor in architecture.regulatory_accessors.
    """
    return get_height_band(height_m)

