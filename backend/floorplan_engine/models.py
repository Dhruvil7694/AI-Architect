"""
floorplan_engine/models.py
--------------------------
Pure-Python dataclasses for the circulation core engine.

Every geometry result carries **dual coordinates** (R1-8):
  - ``local_m``  — local metres frame (origin at footprint min-L, min-S)
  - ``dxf``      — DXF feet frame (original coordinate system)

No Django ORM — all geometry is Shapely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from shapely.geometry import LineString, MultiLineString, Polygon


# ── Axis frame ───────────────────────────────────────────────────────────────

@dataclass
class AxisFrame:
    """Principal-axis coordinate frame for DXF ↔ local-metre projection."""

    origin_dxf: tuple[float, float]     # DXF point at L=0, S=0
    l_vec_dxf: tuple[float, float]      # DXF displacement per 1 metre along L
    s_vec_dxf: tuple[float, float]      # DXF displacement per 1 metre along S
    length_m: float                     # footprint extent along L
    width_m: float                      # footprint extent along S
    rotation_deg: float                 # L-axis angle for audit


# ── Dual geometry wrapper ────────────────────────────────────────────────────

@dataclass
class DualGeom:
    """Polygon stored in both local-metre and DXF-feet frames."""

    local_m: Polygon
    dxf: Polygon


# ── Component results ────────────────────────────────────────────────────────

@dataclass
class LiftResult:
    n_lifts: int
    shaft_geoms: list[DualGeom]
    total_width_m: float
    total_depth_m: float


@dataclass
class StairResult:
    n_stairs: int
    stair_geoms: list[DualGeom]
    stair_centroids_m: list[tuple[float, float]]
    separation_m: float
    separation_ok: bool


@dataclass
class CoreBlock:
    block_geom: DualGeom                # bounding box of core
    lift_geoms: list[DualGeom]
    lobby_geom: DualGeom
    core_width_m: float
    core_depth_m: float
    # Stairs only present for POINT_CORE
    stair_geoms: list[DualGeom] = field(default_factory=list)


@dataclass
class CorridorResult:
    corridor_geom: Optional[DualGeom]
    centerline: Optional[LineString | MultiLineString]   # R1-9, R2-5
    corridor_length_m: float
    corridor_width_m: float


# ── Circulation graph ────────────────────────────────────────────────────────

# Node type constants (R2-9)
NODE_LOBBY = "LOBBY"
NODE_LIFT = "LIFT"
NODE_STAIR = "STAIR"
NODE_CORRIDOR = "CORRIDOR"
NODE_CORRIDOR_END = "CORRIDOR_END"


@dataclass
class CirculationNode:
    node_id: str
    node_type: str                      # one of NODE_* constants
    centroid_m: tuple[float, float]
    polygon: Optional[DualGeom]         # None for CORRIDOR_END (point node)
    degree: int = 0                     # R2-6: computed after edge creation


@dataclass
class CirculationEdge:
    from_id: str
    to_id: str
    distance_m: float                   # R2-5: path distance, not Euclidean


@dataclass
class CirculationGraph:
    nodes: list[CirculationNode] = field(default_factory=list)
    edges: list[CirculationEdge] = field(default_factory=list)

    def dead_end_nodes(self) -> list[CirculationNode]:
        """R2-6: nodes with degree == 1 (potential dead-end exits)."""
        return [n for n in self.nodes if n.degree == 1]

    def node_by_id(self, node_id: str) -> Optional[CirculationNode]:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def edges_from(self, node_id: str) -> list[CirculationEdge]:
        return [e for e in self.edges
                if e.from_id == node_id or e.to_id == node_id]


# ── Top-level result ─────────────────────────────────────────────────────────

@dataclass
class CoreLayoutResult:
    core_type: str
    frame: AxisFrame
    core_blocks: list[CoreBlock]
    stairs: StairResult
    corridor: CorridorResult
    graph: CirculationGraph
    metrics: dict[str, Any]
    compliance: dict[str, Any]
    capacity: Any = None                # CapacityMetrics | None
    geojson: dict[str, Any] = field(default_factory=dict)
