"""
geometry/edge_classifier.py
----------------------------
Converts a Shapely Polygon + a list of road-facing edge indices into a list
of fully-described EdgeSpec objects, one per exterior edge.

Each EdgeSpec carries:
  - the edge's two endpoints (in DXF coordinate units)
  - its type: ROAD | SIDE | REAR
  - the adjacent road width (for ROAD edges only)
  - the inward unit normal vector (pre-computed for the builder)

Classification rules
--------------------
- Edges supplied in `road_facing_edges` → ROAD
- Among remaining non-road edges:
    - The edge most nearly PARALLEL to the primary road edge (index 0 of
      road_facing_edges) → REAR  (it is "opposite" the road in spirit)
    - All others → SIDE

For corner plots (2 road edges) the logic is the same: the most-parallel
non-road edge is REAR; any other is SIDE.

Polygon orientation
-------------------
Shapely always returns exterior rings in counter-clockwise (CCW) order after
construction.  The inward unit normal for edge i (p1→p2) in a CCW polygon
is the 90°-left rotation of the edge direction:
    normal = (-dy/len, dx/len)

This is the direction that points INTO the polygon interior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from shapely.geometry import Polygon

from envelope_engine.geometry import InsufficientInputError, METRES_TO_DXF


# ── Edge type constants ───────────────────────────────────────────────────────
ROAD = "ROAD"
SIDE = "SIDE"
REAR = "REAR"


@dataclass
class EdgeSpec:
    """
    Describes a single exterior edge of the plot polygon.

    Coordinates are in DXF units (feet, SRID=0).
    Margins are stored both in metres (for the audit log) and DXF units
    (for Shapely operations) — they are populated by MarginResolver.
    """

    index: int                            # 0-based edge index
    p1: tuple[float, float]               # start point (DXF coords)
    p2: tuple[float, float]               # end point (DXF coords)
    length: float                         # edge length in DXF units
    inward_normal: tuple[float, float]    # unit vector pointing inward

    edge_type: str                        # ROAD | SIDE | REAR
    road_width: Optional[float] = None   # metres; only for ROAD edges

    # Populated by MarginResolver after classification
    gdcr_clause: str = ""
    required_margin_m: float = 0.0
    required_margin_dxf: float = 0.0     # = required_margin_m * METRES_TO_DXF


def _edge_direction(p1: tuple, p2: tuple) -> tuple[float, float]:
    """Unit vector from p1 to p2."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-10:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _inward_normal_ccw(p1: tuple, p2: tuple) -> tuple[float, float]:
    """
    Inward unit normal for a CCW polygon.
    Edge direction is (dx, dy); rotate 90° left → (-dy, dx) = inward.
    """
    dx, dy = _edge_direction(p1, p2)
    return (-dy, dx)


def _angle_between_directions(d1: tuple, d2: tuple) -> float:
    """
    Absolute angle (radians, [0, pi/2]) between two unit direction vectors.
    Used to find which edge is most parallel to the road edge.
    """
    dot = d1[0] * d2[0] + d1[1] * d2[1]
    dot = max(-1.0, min(1.0, dot))          # clamp for acos safety
    angle = math.acos(abs(dot))             # abs: direction doesn't matter
    return min(angle, math.pi - angle)      # fold into [0, pi/2]


def classify_edges(
    plot_polygon: Polygon,
    road_facing_edges: List[int],
    road_width: float,
) -> List[EdgeSpec]:
    """
    Classify every exterior edge of `plot_polygon`.

    Parameters
    ----------
    plot_polygon      : Shapely Polygon (will be normalised to CCW orientation)
    road_facing_edges : list of 0-based edge indices that face a road
    road_width        : width of the adjacent road in metres

    Returns
    -------
    List[EdgeSpec] — one per edge, in index order

    Raises
    ------
    InsufficientInputError   if road_facing_edges is empty
    ValueError               if any index is out of range
    """
    if not road_facing_edges:
        raise InsufficientInputError(
            "road_facing_edges must contain at least one edge index. "
            "Declare which edge(s) of the plot face a road."
        )

    # Ensure CCW orientation so inward normals point inside
    if not plot_polygon.exterior.is_ccw:
        plot_polygon = Polygon(list(reversed(list(plot_polygon.exterior.coords))))

    coords = list(plot_polygon.exterior.coords)[:-1]   # drop repeated last point
    n = len(coords)

    for idx in road_facing_edges:
        if idx < 0 or idx >= n:
            raise ValueError(
                f"road_facing_edges index {idx} is out of range for a "
                f"{n}-edge polygon."
            )

    road_set = set(road_facing_edges)
    primary_road_idx = road_facing_edges[0]

    # Direction of primary road edge (used to identify REAR)
    p1_road = coords[primary_road_idx]
    p2_road = coords[(primary_road_idx + 1) % n]
    road_dir = _edge_direction(p1_road, p2_road)

    # Build all EdgeSpec objects (edge_type TBD for non-road edges)
    specs: List[EdgeSpec] = []
    non_road_indices: List[int] = []

    for i in range(n):
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        normal = _inward_normal_ccw(p1, p2)

        if i in road_set:
            spec = EdgeSpec(
                index=i, p1=p1, p2=p2, length=length,
                inward_normal=normal, edge_type=ROAD, road_width=road_width,
            )
        else:
            # Placeholder — will be resolved below
            spec = EdgeSpec(
                index=i, p1=p1, p2=p2, length=length,
                inward_normal=normal, edge_type=SIDE,
            )
            non_road_indices.append(i)

        specs.append(spec)

    # ── Classify non-road edges as SIDE or REAR ──────────────────────────────
    # The edge most nearly parallel to the primary road edge becomes REAR.
    if non_road_indices:
        angles = []
        for i in non_road_indices:
            d = _edge_direction(specs[i].p1, specs[i].p2)
            angles.append(_angle_between_directions(road_dir, d))

        # Smallest angle = most parallel = REAR
        rear_idx_in_list = angles.index(min(angles))
        rear_edge_index = non_road_indices[rear_idx_in_list]
        specs[rear_edge_index].edge_type = REAR

        # All other non-road edges stay SIDE (already set above)

    return specs
