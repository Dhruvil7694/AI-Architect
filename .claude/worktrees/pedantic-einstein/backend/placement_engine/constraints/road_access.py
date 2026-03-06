"""
placement_engine/constraints/road_access.py
-------------------------------------------
Road-access validation helpers for tower footprints.

Unit contract
-------------
- All geometries are in DXF feet (SRID=0), consistent with the placement engine.
- Public helpers expose distances in metres for reporting, but internally compare
  using DXF units to avoid repeated conversions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from shapely.geometry.base import BaseGeometry
from shapely.geometry import Polygon
from shapely.ops import unary_union

from placement_engine.geometry import METRES_TO_DXF, DXF_TO_METRES


DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M: float = 20.0


@dataclass
class RoadAccessResult:
    """Simple structured result for a single tower's road access check."""

    ok: bool
    distance_m: float
    threshold_m: float


def _normalise_road_geom(
    road_corridors: Optional[Iterable[BaseGeometry]] | BaseGeometry,
) -> Optional[BaseGeometry]:
    """
    Return a single Shapely geometry representing all road corridors.

    Accepts:
      - None → None
      - A single geometry → returned as-is
      - An iterable of geometries → unary_union
    """
    if road_corridors is None:
        return None

    if isinstance(road_corridors, BaseGeometry):
        if road_corridors.is_empty:
            return None
        return road_corridors

    # Iterable of geometries
    geoms = [g for g in road_corridors if g is not None and not g.is_empty]
    if not geoms:
        return None
    try:
        merged = unary_union(geoms)
        if merged is not None and not merged.is_empty:
            return merged
    except Exception:  # noqa: BLE001
        # Fallback: return first non-empty geometry
        return geoms[0]
    return None


def validate_tower_access(
    tower_polygon: Polygon,
    road_corridors: Optional[Iterable[BaseGeometry]] | BaseGeometry,
    max_distance_m: float = DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M,
) -> RoadAccessResult:
    """
    Validate that a single tower footprint has vehicular access to the road network.

    The metric used is the minimum Euclidean distance from the tower footprint
    polygon to the road corridor polygons. A distance of 0 means the footprint
    touches the corridor (best), and any distance <= max_distance_m is considered
    to have acceptable access.
    """
    if tower_polygon is None or tower_polygon.is_empty:
        # Degenerate footprint: treat as failing with zero distance.
        return RoadAccessResult(ok=False, distance_m=0.0, threshold_m=max_distance_m)

    road_geom = _normalise_road_geom(road_corridors)
    if road_geom is None:
        # No road geometry available — caller can decide how to interpret this.
        # For now we treat as "cannot evaluate" but not a hard fail.
        return RoadAccessResult(ok=True, distance_m=0.0, threshold_m=max_distance_m)

    try:
        dist_dxf = float(tower_polygon.distance(road_geom))
    except Exception:  # noqa: BLE001
        return RoadAccessResult(ok=False, distance_m=0.0, threshold_m=max_distance_m)

    # Compare in DXF, report in metres.
    threshold_dxf = max_distance_m * METRES_TO_DXF
    ok = dist_dxf <= threshold_dxf + 1e-6
    distance_m = dist_dxf * DXF_TO_METRES
    return RoadAccessResult(ok=ok, distance_m=distance_m, threshold_m=max_distance_m)


def all_towers_have_road_access(
    tower_polygons: Sequence[Polygon],
    road_corridors: Optional[Iterable[BaseGeometry]] | BaseGeometry,
    max_distance_m: float = DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M,
) -> bool:
    """
    Return True iff every tower footprint passes road-access validation.

    Intended for use during layout evaluation: layouts that fail this check
    should be discarded (similar to spacing failures) before scoring by BUA.
    """
    if not tower_polygons:
        return True

    road_geom = _normalise_road_geom(road_corridors)
    if road_geom is None:
        # No corridors — skip access constraint to avoid blocking pipelines
        # where internal roads have not been generated yet.
        return True

    threshold_dxf = max_distance_m * METRES_TO_DXF
    for poly in tower_polygons:
        if poly is None or poly.is_empty:
            continue
        try:
            dist_dxf = float(poly.distance(road_geom))
        except Exception:  # noqa: BLE001
            return False
        if dist_dxf > threshold_dxf + 1e-6:
            return False
    return True

