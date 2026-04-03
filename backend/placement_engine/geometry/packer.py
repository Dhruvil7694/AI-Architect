"""
placement_engine/geometry/packer.py
------------------------------------
Multi-tower packing with six competing strategies across two families:

ORIENTATION FAMILY — greedy sequential packing, varies inscribed-rect angle:
  ROW_WISE   — full 7-angle sweep per step (follows envelope's principal axis).
  COL_WISE   — forces the PERPENDICULAR orientation for every tower.
  DIAG_WISE  — forces 45° offset from the primary axis.

TOPOLOGY FAMILY — pre-split envelope into per-tower zones, producing
                  genuinely different placement layouts (not angle variants):
  SPLIT_LR       — side-by-side: vertical strips → both towers face the road.
  SPLIT_FB       — front-back:   horizontal strips → near-road + interior towers.
  SPLIT_STAGGER  — diagonal strips (45°) → staggered courtyard layout.
  GRID_2X2       — (n=4 only) 2×2 quadrant split → central courtyard cluster.
  COMPOSITE_2_1  — (n=3 only) 2 front side-by-side + 1 wide rear → U-shape.

All six strategies run to completion independently.  The winner is selected
by the four-rule priority in _select_packing_winner():
  1. More towers placed wins (regulatory compliance first).
  2. Tie: higher layout quality score wins (spatial quality via layout_scorer).
  3. Tie: larger total footprint area wins.
  4. Tie: ROW_WISE wins (deterministic fallback).

After the winning strategy is chosen, spacing_enforcer.audit_spacing() runs
an independent post-placement gap check for every pair of placed towers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from placement_engine.geometry import (
    MAX_TOWERS,
    MIN_FOOTPRINT_AREA_SQFT,
    FootprintCandidate,
)
from placement_engine.geometry.multipolygon_handler import (
    find_best_in_components,
    find_top_n_in_components,
)
from placement_engine.geometry.spacing_enforcer import (
    compute_exclusion_zone,
    audit_spacing,
    any_spacing_fail,
)
from placement_engine.geometry.orientation_finder import find_orientation
from placement_engine.scoring.placement_scorer import select_best_candidate
from placement_engine.scoring.anchor_adjustment import anchor_to_dominant_edge


@dataclass
class PackingResult:
    """Output of pack_towers()."""
    mode:             str                       # "ROW_WISE" | "COL_WISE"
    footprints:       list[FootprintCandidate]  # ordered by placement sequence
    n_placed:         int
    total_area_sqft:  float
    spacing_audit:    list[dict]
    has_spacing_fail: bool
    layout_quality_score: Optional[float] = None  # 0–1 composite from layout_scorer


def pack_towers(
    envelope:              Polygon,
    n_towers:              int,
    building_height_m:     float,
    min_width_dxf:         float,
    min_depth_dxf:         float,
    road_edge_angles_deg:  Optional[List[float]] = None,
    target_plate_area_sqft: Optional[float] = None,
    preferred_depth_m:      Optional[float] = None,
) -> PackingResult:
    """
    Place up to *n_towers* buildings inside *envelope* deterministically.

    Runs ROW_WISE and COL_WISE strategies, compares outcomes, returns the winner.

    Parameters
    ----------
    envelope              : Legal buildable envelope polygon (DXF feet, SRID=0).
    n_towers              : Number of buildings requested (capped at MAX_TOWERS).
    building_height_m     : Building height in metres (drives H/3 spacing).
    min_width_dxf         : Minimum footprint width (DXF feet).
    min_depth_dxf         : Minimum footprint depth (DXF feet).
    road_edge_angles_deg  : Direction angles of road-facing edges (degrees).
                            Forwarded to the placement scorer for road-alignment
                            heuristics.  None/[] = scorer uses neutral 0.5.

    Returns
    -------
    PackingResult — the winning strategy's outcome with spacing audit.
    """
    n_towers = min(n_towers, MAX_TOWERS)

    # Determine the primary/secondary orientations from the envelope once
    orient = find_orientation(envelope)

    row_result = _run_packing(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        force_angle=None,                          # full sweep per step (ROW_WISE)
        mode="ROW_WISE",
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
    )

    col_result = _run_packing(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        force_angle=orient.angle_secondary_deg,    # force perpendicular
        mode="COL_WISE",
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
    )

    # DIAG_WISE — forces 45° offset from primary, catching plots whose
    # best inscribed rectangle lies along a diagonal axis.
    diag_result = _run_packing(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        force_angle=orient.angle_primary_deg + 45.0,
        mode="DIAG_WISE",
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
    )

    # ── Spatial topology strategies — pre-split envelope into per-tower zones ──
    # These produce genuinely different placement topologies (not just angle variants)
    # by constraining each tower to a distinct sub-region of the envelope.

    # SPLIT_LR: side-by-side strips (towers share road frontage)
    #   Cut lines are parallel to the secondary axis (vertical for landscape envelopes)
    #   → left / right zones.  Both towers face the road simultaneously.
    #   Angle: orient.angle_secondary_deg produces vertical cuts for landscape (primary=0°).
    lr_zones = _split_envelope_n(
        envelope, n_towers,
        split_line_angle_deg=orient.angle_secondary_deg,
    )
    lr_result = _run_packing_partitioned(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        zones=lr_zones,
        mode="SPLIT_LR",
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
    )

    # SPLIT_FB: front-back depth layout (near-road + interior towers)
    #   Cut lines are parallel to the primary axis (horizontal for landscape envelopes)
    #   → front / back zones.
    fb_zones = _split_envelope_n(
        envelope, n_towers,
        split_line_angle_deg=orient.angle_primary_deg,
    )
    fb_result = _run_packing_partitioned(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        zones=fb_zones,
        mode="SPLIT_FB",
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
    )

    # SPLIT_STAGGER: diagonal strips (45° from primary)
    #   Upper-left / lower-right zone split → staggered courtyard layout.
    stag_zones = _split_envelope_n(
        envelope, n_towers,
        split_line_angle_deg=(orient.angle_primary_deg + 45.0) % 180.0,
    )
    stag_result = _run_packing_partitioned(
        envelope=envelope,
        n_towers=n_towers,
        building_height_m=building_height_m,
        min_width_dxf=min_width_dxf,
        min_depth_dxf=min_depth_dxf,
        zones=stag_zones,
        mode="SPLIT_STAGGER",
        road_edge_angles_deg=road_edge_angles_deg,
        target_plate_area_sqft=target_plate_area_sqft,
    )

    # ── n-specific 2-D topology strategies ────────────────────────────────────
    extra_results: list[PackingResult] = []

    if n_towers == 4:
        # GRID_2X2 — 2×2 quadrant layout → central courtyard
        #   Split into 4 equal quadrants (2 cols × 2 rows).
        #   One tower per quadrant → T1 T2 / T3 T4 with open centre.
        grid_zones = _split_envelope_grid(envelope, orient, rows=2, cols=2)
        if len(grid_zones) >= 4:
            grid_result = _run_packing_partitioned(
                envelope=envelope,
                n_towers=n_towers,
                building_height_m=building_height_m,
                min_width_dxf=min_width_dxf,
                min_depth_dxf=min_depth_dxf,
                zones=grid_zones,
                mode="GRID_2X2",
                road_edge_angles_deg=road_edge_angles_deg,
                target_plate_area_sqft=target_plate_area_sqft,
            )
            extra_results.append(grid_result)

    elif n_towers == 3:
        # COMPOSITE_2_1 — two front + one rear (U-shape / partial courtyard)
        #   Step 1: halve envelope front-to-back (primary-axis cut).
        #   Step 2: split front band into 2 side-by-side zones.
        #   Step 3: rear band stays whole → wider single tower zone.
        bands = _split_envelope_n(
            envelope, 2, split_line_angle_deg=orient.angle_primary_deg,
        )
        if len(bands) >= 2:
            # bands[0] projects lowest along primary normal → front band
            front_zones = _split_envelope_n(
                bands[0], 2, split_line_angle_deg=orient.angle_secondary_deg,
            )
            rear_zone = bands[1]
            comp_zones = list(front_zones[:2]) + [rear_zone]
            if len(comp_zones) == 3:
                comp_result = _run_packing_partitioned(
                    envelope=envelope,
                    n_towers=n_towers,
                    building_height_m=building_height_m,
                    min_width_dxf=min_width_dxf,
                    min_depth_dxf=min_depth_dxf,
                    zones=comp_zones,
                    mode="COMPOSITE_2_1",
                    road_edge_angles_deg=road_edge_angles_deg,
                    target_plate_area_sqft=target_plate_area_sqft,
                )
                extra_results.append(comp_result)

    winner = _select_packing_winner(
        row_result, col_result, diag_result,
        lr_result, fb_result, stag_result,
        *extra_results,
        envelope=envelope,
        road_edge_angles_deg=road_edge_angles_deg,
    )

    # Post-placement gap audit on the winner's placed footprints
    placed_polygons = [c.footprint_polygon for c in winner.footprints]
    audit = audit_spacing(placed_polygons, building_height_m)
    fail  = any_spacing_fail(audit)

    return PackingResult(
        mode=winner.mode,
        footprints=winner.footprints,
        n_placed=winner.n_placed,
        total_area_sqft=winner.total_area_sqft,
        spacing_audit=audit,
        has_spacing_fail=fail,
        layout_quality_score=winner.layout_quality_score,
    )


# ── Internal packing loop ──────────────────────────────────────────────────────

def _run_packing(
    envelope:              Polygon,
    n_towers:              int,
    building_height_m:     float,
    min_width_dxf:         float,
    min_depth_dxf:         float,
    force_angle:           Optional[float],
    mode:                  str,
    road_edge_angles_deg:  Optional[List[float]] = None,
    target_plate_area_sqft: Optional[float] = None,
    preferred_depth_m:      Optional[float] = None,
) -> PackingResult:
    """Run one complete packing strategy and return its result.

    For each placement step:
      1. Generate top-N candidate rectangles from the remaining buildable space.
      2. Apply the architectural scoring layer (placement_scorer.select_best_candidate)
         to pick the highest-scoring candidate using edge contact, road alignment,
         and open-space compactness heuristics.
      3. Subtract the H/3 exclusion zone and continue to the next tower.

    This replaces the previous single-candidate (largest-area) selection while
    leaving the inscribed-rectangle solver and spacing logic completely unchanged.
    """
    remaining: BaseGeometry = envelope
    footprints: list[FootprintCandidate] = []

    for _i in range(n_towers):
        if remaining is None or remaining.is_empty:
            break
        if remaining.area < MIN_FOOTPRINT_AREA_SQFT:
            break

        # Generate multiple candidates and score them
        candidates = find_top_n_in_components(
            geom=remaining,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            force_angle=force_angle,
            min_area_sqft=MIN_FOOTPRINT_AREA_SQFT,
            n=10,
        )

        candidate = select_best_candidate(
            candidates=candidates,
            available_polygon=remaining,
            road_edge_angles_deg=road_edge_angles_deg,
            target_plate_area_sqft=target_plate_area_sqft,
            preferred_depth_m=preferred_depth_m,
        )

        if candidate is None:
            break

        # Step 5 — anchor adjustment: slide toward dominant envelope edge
        # if the selected footprint is not already touching the boundary.
        candidate = anchor_to_dominant_edge(candidate, envelope)

        footprints.append(candidate)

        # Subtract FULL H/3 exclusion zone so the next tower respects spacing
        exclusion = compute_exclusion_zone(candidate.footprint_polygon, building_height_m)
        remaining = remaining.difference(exclusion)

    total_area = sum(c.area_sqft for c in footprints)

    return PackingResult(
        mode=mode,
        footprints=footprints,
        n_placed=len(footprints),
        total_area_sqft=total_area,
        spacing_audit=[],       # filled in by pack_towers after winner selected
        has_spacing_fail=False,
    )


def _split_envelope_n(
    envelope: Polygon,
    n: int,
    split_line_angle_deg: float,
) -> List[Polygon]:
    """
    Divide *envelope* into *n* strips using (n-1) parallel cut lines.

    Each cut line runs at *split_line_angle_deg* degrees.  The strips are
    ordered by their centroid's projection onto the normal of that direction
    (smallest → largest projection).

    For a landscape envelope (primary axis horizontal, 0°):
      - split_line_angle_deg=0°  → horizontal cuts → front/back strips (SPLIT_FB)
      - split_line_angle_deg=90° → vertical cuts → left/right strips (SPLIT_LR)

    Returns at most *n* valid zones (Polygons with area ≥ MIN_FOOTPRINT_AREA_SQFT).
    Falls back to [envelope] if splitting fails.
    """
    if n <= 1:
        return [envelope]

    from shapely.ops import split as shapely_split

    cx, cy = envelope.centroid.x, envelope.centroid.y
    angle_rad = math.radians(split_line_angle_deg)

    # Cut line direction
    ldx, ldy = math.cos(angle_rad), math.sin(angle_rad)
    # Normal direction (perpendicular to cut line = strip separation direction)
    ndx, ndy = -ldy, ldx

    # Project envelope vertices onto normal to find the span
    coords = list(envelope.exterior.coords)
    projs = [(x - cx) * ndx + (y - cy) * ndy for x, y in coords]
    p_min, p_max = min(projs), max(projs)

    # Long enough to span the full envelope
    R = max(
        envelope.bounds[2] - envelope.bounds[0],
        envelope.bounds[3] - envelope.bounds[1],
    ) * 3.0

    # Evenly spaced cut positions along the normal direction
    cut_projs = [p_min + (p_max - p_min) * (i + 1) / n for i in range(n - 1)]

    pieces: List[Polygon] = [envelope]
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
        return [envelope]

    # Sort by centroid projection along normal (consistent left→right or front→back order)
    pieces.sort(key=lambda g: (g.centroid.x - cx) * ndx + (g.centroid.y - cy) * ndy)
    return pieces[:n]


def _split_envelope_grid(
    envelope: Polygon,
    orient,                  # OrientationResult from find_orientation()
    rows: int,
    cols: int,
) -> List[Polygon]:
    """
    Divide *envelope* into a rows × cols 2-D grid of zones.

    Algorithm
    ---------
    1. Split into *cols* vertical strips along the secondary axis
       (cut lines run at orient.angle_secondary_deg).
    2. Split each vertical strip into *rows* horizontal zones
       along the primary axis
       (cut lines run at orient.angle_primary_deg).
    3. Flatten and sort zones top-left → top-right → bottom-left → bottom-right
       using (row_index, col_index) derived from centroid projections, so the
       order is fully deterministic for any envelope shape.

    For a landscape envelope (primary=0°, secondary=90°):
      cols=2, rows=2 → four quadrant zones in reading order:
        [ top-left, top-right, bottom-left, bottom-right ]

    Falls back to [envelope] if splitting produces fewer than rows×cols zones.
    """
    col_strips = _split_envelope_n(
        envelope, cols, split_line_angle_deg=orient.angle_secondary_deg,
    )
    if not col_strips:
        return [envelope]

    all_zones: List[Polygon] = []
    for strip in col_strips:
        row_zones = _split_envelope_n(
            strip, rows, split_line_angle_deg=orient.angle_primary_deg,
        )
        all_zones.extend(row_zones)

    if not all_zones:
        return [envelope]

    # Deterministic sort: project centroids onto primary (row) and secondary
    # (col) axes, then sort by (row_bucket, col_bucket) in reading order.
    cx_env = envelope.centroid.x
    cy_env = envelope.centroid.y
    ang_p = math.radians(orient.angle_primary_deg)
    ang_s = math.radians(orient.angle_secondary_deg)
    # Primary axis direction → used for row ordering
    p_dx, p_dy = math.cos(ang_p), math.sin(ang_p)
    # Secondary axis direction → used for column ordering
    s_dx, s_dy = math.cos(ang_s), math.sin(ang_s)

    def _zone_key(z: Polygon):
        gc = z.centroid
        row_proj = (gc.x - cx_env) * p_dy - (gc.y - cy_env) * p_dx   # perp to primary
        col_proj = (gc.x - cx_env) * s_dy - (gc.y - cy_env) * s_dx   # perp to secondary
        return (round(row_proj, 1), round(col_proj, 1))

    all_zones.sort(key=_zone_key)
    return all_zones[: rows * cols]


def _run_packing_partitioned(
    envelope: Polygon,
    n_towers: int,
    building_height_m: float,
    min_width_dxf: float,
    min_depth_dxf: float,
    zones: List[Polygon],
    mode: str,
    road_edge_angles_deg: Optional[List[float]] = None,
    target_plate_area_sqft: Optional[float] = None,
) -> PackingResult:
    """
    Place one tower per zone, each zone restricting where that tower may go.

    Enforces spacing between towers: before placing in zone i, all exclusion
    zones from previously placed towers are subtracted from zone i's available
    area.  This guarantees the same H/3 spacing as the greedy strategies.

    anchor_to_dominant_edge is intentionally NOT called here — the zone itself
    determines topology.  The placement_scorer's edge_contact_score already
    rewards boundary proximity within the zone.

    Falls back gracefully: if a zone yields no valid candidate, that tower is
    simply skipped (n_placed < n_towers → status = TOO_TIGHT in the caller).
    """
    footprints: list[FootprintCandidate] = []

    for zone in zones[:n_towers]:
        # Subtract exclusion zones from all previously placed towers
        available: BaseGeometry = zone
        for placed in footprints:
            excl = compute_exclusion_zone(placed.footprint_polygon, building_height_m)
            available = available.difference(excl)
            if available is None or available.is_empty:
                break

        if available is None or available.is_empty or available.area < MIN_FOOTPRINT_AREA_SQFT:
            continue

        candidates = find_top_n_in_components(
            geom=available,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            force_angle=None,  # full 7-angle sweep within the zone
            min_area_sqft=MIN_FOOTPRINT_AREA_SQFT,
            n=10,
        )

        candidate = select_best_candidate(
            candidates=candidates,
            available_polygon=available,
            road_edge_angles_deg=road_edge_angles_deg,
            target_plate_area_sqft=target_plate_area_sqft,
        )

        if candidate is None:
            continue

        footprints.append(candidate)

    total_area = sum(c.area_sqft for c in footprints)
    return PackingResult(
        mode=mode,
        footprints=footprints,
        n_placed=len(footprints),
        total_area_sqft=total_area,
        spacing_audit=[],       # filled by pack_towers after winner selected
        has_spacing_fail=False,
    )


def _select_packing_winner(
    *results: PackingResult,
    envelope: Optional[Polygon] = None,
    road_edge_angles_deg: Optional[List[float]] = None,
) -> PackingResult:
    """
    Select the best packing result using a four-rule priority:
      1. More towers placed wins (regulatory compliance first).
      2. Tie on n_placed: higher layout quality score wins (spatial quality).
      3. Tie on quality: larger total footprint area wins.
      4. Tie on area: ROW_WISE wins (deterministic fallback).
    """
    if not results:
        raise ValueError("No packing results to compare")

    # Rule 1 — most towers placed
    max_placed = max(r.n_placed for r in results)
    top = [r for r in results if r.n_placed == max_placed]

    if len(top) == 1:
        return top[0]

    # Rule 2 — spatial quality score (only when envelope provided and n_placed tied)
    if envelope is not None:
        from placement_engine.scoring.layout_scorer import score_layout
        for r in top:
            try:
                lqs = score_layout(r, envelope, road_edge_angles_deg)
                r.layout_quality_score = lqs.composite
            except Exception:
                r.layout_quality_score = None

        # Rule 3 & 4 — quality → area → ROW_WISE
        return max(top, key=lambda r: (
            round(r.layout_quality_score or 0.0, 2),  # 2 d.p. tolerance
            r.total_area_sqft,
            r.mode == "ROW_WISE",
        ))

    # Fallback without envelope: area → ROW_WISE
    return max(top, key=lambda r: (r.total_area_sqft, r.mode == "ROW_WISE"))
