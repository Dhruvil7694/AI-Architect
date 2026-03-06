"""
placement_engine/geometry/orientation_finder.py
-------------------------------------------------
Discovers the two principal-axis orientation angles of an envelope polygon
by computing its minimum-area bounding rectangle (MBR) via Shapely's
convex-hull rotating-calipers algorithm.

Returns both angles:
    angle_primary   = direction of the MBR's LONGER edge (θ)
    angle_secondary = θ + 90° (perpendicular)

Both candidates are tested by InscribedRectangle so the better footprint
orientation is always selected, not just assumed.

Determinism guarantee
---------------------
Shapely's minimum_rotated_rectangle() is backed by GEOS, which applies the
rotating-calipers algorithm on sorted convex hull vertices.  For identical
input geometry it always returns the same rectangle — same input → same θ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon


@dataclass
class OrientationResult:
    """Output of find_orientation()."""
    angle_primary_deg:   float    # direction of MBR's longer edge (θ)
    angle_secondary_deg: float    # θ + 90°
    mbr_polygon:         Polygon  # minimum bounding rectangle of convex hull
    mbr_long_dim_dxf:    float    # longer dimension of MBR (DXF feet)
    mbr_short_dim_dxf:   float    # shorter dimension of MBR (DXF feet)


def find_orientation(polygon: Polygon) -> OrientationResult:
    """
    Compute the two candidate orientation angles from *polygon*'s convex hull
    minimum bounding rectangle.

    Parameters
    ----------
    polygon : Shapely Polygon
        The envelope polygon (or any sub-component) in DXF feet, SRID=0.

    Returns
    -------
    OrientationResult

    Notes
    -----
    For a degenerate polygon (< 4 distinct vertices after convex hull), the
    fallback is angle_primary = 0°, angle_secondary = 90°.
    """
    hull = polygon.convex_hull

    # Shapely ≥ 2.0 exposes minimum_rotated_rectangle directly on the polygon.
    mbr: Polygon = hull.minimum_rotated_rectangle

    coords = list(mbr.exterior.coords)   # 5 points — last repeats first
    if len(coords) < 4:
        # Degenerate case: axis-aligned fallback
        return OrientationResult(
            angle_primary_deg=0.0,
            angle_secondary_deg=90.0,
            mbr_polygon=mbr,
            mbr_long_dim_dxf=0.0,
            mbr_short_dim_dxf=0.0,
        )

    # Compute the four edge vectors of the MBR
    edges: list[tuple[float, float, float]] = []  # (dx, dy, length)
    for i in range(4):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        length = math.hypot(dx, dy)
        edges.append((dx, dy, length))

    # Identify the LONGER pair of edges (MBR has two pairs of equal-length edges)
    # Edge 0 and edge 2 are one pair; edge 1 and edge 3 are the other pair.
    len_pair_0 = edges[0][2]   # representative length of pair (0, 2)
    len_pair_1 = edges[1][2]   # representative length of pair (1, 3)

    if len_pair_0 >= len_pair_1:
        long_edge  = edges[0]
        mbr_long   = len_pair_0
        mbr_short  = len_pair_1
    else:
        long_edge  = edges[1]
        mbr_long   = len_pair_1
        mbr_short  = len_pair_0

    angle_primary = math.degrees(math.atan2(long_edge[1], long_edge[0]))
    # Normalise to [0°, 180°) — opposite directions are equivalent for rectangle fitting
    angle_primary = angle_primary % 180.0
    angle_secondary = (angle_primary + 90.0) % 180.0

    return OrientationResult(
        angle_primary_deg=angle_primary,
        angle_secondary_deg=angle_secondary,
        mbr_polygon=mbr,
        mbr_long_dim_dxf=mbr_long,
        mbr_short_dim_dxf=mbr_short,
    )
