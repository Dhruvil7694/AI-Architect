from __future__ import annotations

import itertools
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from django.db import transaction, close_old_connections
from django.conf import settings
from shapely.wkt import loads as shapely_loads
from shapely.ops import unary_union
from shapely.geometry import Polygon

from architecture.models import PlanJob
from architecture.regulatory_accessors import get_cop_required_fraction
from services.plot_service import get_plot_by_public_id
from architecture.spatial.road_edge_detector import detect_road_edges_with_meta
from envelope_engine.services.envelope_service import compute_envelope
from placement_engine.services.placement_service import compute_placement
from placement_engine.geometry import FootprintCandidate, MAX_TOWERS
from placement_engine.geometry.footprint_optimizer import (
    optimize_footprint_in_zone,
    generate_footprint_candidates_in_zone,
)
from placement_engine.geometry.spacing_enforcer import (
    required_spacing_m,
    audit_spacing,
    any_spacing_fail,
)
from placement_engine.constraints.road_access import (
    all_towers_have_road_access,
    DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M,
)
from utils.geometry_geojson import wkt_to_geojson, geometry_to_geojson
from architecture.engines.road_network_engine import (
    generate_internal_road_network,
    road_network_corridor_polygons,
)
from architecture.engines.placement_zone_engine import generate_placement_zones
from utils.geometry_validation import validate_geojson_geometry
from common.units import sqft_to_sqm

logger = logging.getLogger(__name__)

STOREY_HEIGHT_M = 3.0


def _cop_required_sqm(plot_area_sqm: float) -> float:
    """COP area required per GDCR: max(fraction × plot_area, minimum_total_area_sqm)."""
    try:
        from rules_engine.rules.loader import get_gdcr_config
        cop_cfg = get_gdcr_config().get("common_open_plot", {}) or {}
        min_sqm = float(cop_cfg.get("minimum_total_area_sqm", 0.0) or 0.0)
    except Exception:
        min_sqm = 0.0
    by_fraction = plot_area_sqm * get_cop_required_fraction()
    return max(by_fraction, min_sqm) if min_sqm > 0 else by_fraction


def _precompute_zone_footprints(
    zones: List[Any],
    building_height_m: float,
) -> List[List[FootprintCandidate]]:
    """
    Generate footprint candidates for each zone at a given building height.

    Extracted so that _search_best_tower_layout can call this ONCE per
    (floor-count, zone) combination and reuse the result across all tower
    counts.  Without caching, the 7×7 grid optimizer runs O(MAX_TOWERS) times
    per zone per floor count — the dominant cost in the configuration search.
    """
    zone_footprints: List[List[FootprintCandidate]] = []
    for zone in zones:
        try:
            candidates = generate_footprint_candidates_in_zone(
                zone, building_height_m, top_n=3
            )
            if candidates:
                zone_footprints.append(candidates)
                continue
            placement = compute_placement(
                envelope_wkt=zone.wkt,
                building_height_m=building_height_m,
                n_towers=1,
            )
            zone_footprints.append(
                list(placement.footprints) if placement.footprints else []
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Zone precompute failed: %s", e)
            zone_footprints.append([])
    return zone_footprints


def _place_towers_by_zone(
    final_envelope: Polygon,
    zone_result: Optional[Any],
    n_towers: int,
    building_height_m: float,
    road_corridor_geom: Optional[Any] = None,
    road_access_max_distance_m: float = DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M,
    precomputed_zone_footprints: Optional[List[List[FootprintCandidate]]] = None,
) -> Tuple[List[FootprintCandidate], int]:
    """
    Zone-driven placement with candidate layouts and scoring.

    - Generates placement zones from the envelope (already sorted by area, largest first).
    - Tries tower placement inside each zone (one tower per zone).
    - Builds candidate layouts = each subset of k zones (k = min(n_towers, len(zones))).
    - Scores each layout by total BUA (footprint area × floors) when spacing passes.
    - Returns the layout that maximizes buildable area (proxy for GC utilization).
    Falls back to single-envelope placement if no zones.
    """
    zones = (zone_result.candidate_zones or []) if zone_result else []
    zones = [z for z in zones if z is not None and not z.is_empty and z.is_valid]

    if not zones:
        placement = compute_placement(
            envelope_wkt=final_envelope.wkt,
            building_height_m=building_height_m,
            n_towers=n_towers,
        )
        return list(placement.footprints) if placement.footprints else [], placement.n_towers_placed

    k = min(n_towers, len(zones))
    if k <= 0:
        return [], 0

    # Floors are assumed uniform across towers for a given building_height_m.
    floors = max(1.0, building_height_m / STOREY_HEIGHT_M) if STOREY_HEIGHT_M > 0 else 1.0

    # Use precomputed zone footprints if the caller cached them; otherwise compute now.
    # Precomputation is done once per floor-height in _search_best_tower_layout so the
    # expensive 7×7 grid optimizer is not repeated for every (floors, n_towers) pair.
    if precomputed_zone_footprints is not None:
        zone_footprints = precomputed_zone_footprints
    else:
        zone_footprints = _precompute_zone_footprints(zones, building_height_m)

    # Single tower: pick the zone that gives the largest BUA
    if k == 1:
        best_fp: Optional[FootprintCandidate] = None
        best_score = 0.0
        for foot_list in zone_footprints:
            if not foot_list:
                continue
            fp = foot_list[0]
            bua_sqft = (getattr(fp, "area_sqft", 0.0) or 0.0) * floors
            if bua_sqft > best_score:
                best_score = bua_sqft
                best_fp = fp
        if best_fp is None:
            return [], 0
        return [best_fp], 1

    # Multiple towers: for each combination of k zones, search over per-zone
    # candidates (largest first) and shrink only when spacing fails.
    best_footprints: List[FootprintCandidate] = []
    best_score = 0.0
    n_zones = len(zone_footprints)
    road_geom = (
        road_corridor_geom
        if road_corridor_geom is not None and not getattr(road_corridor_geom, "is_empty", False)
        else None
    )

    def _best_layout_for_combo(indices: Tuple[int, ...]) -> Tuple[float, List[FootprintCandidate]]:
        """
        Given a tuple of zone indices, search their candidate ladders to find
        the highest-BUA layout that passes spacing (and road access).
        """
        from collections import deque

        per_zone: List[List[FootprintCandidate]] = [zone_footprints[i] for i in indices]
        if any(len(cands) == 0 for cands in per_zone):
            return 0.0, []

        k_local = len(per_zone)
        # Start from the largest footprint in each zone (index 0)
        start_cfg = tuple(0 for _ in range(k_local))
        queue: deque[Tuple[int, ...]] = deque([start_cfg])
        visited: set[Tuple[int, ...]] = {start_cfg}

        local_best_score = 0.0
        local_best_cfg: Optional[Tuple[int, ...]] = None
        max_expansions = 50
        expansions = 0

        while queue and expansions < max_expansions:
            cfg = queue.popleft()
            expansions += 1

            footprints = [per_zone[i][cfg[i]] for i in range(k_local)]
            polygons = [
                fp.footprint_polygon
                for fp in footprints
                if getattr(fp, "footprint_polygon", None) is not None and not fp.footprint_polygon.is_empty
            ]
            if len(polygons) != k_local:
                continue

            audit = audit_spacing(polygons, building_height_m)
            if any_spacing_fail(audit):
                # Spacing fail: try shrinking individual towers (move to the next
                # smaller candidate in that zone).
                for j in range(k_local):
                    next_idx = cfg[j] + 1
                    if next_idx < len(per_zone[j]):
                        next_cfg = list(cfg)
                        next_cfg[j] = next_idx
                        next_cfg_t = tuple(next_cfg)
                        if next_cfg_t not in visited:
                            visited.add(next_cfg_t)
                            queue.append(next_cfg_t)
                continue

            # Road access check (only when road geometry is available).
            if road_geom is not None and not all_towers_have_road_access(
                polygons,
                road_geom,
                max_distance_m=road_access_max_distance_m,
            ):
                # Treat access failure like spacing failure: try shrinking.
                for j in range(k_local):
                    next_idx = cfg[j] + 1
                    if next_idx < len(per_zone[j]):
                        next_cfg = list(cfg)
                        next_cfg[j] = next_idx
                        next_cfg_t = tuple(next_cfg)
                        if next_cfg_t not in visited:
                            visited.add(next_cfg_t)
                            queue.append(next_cfg_t)
                continue

            # Spacing and road access pass — compute BUA score
            score = sum((getattr(fp, "area_sqft", 0.0) or 0.0) * floors for fp in footprints)
            if score > local_best_score:
                local_best_score = score
                local_best_cfg = cfg

        if local_best_cfg is None:
            return 0.0, []

        final_footprints = [per_zone[i][local_best_cfg[i]] for i in range(k_local)]
        return local_best_score, final_footprints

    for indices in itertools.combinations(range(n_zones), k):
        combo_score, combo_footprints = _best_layout_for_combo(indices)
        if combo_score <= 0.0 or not combo_footprints:
            continue
        if combo_score > best_score:
            best_score = combo_score
            best_footprints = combo_footprints

    # If no valid multi-zone layout (e.g. all combinations fail spacing), fall back to whole envelope
    if not best_footprints and n_towers > 1:
        placement = compute_placement(
            envelope_wkt=final_envelope.wkt,
            building_height_m=building_height_m,
            n_towers=n_towers,
        )
        return list(placement.footprints) if placement.footprints else [], placement.n_towers_placed

    return best_footprints, len(best_footprints)


def _candidate_floor_counts(max_floors: int) -> List[int]:
    """
    Return a small, coarse set of candidate floor counts up to max_floors.

    This keeps the configuration search tractable while still exploring the key
    trade-offs between fewer/taller vs more/shorter towers.
    """
    if max_floors <= 0:
        return []
    if max_floors <= 6:
        return list(range(1, max_floors + 1))

    # For taller buildings, sample a few representative points plus the maximum.
    candidates = {max_floors}
    for f in (8, 12, 16, 20):
        if 1 <= f <= max_floors:
            candidates.add(f)
    # Also add mid-point if not already covered.
    mid = max(1, max_floors // 2)
    if mid <= max_floors:
        candidates.add(mid)

    return sorted(candidates)


def _search_best_tower_layout(
    final_envelope: Polygon,
    zone_result: Optional[Any],
    building_height_m: float,
    road_corridor_geom: Optional[Any],
    tower_pref: Any,
    storey_height_m: float,
    max_bua_sqm: float,
    gdcr_max_height_m: float = 0.0,
) -> Tuple[List[FootprintCandidate], int, int, int]:
    """
    Evaluate multiple (floors, n_towers) configurations and return the best layout.

    Height solver provides the maximum legal building height; we derive the
    corresponding max_floors and sample a coarse set of floor counts below that.
    For each (floors, n_towers) pair we:
      - run the zone-based placement solver (spacing + road access)
      - compute BUA
      - optionally discard configurations that exceed the FSI ceiling
      - keep the configuration that maximises BUA.
    """
    # Normalise user preference for tower count.
    explicit_max: Optional[int] = None
    if isinstance(tower_pref, str) and tower_pref != "auto":
        try:
            explicit_max = int(tower_pref)
        except (TypeError, ValueError):
            explicit_max = None
    elif isinstance(tower_pref, (int, float)):
        try:
            explicit_max = int(tower_pref)
        except (TypeError, ValueError):
            explicit_max = None

    if explicit_max is not None:
        candidate_max_towers = max(1, min(explicit_max, MAX_TOWERS))
    else:
        candidate_max_towers = MAX_TOWERS

    if storey_height_m <= 0:
        storey_height_m = STOREY_HEIGHT_M or 3.0

    # Use the GDCR road-width cap as the floor search ceiling when it exceeds
    # the height solver output.  The height solver is constrained by current
    # envelope geometry; the GDCR cap represents the statutory maximum for
    # the road width.
    height_ceiling = gdcr_max_height_m if gdcr_max_height_m > building_height_m else building_height_m
    max_floors = int(height_ceiling / storey_height_m) if storey_height_m > 0 else 0

    # Cap max_floors at the FSI-derived ceiling: configurations with more floors
    # than this will always be rejected by the FSI filter below, so searching them
    # wastes time proportional to n_floors × MAX_TOWERS × n_zones × grid_size.
    # final_envelope.area is in DXF square feet — convert to sqm before comparing
    # with max_bua_sqm (which is already in m²).
    if max_bua_sqm > 0.0 and storey_height_m > 0 and max_floors > 0:
        max_envelope_footprint_sqm = sqft_to_sqm(final_envelope.area) * 0.40
        if max_envelope_footprint_sqm > 0:
            max_floors_for_fsi = max(1, int(max_bua_sqm / max_envelope_footprint_sqm))
            if max_floors_for_fsi < max_floors:
                logger.info(
                    "FSI ceiling caps floor search: gdcr_max=%d → fsi_max=%d floors",
                    max_floors, max_floors_for_fsi,
                )
                max_floors = max_floors_for_fsi

    floor_candidates = _candidate_floor_counts(max_floors)

    # Pre-compute zone list once (same across all floor / tower iterations).
    _raw_zones = (zone_result.candidate_zones or []) if zone_result else []
    _raw_zones = [z for z in _raw_zones if z is not None and not z.is_empty and z.is_valid]

    best_footprints: List[FootprintCandidate] = []
    best_bua_sqm = 0.0
    best_n_requested = 0
    best_n_placed = 0
    best_floors = 0

    for floors in floor_candidates:
        if floors <= 0:
            continue

        candidate_height_m = float(floors * storey_height_m)
        if candidate_height_m <= 0:
            continue

        # Pre-compute zone footprints ONCE per floor-height, then reuse for all
        # tower counts.  This eliminates the O(MAX_TOWERS) repetition of the
        # expensive 7×7 grid optimizer that dominated wall-clock time.
        cached_zone_fps = _precompute_zone_footprints(_raw_zones, candidate_height_m) if _raw_zones else None

        for n in range(1, candidate_max_towers + 1):
            footprints, n_placed = _place_towers_by_zone(
                final_envelope=final_envelope,
                zone_result=zone_result,
                n_towers=n,
                building_height_m=candidate_height_m,
                road_corridor_geom=road_corridor_geom,
                precomputed_zone_footprints=cached_zone_fps,
            )
            if not footprints or n_placed <= 0:
                continue

            bua_sqm = 0.0
            for fp in footprints:
                area_sqft = getattr(fp, "area_sqft", 0.0) or 0.0
                bua_sqm += sqft_to_sqm(area_sqft) * floors

            # If we have a regulatory FSI ceiling, skip configurations that exceed it.
            if max_bua_sqm > 0.0 and bua_sqm > max_bua_sqm * 1.001:
                continue

            if bua_sqm > best_bua_sqm:
                best_bua_sqm = bua_sqm
                best_footprints = footprints
                best_n_requested = n
                best_n_placed = n_placed
                best_floors = floors

    if best_footprints:
        return best_footprints, best_n_placed, best_n_requested, best_floors

    # Fallback: behave like the legacy path using the maximum candidate tower count
    # and max_floors derived from the height solver.
    fallback_cached = _precompute_zone_footprints(_raw_zones, building_height_m) if _raw_zones else None
    footprints, n_placed = _place_towers_by_zone(
        final_envelope=final_envelope,
        zone_result=zone_result,
        n_towers=candidate_max_towers,
        building_height_m=building_height_m,
        road_corridor_geom=road_corridor_geom,
        precomputed_zone_footprints=fallback_cached,
    )
    if not footprints or n_placed <= 0:
        return [], 0, candidate_max_towers, max_floors or 0

    return footprints, n_placed, candidate_max_towers, max_floors or 0


def create_plan_job(plot_id: str, inputs: Dict[str, Any]) -> PlanJob:
    """
    Create a PlanJob row and start a background worker to populate it.
    """
    plot = get_plot_by_public_id(plot_id)

    with transaction.atomic():
        job = PlanJob.objects.create(
            plot=plot,
            inputs_json=inputs,
            status=PlanJob.STATUS_PENDING,
            progress=0,
        )

    # Fire-and-forget background worker.
    thread = threading.Thread(
        target=_run_plan_job_worker,
        args=(str(job.id),),
        daemon=True,
    )
    thread.start()

    return job


def _run_plan_job_worker(job_id: str) -> None:
    """
    Background worker: load job, run optimisation, store result.

    Django does not automatically manage DB connections in background threads.
    We must call close_old_connections() at the start so this thread gets a
    fresh connection rather than inheriting a potentially stale one from the
    request thread that spawned us.
    """
    # Ensure this thread gets a fresh DB connection (not a stale inherited one).
    close_old_connections()
    try:
        try:
            job = PlanJob.objects.select_related("plot").get(id=job_id)
        except PlanJob.DoesNotExist:
            logger.error("_run_plan_job_worker: job %s not found", job_id)
            return

        job.status = PlanJob.STATUS_RUNNING
        job.progress = 10
        job.save(update_fields=["status", "progress"])

        try:
            result = _build_envelope_plan_result(job)
            job.status = PlanJob.STATUS_COMPLETED
            job.progress = 100
            job.result_json = result
            job.completed_at = datetime.now(timezone.utc)
            job.save(update_fields=["status", "progress", "result_json", "completed_at"])
            logger.info("Plan job %s completed successfully", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Plan job %s failed: %s", job_id, exc)
            try:
                close_old_connections()  # reconnect in case connection dropped during computation
                job.status = PlanJob.STATUS_FAILED
                job.progress = 100
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                job.save(update_fields=["status", "progress", "error_message", "completed_at"])
            except Exception as save_exc:  # noqa: BLE001
                logger.error(
                    "Plan job %s: could not save FAILED status: %s", job_id, save_exc
                )
    finally:
        # Release the DB connection back to the pool when the thread exits.
        close_old_connections()


def _build_envelope_plan_result(job: PlanJob) -> Dict[str, Any]:
    """
    Build a plan result using the real envelope engine to compute margins,
    common open plot (COP), and buildable area.

    For now this focuses on:
      - plotBoundary  : original plot polygon
      - envelope      : buildable envelope polygon
      - cop           : carved common open plot polygon (when available)
      - copMargin     : margin band polygon (setback zone)
      - towerFootprints / spacingLines: left empty for later stages.
    """
    plot = job.plot
    inputs: Dict[str, Any] = job.inputs_json or {}
    geom = plot.geom

    if not geom:
        raise ValueError("Plot has no geometry")

    # GeoJSON plot boundary (GeoDjango already knows how to serialise).
    plot_boundary = json.loads(geom.geojson)

    minx, miny, maxx, maxy = geom.extent
    width = maxx - minx
    height = maxy - miny

    road_width_m = float(getattr(plot, "road_width_m", 0.0) or 0.0)
    if road_width_m <= 0.0:
        raise ValueError("Plot.road_width_m must be set for margin calculation")

    # Calculated building height: use regulatory height solver (GDCR + envelope + placement + layout).
    # Fall back to GDCR cap or 30 m if solver fails or returns 0.
    building_height_m: float = 30.0
    height_controlling_constraint: Optional[str] = None
    storey_height_m = float(inputs.get("storey_height_m") or 3.0)
    if storey_height_m <= 0:
        storey_height_m = 3.0

    try:
        from architecture.regulatory.height_solver import solve_max_legal_height
        height_solution = solve_max_legal_height(
            plot=plot,
            building_height_upper_bound=None,
            storey_height_m=storey_height_m,
        )
        if height_solution.max_height_m > 0:
            building_height_m = height_solution.max_height_m
            height_controlling_constraint = getattr(
                height_solution, "controlling_constraint", None
            ) or "HEIGHT_SOLVER"
        else:
            raise ValueError("Height solver returned zero")
    except Exception as e:
        logger.warning("Height solver failed, using GDCR cap: %s", e)
        try:
            from compliance.gdcr_config import load_gdcr_config
            yaml_path = settings.BASE_DIR.parent / "GDCR.yaml"
            gdcr = load_gdcr_config(yaml_path)
            max_height = gdcr.height_rules.max_height_for_road_width(road_width_m)
            building_height_m = float(max_height or 30.0)
            height_controlling_constraint = "GDCR_CAP"
        except Exception:
            building_height_m = 30.0
            height_controlling_constraint = "FALLBACK"

    # Prefer Plot.road_edges if set (assigned from DXF — more accurate than
    # the longest-edge detector fallback used when the field is blank).
    _road_edges_str = getattr(plot, "road_edges", "") or ""
    if _road_edges_str.strip():
        road_edges = [int(x) for x in _road_edges_str.split(",") if x.strip()]
        logger.info("Using Plot.road_edges field: %s", road_edges)
    else:
        road_edges, _ = detect_road_edges_with_meta(geom, None)

    env = compute_envelope(
        plot_wkt=geom.wkt,
        building_height=building_height_m,
        road_width=road_width_m,
        road_facing_edges=road_edges,
        enforce_gc=True,
    )

    if env.status != "VALID" or env.envelope_polygon is None:
        raise ValueError(f"Envelope invalid for plot: status={env.status}")

    # ── Internal road network (before placement) ────────────────────────────────
    plot_polygon = shapely_loads(geom.wkt)
    road_result = generate_internal_road_network(
        plot_polygon=plot_polygon,
        envelope_polygon=env.envelope_polygon,
        cop_polygon=getattr(env, "common_plot_polygon", None),
        road_facing_edge_indices=road_edges or [],
    )
    internal_roads_geojson: List[Dict[str, Any]] = []
    road_corridors_geojson: List[Dict[str, Any]] = []
    corridor_union: Optional[Any] = None
    final_envelope = env.envelope_polygon
    if road_result.status == "VALID" and road_result.centreline_linestrings:
        for ls in road_result.centreline_linestrings:
            g = geometry_to_geojson(ls)
            if g:
                internal_roads_geojson.append(g)
        corridors = road_result.road_corridor_polygons if getattr(road_result, "road_corridor_polygons", None) else road_network_corridor_polygons(
            road_result.centreline_linestrings,
            road_result.road_width_dxf,
        )
        for poly in corridors:
            pg = geometry_to_geojson(poly)
            if pg:
                road_corridors_geojson.append(pg)
        if corridors:
            try:
                corridor_union = unary_union(corridors)
                if corridor_union is not None and not corridor_union.is_empty:
                    final_envelope = final_envelope.difference(corridor_union)
                    if final_envelope.is_empty or (hasattr(final_envelope, "geoms") and not list(final_envelope.geoms)):
                        final_envelope = env.envelope_polygon
                    elif hasattr(final_envelope, "geoms"):
                        final_envelope = max(final_envelope.geoms, key=lambda g: getattr(g, "area", 0))
            except Exception:
                pass

    # ── Pipeline validation: envelope ───────────────────────────────────────────
    if final_envelope is None or getattr(final_envelope, "is_empty", True) or getattr(final_envelope, "area", 0) <= 0:
        raise ValueError("Envelope is empty after road corridor subtraction")

    # ── Pipeline validation: COP ⊂ plot ─────────────────────────────────────────
    cop_polygon = getattr(env, "common_plot_polygon", None)
    if cop_polygon is not None and not cop_polygon.is_empty:
        if not plot_polygon.contains(cop_polygon) and not plot_polygon.covers(cop_polygon):
            try:
                if cop_polygon.intersection(plot_polygon).area < cop_polygon.area * 0.99:
                    raise ValueError("COP is not contained in plot")
            except Exception as e:
                if "COP" in str(e):
                    raise
                logger.warning("COP containment check: %s", e)

    # Placement zones (split envelope into candidate zones, ranked by area)
    zone_result = generate_placement_zones(final_envelope)
    tower_zones_geojson: List[Dict[str, Any]] = []
    if zone_result.candidate_zones:
        for z in zone_result.candidate_zones:
            g = geometry_to_geojson(z)
            if g:
                tower_zones_geojson.append(g)

    envelope_geo = geometry_to_geojson(final_envelope) or wkt_to_geojson(final_envelope.wkt)
    cop_geo = (
        wkt_to_geojson(env.common_plot_polygon.wkt)
        if getattr(env, "common_plot_polygon", None) is not None
        else None
    )
    margin_geo = (
        wkt_to_geojson(env.margin_polygon.wkt)
        if getattr(env, "margin_polygon", None) is not None
        else None
    )

    # ── Metrics pre-pass: FSI ceiling for later configuration search ────────────
    plot_area_sqm = float(plot.plot_area_sqm)
    cop_required_sqm = _cop_required_sqm(plot_area_sqm)
    cop_provided_sqm = sqft_to_sqm(float(env.common_plot_area_sqft or 0.0))
    max_fsi = None
    try:
        from architecture.feasibility.regulatory_metrics import _get_gdcr_fsi
        _, max_fsi_val = _get_gdcr_fsi()
        max_fsi = float(max_fsi_val)
        max_bua_sqm = plot_area_sqm * max_fsi
    except Exception as e:
        logger.warning("FSI debug: failed to read GDCR FSI config: %s", e)
        max_bua_sqm = 0.0

    # GDCR road-width cap: upper bound on building height from the road width
    # table, independent of envelope geometry.  Used to raise the floor search
    # ceiling beyond what the height solver returns (which is constrained by
    # the current envelope footprint area).
    gdcr_max_height_m = 0.0
    try:
        from architecture.regulatory_accessors import get_max_permissible_height_by_road_width
        gdcr_max_height_m = float(get_max_permissible_height_by_road_width(road_width_m) or 0.0)
    except Exception as e:
        logger.warning("Could not fetch GDCR road-width height cap: %s", e)

    # Debug logging for development configuration diagnostics (pre-solver).
    logger.warning(
        "DEV_CONFIG_DEBUG: plot_area_sqm=%.3f road_width_m=%.3f max_fsi=%s "
        "max_bua_sqm=%.3f max_height_m=%.3f gdcr_max_height_m=%.3f storey_height_m=%.3f",
        plot_area_sqm,
        road_width_m,
        f"{max_fsi:.3f}" if isinstance(max_fsi, (int, float)) else "None",
        max_bua_sqm,
        building_height_m,
        gdcr_max_height_m,
        storey_height_m,
    )

    # ── Tower placement: configuration search over floors × tower count ─────────
    tower_pref = inputs.get("towerCount", "auto")
    logger.warning(
        "TOWER_SEARCH_START: building_height_m=%.3f tower_pref=%s storey_height_m=%.3f max_bua_sqm=%.3f gdcr_max_height_m=%.3f",
        building_height_m, tower_pref, storey_height_m, max_bua_sqm, gdcr_max_height_m,
    )
    all_footprints, n_towers_placed, n_towers_requested, floor_count = _search_best_tower_layout(
        final_envelope=final_envelope,
        zone_result=zone_result,
        building_height_m=building_height_m,
        road_corridor_geom=corridor_union,
        tower_pref=tower_pref,
        storey_height_m=storey_height_m,
        max_bua_sqm=max_bua_sqm,
        gdcr_max_height_m=gdcr_max_height_m,
    )
    logger.warning(
        "TOWER_SEARCH_DONE: n_placed=%d n_requested=%d floor_count=%d footprints=%d",
        n_towers_placed, n_towers_requested, floor_count, len(all_footprints),
    )

    # ── Pipeline validation: towers ⊂ envelope ──────────────────────────────────
    for fp in all_footprints:
        poly = getattr(fp, "footprint_polygon", None)
        if poly is not None and not poly.is_empty:
            if not final_envelope.contains(poly) and not final_envelope.covers(poly):
                try:
                    if poly.intersection(final_envelope).area < poly.area * 0.99:
                        raise ValueError("Tower footprint is not contained in envelope")
                except Exception as e:
                    if "Tower" in str(e):
                        raise
                    logger.warning("Tower containment: %s", e)

    # ── Road access validation (metrics only; hard constraint enforced in placement) ─
    road_access_ok = True
    if corridor_union is not None and not corridor_union.is_empty and all_footprints:
        polygons = [
            getattr(fp, "footprint_polygon", None)
            for fp in all_footprints
            if getattr(fp, "footprint_polygon", None) is not None and not fp.footprint_polygon.is_empty
        ]
        if polygons:
            road_access_ok = all_towers_have_road_access(
                polygons,
                corridor_union,
                max_distance_m=DEFAULT_ROAD_ACCESS_MAX_DISTANCE_M,
            )

    # ── Metrics: achieved BUA, FSI, floor count, COP, parking ───────────────────
    total_footprint_sqm = 0.0
    for fp in all_footprints:
        total_footprint_sqm += sqft_to_sqm(getattr(fp, "area_sqft", 0.0) or 0.0)
    achieved_bua_sqm = total_footprint_sqm * max(1, floor_count)
    achieved_fsi = (achieved_bua_sqm / plot_area_sqm) if plot_area_sqm > 0 else 0.0
    achieved_gc_pct = (total_footprint_sqm / plot_area_sqm * 100.0) if plot_area_sqm > 0 else 0.0

    # Height implied by chosen floor count (may be below regulatory maximum).
    chosen_building_height_m = float(floor_count * storey_height_m) if floor_count and storey_height_m else building_height_m

    logger.warning(
        "GC_DEBUG: plot_area_sqm=%.3f total_footprint_sqm=%.3f "
        "actual_gc=%.2f%% target_gc=%.1f%% floor_count=%d achieved_fsi=%.4f "
        "gdcr_max_height_m=%.1f",
        plot_area_sqm,
        total_footprint_sqm,
        achieved_gc_pct,
        float(env.ground_coverage_pct or 0.0),
        floor_count,
        achieved_fsi,
        gdcr_max_height_m,
    )

    # ── Tower geometry + spacing visuals ────────────────────────────────────────
    tower_geoms: List[Dict[str, Any]] = []
    spacing_lines: List[Dict[str, Any]] = []
    centroids: List[Tuple[float, float]] = []

    for idx, fp in enumerate(all_footprints):
        poly = getattr(fp, "footprint_polygon", None)
        if poly is None or poly.is_empty:
            continue
        geom = wkt_to_geojson(poly.wkt)
        if not geom:
            continue
        tower_id = f"T{idx + 1}"
        tower_geoms.append(
            {
                "type": "Feature",
                "id": tower_id,
                "geometry": geom,
                "properties": {
                    "towerId": tower_id,
                    "index": idx,
                    "floors": floor_count,
                    "height": chosen_building_height_m,
                },
            }
        )
        c = poly.centroid
        centroids.append((float(c.x), float(c.y)))

    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            (x1, y1), (x2, y2) = centroids[i], centroids[j]
            spacing_lines.append(
                {
                    "type": "LineString",
                    "coordinates": [[x1, y1], [x2, y2]],
                }
            )

    plot_id_public = f"{plot.tp_scheme}-{plot.fp_number}"

    result = {
        "planId": str(job.id),
        "plotId": plot_id_public,
        "metrics": {
            "plotAreaSqm": plot_area_sqm,
            "envelopeAreaSqft": float(env.envelope_area_sqft or 0.0),
            "groundCoveragePct": float(env.ground_coverage_pct or 0.0),
            "copAreaSqft": float(env.common_plot_area_sqft or 0.0),
            "copStatus": getattr(env, "common_plot_status", "NA"),
            "buildingHeightM": chosen_building_height_m,
            "heightControllingConstraint": height_controlling_constraint or "HEIGHT_SOLVER",
            "roadWidthM": road_width_m,
            "nTowersRequested": n_towers_requested,
            "nTowersPlaced": n_towers_placed,
            "spacingRequiredM": float(required_spacing_m(chosen_building_height_m)),
            "maxFSI": round(float(max_fsi), 3) if isinstance(max_fsi, (int, float)) else None,
            "achievedFSI": round(achieved_fsi, 4),
            "achievedGCPct": round(achieved_gc_pct, 2),
            "totalFootprintSqm": round(total_footprint_sqm, 2),
            "gdcrMaxHeightM": round(gdcr_max_height_m, 2),
            "achievedBUA": round(achieved_bua_sqm, 2),
            "maxBUA": round(max_bua_sqm, 2),
            "floorCount": floor_count,
            "copRequiredSqm": round(cop_required_sqm, 2),
            "copProvidedSqm": round(cop_provided_sqm, 2),
            "roadAccessOk": road_access_ok,
        },
        "geometry": {
            "plotBoundary": plot_boundary,
            "envelope": envelope_geo,
            "cop": cop_geo,
            "copMargin": margin_geo,
            "internalRoads": internal_roads_geojson,
            "roadCorridors": road_corridors_geojson,
            "towerZones": tower_zones_geojson,
            "towerFootprints": tower_geoms,
            "spacingLines": spacing_lines,
        },
        "debug": {
            "buildableEnvelope": envelope_geo,
            "copCandidateZones": [cop_geo] if cop_geo else [],
            "roadNetwork": internal_roads_geojson,
            "towerZones": tower_zones_geojson,
        },
    }
    try:
        if envelope_geo:
            result["geometry"]["envelope"] = validate_geojson_geometry(envelope_geo) or envelope_geo
        if cop_geo:
            result["geometry"]["cop"] = validate_geojson_geometry(cop_geo) or cop_geo
    except Exception:
        pass
    return result


def get_plan_job_status(job_id: str) -> Dict[str, Any]:
    job = PlanJob.objects.get(id=job_id)
    return {
        "jobId": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "errorMessage": job.error_message,
    }


def get_plan_job_result(job_id: str) -> Dict[str, Any]:
    job = PlanJob.objects.get(id=job_id)
    if job.result_json is None:
        raise ValueError("Plan job has no result yet")
    return job.result_json


__all__ = [
    "create_plan_job",
    "get_plan_job_status",
    "get_plan_job_result",
]

