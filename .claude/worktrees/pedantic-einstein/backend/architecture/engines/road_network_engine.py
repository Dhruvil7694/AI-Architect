"""
architecture.engines.road_network_engine
---------------------------------------
Internal circulation road network for site planning.

Responsibilities:
  1. Detect road-facing boundary of plot (entry edge)
  2. Create entry point (midpoint of road edge)
  3. Generate internal spine road (from entry toward plot interior)
  4. Connect spine road to COP (if COP present)
  5. Reserve circulation corridor for towers (buffer along centreline)

Internal road minimum width: 6 m (configurable via GDCR or parameter).
Output: list of Shapely LineString centreline geometries (DXF feet).
Caller can buffer by width/2 to get corridor polygons for envelope subtraction.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from shapely.geometry import LineString, Point, Polygon

from common.units import metres_to_dxf

logger = logging.getLogger(__name__)

# Default minimum internal road width (metres)
DEFAULT_INTERNAL_ROAD_WIDTH_M = 6.0


def _get_internal_road_width_m() -> float:
    """Read internal road width from GDCR if present."""
    try:
        from rules_engine.rules.loader import get_gdcr_config
        gdcr = get_gdcr_config()
        # Optional key; not all GDCR.yaml have this
        val = (gdcr.get("internal_circulation") or {}).get("minimum_road_width_m")
        if val is not None:
            return float(val)
    except Exception:
        pass
    return DEFAULT_INTERNAL_ROAD_WIDTH_M


def _plot_exterior_ring(poly: Polygon) -> List[Tuple[float, float]]:
    """Return list of (x,y) for exterior ring (no repeated closing point)."""
    if poly is None or poly.is_empty or not poly.exterior:
        return []
    return list(poly.exterior.coords)[:-1]


def _edge_midpoint(coords: List[Tuple[float, float]], edge_index: int) -> Optional[Tuple[float, float]]:
    """Return midpoint of edge at index (0-based)."""
    if not coords or edge_index < 0:
        return None
    n = len(coords)
    i = edge_index % n
    j = (i + 1) % n
    a = coords[i]
    b = coords[j]
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def _inward_normal_at_edge(coords: List[Tuple[float, float]], edge_index: int) -> Tuple[float, float]:
    """
    For CCW polygon, edge i is from coords[i] to coords[i+1].
    Inward normal = 90° left of edge direction (pointing into plot).
    """
    n = len(coords)
    i = edge_index % n
    j = (i + 1) % n
    dx = coords[j][0] - coords[i][0]
    dy = coords[j][1] - coords[i][1]
    length = math.hypot(dx, dy)
    if length < 1e-10:
        return (0.0, 0.0)
    # Edge direction (i->j). Left normal = (-dy, dx); inward for CCW = (-dy, dx) normalized
    nx = -dy / length
    ny = dx / length
    return (nx, ny)


@dataclass
class RoadNetworkResult:
    """Result of internal road network generation."""
    status: str  # "VALID" | "NO_ENTRY" | "ERROR"
    centreline_linestrings: List[LineString] = field(default_factory=list)
    road_corridor_polygons: List[Polygon] = field(default_factory=list)
    entry_point: Optional[Tuple[float, float]] = None
    tower_access_nodes: List[Tuple[float, float]] = field(default_factory=list)
    road_width_m: float = DEFAULT_INTERNAL_ROAD_WIDTH_M
    road_width_dxf: float = 0.0
    error_message: str = ""


def generate_internal_road_network(
    plot_polygon: Polygon,
    envelope_polygon: Optional[Polygon],
    cop_polygon: Optional[Polygon],
    road_facing_edge_indices: List[int],
    *,
    road_width_m: Optional[float] = None,
    spine_length_ratio: float = 0.4,
) -> RoadNetworkResult:
    """
    Generate internal circulation road: entry detection, spine, mandatory COP connection,
    tower access nodes along spine. Returns centreline LineStrings and road corridor polygons.

    Steps:
      1. Road entry = midpoint of first road-facing edge (or longest edge fallback).
      2. Spine: from entry inward along inward normal (length = spine_length_ratio × plot depth).
      3. Mandatory connection to COP when COP present: spine end → COP (clip to plot).
      4. Tower access nodes: points along spine at regular intervals for tower access.
      5. Road corridor polygons = buffer(centreline, width_dxf/2). Minimum width 6 m.
    """
    result = RoadNetworkResult(
        status="ERROR",
        road_width_m=road_width_m or _get_internal_road_width_m(),
    )
    result.road_width_dxf = metres_to_dxf(result.road_width_m)

    if plot_polygon is None or plot_polygon.is_empty:
        result.error_message = "Plot polygon is empty"
        return result

    coords = _plot_exterior_ring(plot_polygon)
    if len(coords) < 3:
        result.error_message = "Plot has no valid exterior ring"
        return result

    if not road_facing_edge_indices:
        # Fallback: use longest edge as "road"
        lengths = []
        for i in range(len(coords)):
            j = (i + 1) % len(coords)
            lengths.append(
                math.hypot(coords[j][0] - coords[i][0], coords[j][1] - coords[i][1])
            )
        road_facing_edge_indices = [max(range(len(lengths)), key=lambda i: lengths[i])]

    entry_edge = road_facing_edge_indices[0]
    entry_pt = _edge_midpoint(coords, entry_edge)
    if entry_pt is None:
        result.status = "NO_ENTRY"
        result.error_message = "Could not compute entry point"
        return result

    result.entry_point = entry_pt
    nx, ny = _inward_normal_at_edge(coords, entry_edge)

    # Plot depth along inward normal (approximate)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    projections = [x * nx + y * ny for x, y in zip(xs, ys)]
    depth_extent = max(projections) - min(projections) if projections else 50.0
    spine_length_dxf = depth_extent * max(0.1, min(0.8, spine_length_ratio))

    # Spine segment: entry -> entry + inward * spine_length
    end_x = entry_pt[0] + nx * spine_length_dxf
    end_y = entry_pt[1] + ny * spine_length_dxf
    spine = LineString([entry_pt, (end_x, end_y)])

    # Clip spine to plot (optional: avoid envelope overlap by stopping at envelope boundary)
    try:
        spine_clipped = spine.intersection(plot_polygon)
        if spine_clipped.is_empty:
            spine_clipped = spine
        elif hasattr(spine_clipped, "geoms"):
            # Take longest segment
            geoms = list(spine_clipped.geoms)
            if geoms:
                spine_clipped = max(geoms, key=lambda g: g.length if hasattr(g, "length") else 0)
        if isinstance(spine_clipped, LineString) and not spine_clipped.is_empty:
            spine = spine_clipped
    except Exception:
        pass

    lines: List[LineString] = [spine]

    # Mandatory connection to COP when COP present
    if cop_polygon is not None and not cop_polygon.is_empty and cop_polygon.is_valid:
        try:
            c = cop_polygon.centroid
            cop_cx, cop_cy = float(c.x), float(c.y)
        except Exception:
            cop_cx, cop_cy = end_x, end_y
        if hasattr(spine, "coords"):
            spine_pts = list(spine.coords)
            spine_end = spine_pts[-1] if spine_pts else (end_x, end_y)
        else:
            spine_end = (end_x, end_y)
        try:
            conn = LineString([spine_end, (cop_cx, cop_cy)])
            conn_clip = conn.intersection(plot_polygon)
            if not conn_clip.is_empty:
                if isinstance(conn_clip, LineString) and conn_clip.length > 1e-6:
                    lines.append(conn_clip)
                elif hasattr(conn_clip, "geoms"):
                    for g in conn_clip.geoms:
                        if isinstance(g, LineString) and g.length > 1e-6:
                            lines.append(g)
                            break
        except Exception:
            pass

    # Tower access nodes along spine (and first segment of connection if present)
    tower_nodes: List[Tuple[float, float]] = [entry_pt]
    try:
        spine_coords = list(spine.coords)
        if len(spine_coords) >= 2:
            n = max(2, min(5, len(spine_coords)))
            for i in range(1, n):
                idx = int(i * (len(spine_coords) - 1) / (n - 1))
                idx = min(idx, len(spine_coords) - 1)
                pt = spine_coords[idx]
                tower_nodes.append((float(pt[0]), float(pt[1])))
        if lines and len(lines) > 1 and hasattr(lines[1], "coords"):
            conn_coords = list(lines[1].coords)
            if len(conn_coords) >= 2:
                mid = len(conn_coords) // 2
                tower_nodes.append((float(conn_coords[mid][0]), float(conn_coords[mid][1])))
    except Exception:
        pass
    result.tower_access_nodes = tower_nodes

    result.centreline_linestrings = lines
    result.road_corridor_polygons = road_network_corridor_polygons(lines, result.road_width_dxf)
    result.status = "VALID"
    result.error_message = ""
    logger.info(
        "Internal road network: %d segment(s), %d tower nodes, width %.1f m.",
        len(lines),
        len(result.tower_access_nodes),
        result.road_width_m,
    )
    return result


def road_network_corridor_polygons(
    centreline_linestrings: List[LineString],
    width_dxf: float,
) -> List[Polygon]:
    """
    Return list of corridor polygons (buffer along each centreline by width_dxf/2).
    Used to subtract from envelope to reserve circulation.
    """
    polygons: List[Polygon] = []
    for ls in centreline_linestrings:
        if ls is None or ls.is_empty or ls.length < 1e-10:
            continue
        try:
            buf = ls.buffer(width_dxf / 2.0, cap_style=2, join_style=2)
            if isinstance(buf, Polygon) and not buf.is_empty:
                polygons.append(buf)
            elif hasattr(buf, "geoms"):
                for g in buf.geoms:
                    if isinstance(g, Polygon) and not g.is_empty:
                        polygons.append(g)
        except Exception:
            continue
    return polygons
