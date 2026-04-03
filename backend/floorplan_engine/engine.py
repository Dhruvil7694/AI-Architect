"""
floorplan_engine/engine.py
--------------------------
Main orchestrator for the procedural circulation core generator.

Orchestration order (R2-10):
  1. Parse footprint
  2. Detect axes (R2-8 MRR fallback, R1-10 orientation override)
  3. Convert to local metres
  4. Select core type
  5. Calculate + distribute lifts
  6. Assemble core block(s) (R2-7 safe width)
  7. Find core position(s) (R2-1 constrained inscribed rect)
  8. Position stairs (R2-10: before corridor)
  9. Generate corridor (R2-2 MultiPolygon guard, R2-3 arm count)
 10. Build circulation graph (R2-5 path distances, R2-9 CORRIDOR_END)
 11. Validate compliance (R2-4 sampling, R2-6 graph dead-end)
 12. Compute capacity (optional)
 13. Back-project to DXF (R1-8 dual coords)
 14. Build GeoJSON FeatureCollection
 15. Return CoreLayoutResult
"""

from __future__ import annotations

import logging
from typing import Any

from shapely.geometry import LineString, mapping

from floorplan_engine.config import (
    DOUBLE_CORE,
    POINT_CORE,
    CapacityMetrics,
    CoreConfig,
    compute_capacity,
)
from floorplan_engine.core.core_layout import assemble_core_block
from floorplan_engine.core.core_placer import find_core_positions
from floorplan_engine.core.core_selector import select_core_type
from floorplan_engine.core.lift_calculator import calculate_lifts, distribute_lifts
from floorplan_engine.core.stair_positioner import position_stairs
from floorplan_engine.corridor.corridor_generator import generate_corridor
from floorplan_engine.geometry.axis_detection import detect_principal_axes
from floorplan_engine.geometry.polygon_utils import (
    dxf_to_local,
    footprint_area_sqm,
    geojson_to_polygon,
    make_dual,
    make_feature,
    make_feature_collection,
    polygon_to_geojson,
)
from floorplan_engine.graph.circulation_graph import build_circulation_graph
from floorplan_engine.models import (
    CoreBlock,
    CoreLayoutResult,
    CorridorResult,
    DualGeom,
    LiftResult,
    StairResult,
)
from floorplan_engine.validation.compliance_engine import validate_circulation

logger = logging.getLogger(__name__)


def generate_floor_core_layout(tower_data: dict) -> dict:
    """
    Generate a floor circulation layout for a single residential tower.

    Parameters
    ----------
    tower_data : dict
        Required keys:
            footprint       — GeoJSON Polygon (DXF feet coordinates)
            n_floors        — int
            building_height_m — float
        Optional keys:
            tower_type      — "LOW_RISE" | "MID_RISE" | "HIGH_RISE"
            target_units_per_floor — int (default 6)
            orientation_deg — float (overrides axis detection)
            config_overrides — dict (CoreConfig field overrides)

    Returns
    -------
    dict  — contains core_type, lifts, stairs, lobby, corridor,
            corridor_centerline, layout (GeoJSON), graph, metrics,
            capacity, compliance
    """
    # ── Parse inputs ─────────────────────────────────────────────────────
    footprint_geojson = tower_data["footprint"]
    n_floors = int(tower_data["n_floors"])
    building_height_m = float(tower_data["building_height_m"])
    target_units = int(tower_data.get("target_units_per_floor", 6))
    orientation_deg = tower_data.get("orientation_deg")
    config_overrides = tower_data.get("config_overrides", {})

    config = CoreConfig(**config_overrides) if config_overrides else CoreConfig()

    # Step 1: Parse footprint
    footprint_dxf = geojson_to_polygon(footprint_geojson)

    # Step 2: Detect axes (R2-8, R1-10)
    frame = detect_principal_axes(footprint_dxf, orientation_deg)
    length_m = frame.length_m
    width_m = frame.width_m

    # Step 3: Convert to local metres
    footprint_m = dxf_to_local(footprint_dxf, frame)

    # Step 4: Select core type
    area_sqm = footprint_area_sqm(footprint_dxf)
    core_type = select_core_type(area_sqm, config)
    logger.info("Core type: %s (area=%.1f sqm)", core_type, area_sqm)

    # Step 5: Calculate + distribute lifts
    lift_result, lift_local_polys = calculate_lifts(n_floors, config)
    n_cores = 2 if core_type == DOUBLE_CORE else 1
    lift_dist = distribute_lifts(lift_result.n_lifts, n_cores)

    # Step 6: Assemble core block(s) (R2-7)
    include_stairs = (core_type == POINT_CORE)
    raw_blocks = []
    for bi in range(n_cores):
        core_poly, lift_polys, lobby_poly, stair_polys, cw, cd = (
            assemble_core_block(lift_dist[bi], include_stairs, config)
        )
        raw_blocks.append((core_poly, lift_polys, lobby_poly, stair_polys, cw, cd))

    core_width_m = raw_blocks[0][4]
    core_depth_m = raw_blocks[0][5]

    # Step 7: Find core positions (R2-1)
    core_positions = find_core_positions(
        footprint_m, core_type, core_width_m, core_depth_m, length_m, width_m,
    )

    # Step 8: Position stairs (R2-10: before corridor)
    stair_polys_m, stair_centroids, stair_sep, stair_sep_ok = position_stairs(
        core_type, core_positions, core_depth_m,
        length_m, width_m, config,
    )

    # Step 9: Generate corridor (R2-2, R2-3)
    corridor_poly_m, centerline, corridor_length = generate_corridor(
        core_type, core_positions, core_width_m,
        stair_centroids, footprint_m,
        length_m, width_m, target_units, config,
    )

    # ── Build DualGeom wrappers ──────────────────────────────────────────

    # Core blocks
    core_blocks: list[CoreBlock] = []
    for bi, (core_poly, lift_polys, lobby_poly, cp_stairs, cw, cd) in enumerate(raw_blocks):
        cl, cs = core_positions[bi]
        # Translate core block to its position
        dx = cl - cw / 2
        ds = cs - cd / 2
        from shapely.affinity import translate

        t_core = translate(core_poly, xoff=dx, yoff=ds)
        t_lobby = translate(lobby_poly, xoff=dx, yoff=ds)
        t_lifts = [translate(lp, xoff=dx, yoff=ds) for lp in lift_polys]
        t_stairs_in_block = [translate(sp, xoff=dx, yoff=ds) for sp in cp_stairs]

        block = CoreBlock(
            block_geom=make_dual(t_core, frame),
            lift_geoms=[make_dual(lp, frame) for lp in t_lifts],
            lobby_geom=make_dual(t_lobby, frame),
            core_width_m=cw,
            core_depth_m=cd,
            stair_geoms=[make_dual(sp, frame) for sp in t_stairs_in_block],
        )
        core_blocks.append(block)

    # Stairs
    stair_duals = [make_dual(sp, frame) for sp in stair_polys_m]
    # For POINT_CORE, stairs are in the core block — use those instead
    if core_type == POINT_CORE and core_blocks and core_blocks[0].stair_geoms:
        stair_duals = core_blocks[0].stair_geoms
        if len(stair_centroids) < 2 and len(stair_duals) >= 2:
            # Recompute centroids from actual positioned stairs
            stair_centroids = [
                (sg.local_m.centroid.x, sg.local_m.centroid.y)
                for sg in stair_duals
            ]

    stairs_result = StairResult(
        n_stairs=len(stair_duals),
        stair_geoms=stair_duals,
        stair_centroids_m=stair_centroids,
        separation_m=stair_sep,
        separation_ok=stair_sep_ok,
    )

    # Corridor
    corridor_result = CorridorResult(
        corridor_geom=make_dual(corridor_poly_m, frame) if corridor_poly_m else None,
        centerline=centerline,
        corridor_length_m=corridor_length,
        corridor_width_m=config.corridor_width if corridor_poly_m else 0.0,
    )

    # Step 10: Build circulation graph (R2-5, R2-9)
    graph = build_circulation_graph(core_blocks, stairs_result, corridor_result)

    # Step 11: Validate compliance (R2-4, R2-6)
    compliance = validate_circulation(
        core_type, stairs_result, corridor_result, graph,
        length_m, width_m, config,
    )

    # Step 12: Capacity (optional)
    capacity = compute_capacity(
        lift_result.n_lifts, config.stair_width, stairs_result.n_stairs,
        corridor_length, n_floors, target_units, config.occupancy_per_unit,
    )

    # Step 13 + 14: Build GeoJSON FeatureCollection
    features = _build_features(core_blocks, stairs_result, corridor_result)
    geojson = make_feature_collection(features)

    # ── Metrics ──────────────────────────────────────────────────────────
    core_area = sum(b.block_geom.local_m.area for b in core_blocks)
    corridor_area = corridor_poly_m.area if corridor_poly_m else 0.0
    metrics = {
        "core_type": core_type,
        "n_lifts": lift_result.n_lifts,
        "n_stairs": stairs_result.n_stairs,
        "core_area_sqm": round(core_area, 2),
        "corridor_area_sqm": round(corridor_area, 2),
        "circulation_pct": round(
            (core_area + corridor_area) / max(footprint_m.area, 1) * 100, 1
        ),
        "footprint_area_sqm": round(area_sqm, 2),
        "max_travel_distance_m": compliance["travel_distance_max_m"],
        "stair_separation_m": compliance["stair_separation_m"],
    }

    # Step 15: Return
    result = CoreLayoutResult(
        core_type=core_type,
        frame=frame,
        core_blocks=core_blocks,
        stairs=stairs_result,
        corridor=corridor_result,
        graph=graph,
        metrics=metrics,
        compliance=compliance,
        capacity=capacity,
        geojson=geojson,
    )

    return _serialize(result, centerline)


# ── GeoJSON feature builder ─────────────────────────────────────────────────

def _build_features(
    core_blocks: list[CoreBlock],
    stairs: StairResult,
    corridor: CorridorResult,
) -> list[dict]:
    """Build the GeoJSON features list from DXF-space geometry."""
    features = []

    for bi, block in enumerate(core_blocks):
        # Core bounding box
        features.append(make_feature(
            block.block_geom.dxf, "core", id=f"core_{bi}",
        ))
        # Lobby
        features.append(make_feature(
            block.lobby_geom.dxf, "lobby", id=f"lobby_{bi}",
        ))
        # Lifts in core
        for li, lg in enumerate(block.lift_geoms):
            features.append(make_feature(
                lg.dxf, "lift", id=f"lift_{bi}_{li}",
            ))
        # Stairs in core (POINT_CORE only)
        for si, sg in enumerate(block.stair_geoms):
            features.append(make_feature(
                sg.dxf, "stair", id=f"stair_core_{bi}_{si}",
            ))

    # Standalone stairs (not in core block)
    for si, sg in enumerate(stairs.stair_geoms):
        # Skip if already emitted as part of core block
        already = any(
            sg.dxf.equals(bs.dxf)
            for block in core_blocks
            for bs in block.stair_geoms
        )
        if not already:
            features.append(make_feature(
                sg.dxf, "stair", id=f"stair_{si}",
            ))

    # Corridor
    if corridor.corridor_geom is not None:
        features.append(make_feature(
            corridor.corridor_geom.dxf, "corridor",
        ))

    return features


# ── Serialisation ────────────────────────────────────────────────────────────

def _serialize(result: CoreLayoutResult, centerline) -> dict:
    """Convert CoreLayoutResult to a plain dict for API response."""
    # Individual geometry items as GeoJSON
    lifts_gj = []
    for block in result.core_blocks:
        for lg in block.lift_geoms:
            lifts_gj.append(polygon_to_geojson(lg.dxf))

    stairs_gj = [polygon_to_geojson(sg.dxf) for sg in result.stairs.stair_geoms]

    lobby_gj = None
    if result.core_blocks:
        lobby_gj = polygon_to_geojson(result.core_blocks[0].lobby_geom.dxf)

    corridor_gj = None
    if result.corridor.corridor_geom:
        corridor_gj = polygon_to_geojson(result.corridor.corridor_geom.dxf)

    centerline_gj = None
    if centerline:
        centerline_gj = mapping(centerline)

    # Graph serialisation
    graph_dict = {
        "nodes": [
            {
                "id": n.node_id,
                "type": n.node_type,
                "centroid": list(n.centroid_m),
                "degree": n.degree,
            }
            for n in result.graph.nodes
        ],
        "edges": [
            {
                "from": e.from_id,
                "to": e.to_id,
                "distance_m": round(e.distance_m, 2),
            }
            for e in result.graph.edges
        ],
    }

    return {
        "status": "ok",
        "core_type": result.core_type,
        "lifts": lifts_gj,
        "stairs": stairs_gj,
        "lobby": lobby_gj,
        "corridor": corridor_gj,
        "corridor_centerline": centerline_gj,
        "layout": result.geojson,
        "graph": graph_dict,
        "metrics": result.metrics,
        "capacity": {
            "people_per_lift": round(result.capacity.people_per_lift, 1),
            "stair_capacity_persons_per_min": round(
                result.capacity.stair_capacity_persons_per_min, 1
            ),
            "corridor_density_persons_per_m": round(
                result.capacity.corridor_density_persons_per_m, 2
            ),
        } if result.capacity else None,
        "compliance": result.compliance,
    }
