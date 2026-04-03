"""
floorplan_engine/graph/circulation_graph.py
-------------------------------------------
Build the circulation connectivity graph.

R2-5: Edge distances use ``centerline.project()`` (path distance along
      the corridor), not Euclidean distance.
R2-9: ``CORRIDOR_END`` nodes for dead-end detection and path sampling.
R2-6: Node degrees computed after edge creation.
"""

from __future__ import annotations

from typing import Optional

from shapely.geometry import LineString, MultiLineString, Point

from floorplan_engine.models import (
    CirculationEdge,
    CirculationGraph,
    CirculationNode,
    CoreBlock,
    CorridorResult,
    DualGeom,
    NODE_CORRIDOR,
    NODE_CORRIDOR_END,
    NODE_LIFT,
    NODE_LOBBY,
    NODE_STAIR,
    StairResult,
)


def build_circulation_graph(
    core_blocks: list[CoreBlock],
    stairs: StairResult,
    corridor: CorridorResult,
) -> CirculationGraph:
    """
    Build a connectivity graph: lift → lobby → corridor → stair.

    Nodes
    -----
    - One per lift shaft
    - One per lobby (per core block)
    - One corridor body node
    - CORRIDOR_END nodes at corridor endpoints (R2-9)
    - One per staircase

    Edges
    -----
    - Lift → Lobby: distance 0 (adjacent)
    - Lobby → Corridor: distance 0 (lobby face connects to corridor)
    - Corridor → Stair: path distance along centerline (R2-5)
    - Corridor → CORRIDOR_END: path distance to endpoint
    """
    graph = CirculationGraph()

    # ── Lobby and lift nodes ─────────────────────────────────────────────
    lobby_ids = []
    for bi, block in enumerate(core_blocks):
        lobby_id = f"lobby_{bi}"
        lc = _centroid_of(block.lobby_geom)
        graph.nodes.append(CirculationNode(
            node_id=lobby_id,
            node_type=NODE_LOBBY,
            centroid_m=lc,
            polygon=block.lobby_geom,
        ))
        lobby_ids.append(lobby_id)

        for li, lift_geom in enumerate(block.lift_geoms):
            lift_id = f"lift_{bi}_{li}"
            graph.nodes.append(CirculationNode(
                node_id=lift_id,
                node_type=NODE_LIFT,
                centroid_m=_centroid_of(lift_geom),
                polygon=lift_geom,
            ))
            # Lift → Lobby: adjacent
            graph.edges.append(CirculationEdge(
                from_id=lift_id, to_id=lobby_id, distance_m=0.0,
            ))

    # ── Stair nodes ──────────────────────────────────────────────────────
    stair_ids = []
    for si in range(stairs.n_stairs):
        stair_id = f"stair_{si}"
        sc = stairs.stair_centroids_m[si] if si < len(stairs.stair_centroids_m) else (0, 0)
        sg = stairs.stair_geoms[si] if si < len(stairs.stair_geoms) else None
        graph.nodes.append(CirculationNode(
            node_id=stair_id,
            node_type=NODE_STAIR,
            centroid_m=sc,
            polygon=sg,
        ))
        stair_ids.append(stair_id)

    # ── Corridor node ────────────────────────────────────────────────────
    centerline = corridor.centerline
    if corridor.corridor_geom is not None:
        corr_centroid = _centroid_of(corridor.corridor_geom)
        graph.nodes.append(CirculationNode(
            node_id="corridor",
            node_type=NODE_CORRIDOR,
            centroid_m=corr_centroid,
            polygon=corridor.corridor_geom,
        ))

        # Lobby → Corridor: adjacent (distance 0)
        for lobby_id in lobby_ids:
            graph.edges.append(CirculationEdge(
                from_id=lobby_id, to_id="corridor", distance_m=0.0,
            ))

        # Corridor → Stair: path distance (R2-5)
        for si, stair_id in enumerate(stair_ids):
            sc = stairs.stair_centroids_m[si] if si < len(stairs.stair_centroids_m) else None
            if sc and centerline:
                dist = _path_distance_to(centerline, sc)
            else:
                dist = 0.0
            graph.edges.append(CirculationEdge(
                from_id="corridor", to_id=stair_id, distance_m=dist,
            ))

        # CORRIDOR_END nodes (R2-9)
        if centerline is not None:
            endpoints = _corridor_endpoints(centerline)
            for ei, ep in enumerate(endpoints):
                end_id = f"corridor_end_{ei}"
                graph.nodes.append(CirculationNode(
                    node_id=end_id,
                    node_type=NODE_CORRIDOR_END,
                    centroid_m=(ep.x, ep.y),
                    polygon=None,
                ))
                # Edge from corridor body to endpoint
                dist = _path_distance_to(centerline, (ep.x, ep.y))
                graph.edges.append(CirculationEdge(
                    from_id="corridor", to_id=end_id, distance_m=dist,
                ))

    # ── Compute degrees (R2-6) ───────────────────────────────────────────
    _compute_degrees(graph)

    return graph


# ── Helpers ──────────────────────────────────────────────────────────────────

def _centroid_of(geom: Optional[DualGeom]) -> tuple[float, float]:
    """Extract centroid from a DualGeom's local_m polygon."""
    if geom is None:
        return (0.0, 0.0)
    c = geom.local_m.centroid
    return (c.x, c.y)


def _path_distance_to(
    centerline: LineString | MultiLineString,
    point: tuple[float, float],
) -> float:
    """
    R2-5: Path distance from the start of the centerline to the
    projection of ``point`` onto the centerline.
    """
    pt = Point(point)
    if isinstance(centerline, MultiLineString):
        # Find which line is closest, project onto that
        best_dist = float("inf")
        for line in centerline.geoms:
            d = line.distance(pt)
            if d < best_dist:
                best_dist = d
                proj = line.project(pt)
        return proj
    return centerline.project(pt)


def _corridor_endpoints(
    centerline: LineString | MultiLineString,
) -> list[Point]:
    """Extract the geometric endpoints of the corridor centerline."""
    if isinstance(centerline, MultiLineString):
        pts = []
        for line in centerline.geoms:
            coords = list(line.coords)
            if coords:
                pts.append(Point(coords[0]))
                pts.append(Point(coords[-1]))
        # Deduplicate points that are very close (shared core center)
        unique = []
        for p in pts:
            if not any(p.distance(u) < 0.1 for u in unique):
                unique.append(p)
        return unique
    else:
        coords = list(centerline.coords)
        if len(coords) >= 2:
            return [Point(coords[0]), Point(coords[-1])]
        return []


def _compute_degrees(graph: CirculationGraph) -> None:
    """R2-6: Set degree on each node = number of connected edges."""
    id_set = {n.node_id for n in graph.nodes}
    for node in graph.nodes:
        node.degree = sum(
            1 for e in graph.edges
            if (e.from_id == node.node_id and e.to_id in id_set)
            or (e.to_id == node.node_id and e.from_id in id_set)
        )
