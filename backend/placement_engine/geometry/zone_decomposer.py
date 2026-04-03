"""
placement_engine/geometry/zone_decomposer.py
---------------------------------------------
Partitions the buildable core (post-fire-loop, post-COP) into adaptive
tower placement zones.

Strategy selection
------------------
1. n_towers == 1           → SINGLE — the whole core minus COP is one zone.
2. Near-convex core        → STRIP  — parallel cut lines along the road normal
   (convexity ratio > 0.85)          (reuses proven split logic from packer).
3. Irregular core          → VORONOI — seed-based Voronoi decomposition adapted
   (L-shaped, skewed, etc.)           to the plot shape.

Zone viability
--------------
Every zone must be able to contain a tower footprint.  If a zone's negative
buffer by min_width_dxf/2 collapses to empty, the zone is too narrow and
gets merged with its neighbour that shares the longest boundary.

Unit contract
-------------
All geometry in DXF feet (SRID=0), consistent with the placement engine.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from shapely.geometry import LineString, MultiPoint, MultiPolygon, Polygon
from shapely.ops import voronoi_diagram

from envelope_engine.geometry.edge_classifier import ROAD, EdgeSpec
from placement_engine.geometry import METRES_TO_DXF, MIN_FOOTPRINT_AREA_SQFT

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class TowerZone:
    """A subdivision of the buildable core where a single tower may be placed."""
    polygon: Polygon
    index: int
    area_sqft: float
    is_road_adjacent: bool = False
    cop_distance_dxf: float = 0.0  # NEW: distance from zone centroid to COP centroid
    cop_facing: bool = False        # NEW: zone shares boundary with COP


@dataclass
class ZoneResult:
    """Result of zone decomposition."""
    zones: List[TowerZone]
    strategy: str            # "SINGLE" | "STRIP" | "VORONOI"
    buildable_core: Polygon  # the input polygon that was decomposed


# ── Convexity check ──────────────────────────────────────────────────────────


def _convexity_ratio(polygon: Polygon) -> float:
    """
    Ratio of polygon area to its convex hull area.
    1.0 = perfectly convex; lower values indicate concavities (L-shape, etc.).
    """
    hull = polygon.convex_hull
    if hull.is_empty or hull.area == 0:
        return 0.0
    return polygon.area / hull.area


# ── Road adjacency check ─────────────────────────────────────────────────────


def _is_zone_road_adjacent(
    zone: Polygon,
    road_edge_specs: List[EdgeSpec],
    touch_threshold_dxf: float = 5.0,
) -> bool:
    """Check if a zone polygon is adjacent to any road edge."""
    for spec in road_edge_specs:
        if spec.edge_type != ROAD:
            continue
        road_line = LineString([spec.p1, spec.p2])
        if zone.distance(road_line) < touch_threshold_dxf:
            return True
    return False


# ── Road-normal angle detection ───────────────────────────────────────────────


def _road_normal_angle_deg(road_edge_specs: List[EdgeSpec]) -> float:
    """
    Return the inward-normal angle (degrees) of the primary road edge.
    This is the direction perpendicular to the road, pointing into the plot.
    Falls back to 0° if no road edge is found.
    """
    road_specs = [s for s in road_edge_specs if s.edge_type == ROAD]
    if not road_specs:
        return 0.0

    # Use the longest road edge
    primary = max(road_specs, key=lambda s: s.length)
    nx, ny = primary.inward_normal
    return math.degrees(math.atan2(ny, nx))


def _road_edge_angle_deg(road_edge_specs: List[EdgeSpec]) -> float:
    """
    Return the direction angle (degrees) along the primary road edge.
    This is the tangent direction, not the normal.
    """
    road_specs = [s for s in road_edge_specs if s.edge_type == ROAD]
    if not road_specs:
        return 0.0

    primary = max(road_specs, key=lambda s: s.length)
    dx = primary.p2[0] - primary.p1[0]
    dy = primary.p2[1] - primary.p1[1]
    return math.degrees(math.atan2(dy, dx))


# ── Strip split (for convex / near-convex plots) ─────────────────────────────


def _strip_split(
    core: Polygon,
    n_zones: int,
    split_line_angle_deg: float,
) -> List[Polygon]:
    """
    Divide *core* into *n_zones* strips using parallel cut lines.

    Cut lines run at *split_line_angle_deg* degrees.  The strips are
    ordered by their centroid's projection onto the normal of that direction.

    This is extracted from packer._split_envelope_n with identical logic.
    """
    if n_zones <= 1:
        return [core]

    from shapely.ops import split as shapely_split

    cx, cy = core.centroid.x, core.centroid.y
    angle_rad = math.radians(split_line_angle_deg)

    # Cut line direction
    ldx, ldy = math.cos(angle_rad), math.sin(angle_rad)
    # Normal direction (perpendicular to cut line)
    ndx, ndy = -ldy, ldx

    # Project vertices onto normal to find span
    coords = list(core.exterior.coords)
    projs = [(x - cx) * ndx + (y - cy) * ndy for x, y in coords]
    p_min, p_max = min(projs), max(projs)

    R = max(
        core.bounds[2] - core.bounds[0],
        core.bounds[3] - core.bounds[1],
    ) * 3.0

    # Evenly spaced cut positions
    cut_projs = [p_min + (p_max - p_min) * (i + 1) / n_zones for i in range(n_zones - 1)]

    pieces: List[Polygon] = [core]
    for proj in cut_projs:
        px = cx + ndx * proj
        py = cy + ndy * proj
        cut_line = LineString([
            (px - ldx * R, py - ldy * R),
            (px + ldx * R, py + ldy * R),
        ])
        new_pieces: List[Polygon] = []
        for piece in pieces:
            try:
                result = shapely_split(piece, cut_line)
                sub = [
                    g for g in result.geoms
                    if isinstance(g, Polygon) and g.area >= MIN_FOOTPRINT_AREA_SQFT
                ]
                new_pieces.extend(sub)
            except Exception:
                new_pieces.append(piece)
        pieces = new_pieces

    if not pieces:
        return [core]

    # Sort by centroid projection along normal
    pieces.sort(key=lambda g: (g.centroid.x - cx) * ndx + (g.centroid.y - cy) * ndy)
    return pieces[:n_zones]


# ── Voronoi split (for irregular plots) ──────────────────────────────────────


def _voronoi_split(
    core: Polygon,
    n_zones: int,
    road_edge_specs: List[EdgeSpec],
) -> List[Polygon]:
    """
    Seed-based Voronoi decomposition for irregular plot shapes.

    Seeds are placed at equal intervals along the longest frontage edge
    (road edge), then Voronoi cells are clipped to the core polygon.
    If the plot has no road edge, seeds are placed along the longest
    exterior edge of the core.
    """
    # Find the edge to place seeds along
    road_specs = [s for s in road_edge_specs if s.edge_type == ROAD]
    if road_specs:
        primary = max(road_specs, key=lambda s: s.length)
        seed_line = LineString([primary.p1, primary.p2])
    else:
        # Fallback: longest exterior edge of core
        coords = list(core.exterior.coords)
        longest_edge = None
        longest_len = 0.0
        for i in range(len(coords) - 1):
            seg = LineString([coords[i], coords[i + 1]])
            if seg.length > longest_len:
                longest_len = seg.length
                longest_edge = seg
        seed_line = longest_edge or LineString([coords[0], coords[1]])

    # Place seeds at equal intervals along the line, offset inward
    seeds = []
    for i in range(n_zones):
        frac = (i + 0.5) / n_zones
        pt = seed_line.interpolate(frac, normalized=True)

        # Offset seed inward from the edge toward the core centroid
        core_cx, core_cy = core.centroid.x, core.centroid.y
        dx = core_cx - pt.x
        dy = core_cy - pt.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            # Move 20% of the distance toward centroid
            offset_frac = 0.2
            pt_x = pt.x + dx * offset_frac
            pt_y = pt.y + dy * offset_frac
        else:
            pt_x, pt_y = pt.x, pt.y
        seeds.append((pt_x, pt_y))

    if len(seeds) < 2:
        return [core]

    # Compute Voronoi diagram
    try:
        multi_pt = MultiPoint(seeds)
        voronoi = voronoi_diagram(multi_pt, envelope=core)

        zones: List[Polygon] = []
        for cell in voronoi.geoms:
            clipped = cell.intersection(core)
            if clipped.is_empty:
                continue
            if isinstance(clipped, MultiPolygon):
                # Take largest component of clipped cell
                largest = max(clipped.geoms, key=lambda g: g.area)
                if largest.area >= MIN_FOOTPRINT_AREA_SQFT:
                    zones.append(largest)
            elif isinstance(clipped, Polygon) and clipped.area >= MIN_FOOTPRINT_AREA_SQFT:
                zones.append(clipped)

        if len(zones) >= n_zones:
            # Sort by proximity to road (road-adjacent zones first)
            if road_specs:
                road_line = LineString([road_specs[0].p1, road_specs[0].p2])
                zones.sort(key=lambda z: z.centroid.distance(road_line))
            return zones[:n_zones]

        # If Voronoi produced fewer zones than needed, return what we have
        if zones:
            return zones

    except Exception as exc:
        logger.warning("Voronoi decomposition failed: %s — falling back to strip.", exc)

    # Fallback to strip split
    road_angle = _road_edge_angle_deg(road_edge_specs)
    return _strip_split(core, n_zones, road_angle)


# ── Zone viability and merging ────────────────────────────────────────────────


def _merge_narrow_zones(
    zones: List[Polygon],
    min_width_dxf: float,
) -> List[Polygon]:
    """
    Merge zones that are too narrow to contain a tower footprint.

    A zone is "too narrow" if `zone.buffer(-min_width_dxf / 2)` collapses.
    Narrow zones are merged with the adjacent zone sharing the longest boundary.
    """
    if len(zones) <= 1:
        return zones

    viable = []
    narrow = []

    for zone in zones:
        shrunk = zone.buffer(-min_width_dxf / 2.0)
        if shrunk.is_empty or (isinstance(shrunk, MultiPolygon) and all(g.is_empty for g in shrunk.geoms)):
            narrow.append(zone)
        else:
            viable.append(zone)

    if not narrow:
        return zones

    # Merge each narrow zone with the viable zone sharing longest boundary
    for nz in narrow:
        best_idx = 0
        best_shared = 0.0
        for i, vz in enumerate(viable):
            try:
                shared = nz.intersection(vz.buffer(1.0)).length
            except Exception:
                shared = 0.0
            if shared > best_shared:
                best_shared = shared
                best_idx = i

        if viable:
            viable[best_idx] = viable[best_idx].union(nz)
        else:
            viable.append(nz)

    return viable


# ── Main entry point ─────────────────────────────────────────────────────────


def decompose_into_zones(
    buildable_core: Polygon,
    n_towers: int,
    cop: Optional[Polygon],
    road_edge_specs: List[EdgeSpec],
    min_width_dxf: float,
    spacing_gap_dxf: float = 0.0,
    cop_centroid: Optional[tuple] = None,  # NEW: (x, y) for COP-aware zone scoring
) -> ZoneResult:
    """
    Partition buildable_core minus COP into tower placement zones.

    Parameters
    ----------
    buildable_core   : Polygon after fire loop carve (DXF feet).
    n_towers         : Number of towers to place.
    cop              : COP polygon to exclude (DXF feet), or None.
    road_edge_specs  : Classified edge specs from envelope computation.
    min_width_dxf    : Minimum tower footprint width (DXF feet).

    Returns
    -------
    ZoneResult with a list of TowerZone objects.
    """
    # Subtract COP from buildable core
    core = buildable_core
    if cop is not None and not cop.is_empty:
        core = buildable_core.difference(cop)
        if isinstance(core, MultiPolygon):
            # Keep all components that can hold a tower
            components = [
                g for g in core.geoms
                if isinstance(g, Polygon) and g.area >= MIN_FOOTPRINT_AREA_SQFT
            ]
            if not components:
                logger.warning("COP subtraction left no viable core — using full core.")
                core = buildable_core
            elif len(components) == 1:
                core = components[0]
            # If multiple components, they'll be handled by the split strategies

    if core.is_empty:
        return ZoneResult(zones=[], strategy="SINGLE", buildable_core=buildable_core)

    # Single tower → one zone
    if n_towers <= 1:
        zone = TowerZone(
            polygon=core,
            index=0,
            area_sqft=core.area,
            is_road_adjacent=_is_zone_road_adjacent(core, road_edge_specs),
        )
        return ZoneResult(zones=[zone], strategy="SINGLE", buildable_core=buildable_core)

    # Choose strategy based on core shape
    convexity = _convexity_ratio(core)
    strategy: str

    if convexity > 0.85:
        # Near-convex → strip split perpendicular to road
        strategy = "STRIP"
        road_angle = _road_edge_angle_deg(road_edge_specs)
        raw_zones = _strip_split(core, n_towers, road_angle)
    else:
        # Irregular → Voronoi decomposition
        strategy = "VORONOI"
        raw_zones = _voronoi_split(core, n_towers, road_edge_specs)

    # Shrink each zone inward by half the spacing gap so towers in adjacent
    # zones naturally maintain the required inter-tower distance.
    if spacing_gap_dxf > 0 and len(raw_zones) > 1:
        half_gap = spacing_gap_dxf / 2.0
        shrunk_zones: List[Polygon] = []
        for zone in raw_zones:
            shrunk = zone.buffer(-half_gap)
            if isinstance(shrunk, MultiPolygon):
                shrunk = max(shrunk.geoms, key=lambda g: g.area) if shrunk.geoms else None
            if shrunk is not None and not shrunk.is_empty and shrunk.area >= MIN_FOOTPRINT_AREA_SQFT:
                shrunk_zones.append(shrunk)
        if shrunk_zones:
            raw_zones = shrunk_zones

    # Handle MultiPolygon core (COP split core into disjoint pieces)
    if isinstance(core, MultiPolygon) and len(raw_zones) < n_towers:
        components = sorted(
            [g for g in core.geoms if isinstance(g, Polygon) and g.area >= MIN_FOOTPRINT_AREA_SQFT],
            key=lambda g: g.area,
            reverse=True,
        )
        if len(components) >= n_towers:
            raw_zones = components[:n_towers]
            strategy = "STRIP"  # component-based is effectively strip

    # Merge narrow zones
    raw_zones = _merge_narrow_zones(raw_zones, min_width_dxf)

    # Build TowerZone objects
    zones = []
    for i, poly in enumerate(raw_zones):
        zones.append(TowerZone(
            polygon=poly,
            index=i,
            area_sqft=poly.area,
            is_road_adjacent=_is_zone_road_adjacent(poly, road_edge_specs),
        ))

    # ── COP-aware zone scoring (NEW) ──────────────────────────────────────────
    if cop_centroid is not None and cop is not None:
        cop_cx, cop_cy = cop_centroid
        for zone in zones:
            zx, zy = zone.polygon.centroid.x, zone.polygon.centroid.y
            zone.cop_distance_dxf = math.sqrt((zx - cop_cx)**2 + (zy - cop_cy)**2)
            
            # Check if zone shares boundary with COP
            try:
                zone.cop_facing = (
                    zone.polygon.touches(cop) or 
                    zone.polygon.intersects(cop.boundary) or
                    zone.polygon.distance(cop) < 5.0  # within 5 DXF feet
                )
            except Exception:
                zone.cop_facing = False

        # Sort zones: COP-adjacent first, then by proximity to COP
        zones.sort(key=lambda z: (not z.cop_facing, z.cop_distance_dxf))
        
        logger.info(
            "COP-aware zone sorting: %d zones, %d COP-facing",
            len(zones), sum(1 for z in zones if z.cop_facing),
        )

    logger.info(
        "Zone decomposition: strategy=%s, n_zones=%d (requested=%d), "
        "convexity=%.2f, core_area=%.0f sqft",
        strategy, len(zones), n_towers, convexity, core.area,
    )

    return ZoneResult(zones=zones, strategy=strategy, buildable_core=buildable_core)
