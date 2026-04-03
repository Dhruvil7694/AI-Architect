from __future__ import annotations

import dataclasses
import itertools
import json
import logging
import math
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable

from django.db import transaction, close_old_connections
from django.conf import settings
from shapely.affinity import scale as shapely_scale_geom
from shapely.wkt import loads as shapely_loads
from shapely.ops import unary_union
from shapely.geometry import Polygon

from architecture.models import PlanJob
from architecture.regulatory_accessors import get_cop_required_fraction
from services.plot_service import get_plot_by_public_id
from architecture.spatial.road_edge_detector import (
    detect_road_edges_with_meta,
    select_governing_road_edges,
)
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
from common.units import dxf_plane_area_to_sqm, dxf_to_metres, sqm_to_sqft

logger = logging.getLogger(__name__)

STOREY_HEIGHT_M = 3.0


def _normalize_inputs(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map frontend camelCase PlannerInputs keys to the snake_case keys
    that the backend pipeline (program_spec_mapper, height_solver, etc.) expects.

    The frontend sends: buildingType, floors, unitsPerCore, segment,
    nBuildings, unitMix, storeyHeightM.
    The backend reads:  building_type, towerCount, storey_height_m,
    preferredFloors.max, units_per_core, etc.
    """
    out = dict(raw)
    if "nBuildings" in out and "towerCount" not in out:
        val = out.pop("nBuildings")
        if val is not None:
            out["towerCount"] = val
    if "floors" in out and "preferredFloors" not in out:
        val = out.pop("floors")
        if val is not None:
            out["preferredFloors"] = {"max": val}
    if "storeyHeightM" in out and "storey_height_m" not in out:
        out["storey_height_m"] = out.pop("storeyHeightM")
    if "buildingType" in out and "building_type" not in out:
        out["building_type"] = out.pop("buildingType")
    if "unitsPerCore" in out and "units_per_core" not in out:
        out["units_per_core"] = out.pop("unitsPerCore")
    return out


def _scale_footprints_to_bua(
    footprints: List[FootprintCandidate],
    current_bua_sqm: float,
    target_bua_sqm: float,
) -> List[FootprintCandidate]:
    """
    Scale footprint polygons uniformly so that their total gross BUA equals
    *target_bua_sqm* (≤ current_bua_sqm).

    Used when the DP inscribed-rectangle returns a footprint larger than
    required for the current floor count.  Scaling preserves polygon shape and
    centroid; the result is guaranteed to be ≤ the original in size, so it
    stays inside the zone.

    Returns the same list unchanged if target >= current (no scale needed).
    """
    if target_bua_sqm >= current_bua_sqm or current_bua_sqm <= 0 or not footprints:
        return footprints

    # Uniform linear scale factor applied to both axes of each polygon.
    # area scales by factor², so linear_factor = sqrt(target/current).
    linear_factor = math.sqrt(target_bua_sqm / current_bua_sqm)

    scaled: List[FootprintCandidate] = []
    for fp in footprints:
        poly = getattr(fp, "footprint_polygon", None)
        if poly is None or poly.is_empty:
            scaled.append(fp)
            continue
        new_poly = shapely_scale_geom(poly, xfact=linear_factor, yfact=linear_factor, origin="centroid")
        new_area_sqft = fp.area_sqft * (linear_factor ** 2)
        scaled.append(dataclasses.replace(
            fp,
            footprint_polygon=new_poly,
            area_sqft=new_area_sqft,
            width_dxf=fp.width_dxf * linear_factor,
            depth_dxf=fp.depth_dxf * linear_factor,
            width_m=fp.width_m * linear_factor,
            depth_m=fp.depth_m * linear_factor,
        ))
    return scaled


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

    Uses the DP inscribed-rectangle solver (via compute_placement → pack_towers →
    find_best_inscribed_rect) as the primary method — this is the same algorithm
    that achieves ~1,359 m² on FP133.  The grid-based footprint_optimizer is run
    as a secondary source and its candidates are merged in, taking the top-3 by area.

    The old order (grid first, DP fallback only when grid returns nothing) produced
    footprints ~3× smaller than optimal because the centre-grid check misses the
    true maximum inscribed rectangle in irregular/rotated zones.
    """
    zone_footprints: List[List[FootprintCandidate]] = []
    for zone in zones:
        try:
            # Primary: DP inscribed-rectangle via compute_placement (pack_towers).
            # This is the high-quality path that correctly handles rotated/irregular zones.
            placement = compute_placement(
                envelope_wkt=zone.wkt,
                building_height_m=building_height_m,
                n_towers=1,
            )
            dp_candidates = list(placement.footprints) if placement.footprints else []

            # Secondary: grid optimizer — may contribute additional candidate shapes.
            try:
                grid_candidates = generate_footprint_candidates_in_zone(
                    zone, building_height_m, top_n=3
                )
            except Exception:  # noqa: BLE001
                grid_candidates = []

            # Merge, deduplicate by area, keep top-3 largest.
            all_cands = dp_candidates + grid_candidates
            all_cands.sort(key=lambda c: getattr(c, "area_sqft", 0.0), reverse=True)

            if all_cands:
                zone_footprints.append(all_cands[:3])
            else:
                zone_footprints.append([])
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

        # Pre-compute which (i, j) zone-pairs are road-separated (the zone polygons
        # have a non-zero gap between them due to the road corridor subtraction).
        # GDCR H/3 inter-building spacing applies to buildings within the same
        # zone (plot area). When zones are separated by an internal road corridor,
        # the road itself provides the required physical separation — the H/3 check
        # must NOT be applied to those pairs, otherwise large-height towers can
        # never be placed across the road.
        zone_polys_in_combo = [zones[i] for i in indices]
        road_separated_pairs: set = set()
        for _pi in range(k_local):
            for _pj in range(_pi + 1, k_local):
                try:
                    if zone_polys_in_combo[_pi].distance(zone_polys_in_combo[_pj]) > 1e-6:
                        road_separated_pairs.add((_pi, _pj))
                except Exception:  # noqa: BLE001
                    pass

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
            # Skip spacing check for zone-pairs already separated by the road
            # corridor — those towers can never fail H/3 due to the road gap.
            if road_separated_pairs:
                audit = [e for e in audit if tuple(e["pair"]) not in road_separated_pairs]
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
    user_max_floors: int = 0,
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

    # Cap max_floors by user preference (preferredFloors.max from frontend inputs).
    if user_max_floors > 0 and max_floors > user_max_floors:
        logger.info(
            "User preferredFloors.max=%d caps floor search from %d",
            user_max_floors, max_floors,
        )
        max_floors = user_max_floors

    # NOTE: The old FSI-based floor ceiling (40% envelope × max_floors estimate) is
    # intentionally removed.  Oversized footprints are now scaled down by
    # _scale_footprints_to_bua() so all floor counts from 1 to GDCR max are valid.
    # Searching all candidates costs modestly more but avoids missing the optimal
    # configuration (e.g. 23 floors × 640 m² footprint for FSI 4.0 on a 60m road).

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
                area_dxf2 = getattr(fp, "area_sqft", 0.0) or 0.0
                bua_sqm += dxf_plane_area_to_sqm(area_dxf2) * floors

            # If gross BUA exceeds the FSI ceiling, scale footprints down so that
            # footprint × floors = max_bua.  This keeps the correct floor count
            # (e.g. 23 floors at 60m road) while shrinking the plate to FSI-limit
            # size (e.g. 1,359 m² → 640 m² at 23 floors → FSI ≈ 4.0).
            # Scaling is safe because a smaller concentric rectangle is always
            # contained within the zone that held the original.
            if max_bua_sqm > 0.0 and bua_sqm > max_bua_sqm * 1.001:
                footprints = _scale_footprints_to_bua(footprints, bua_sqm, max_bua_sqm)
                bua_sqm = max_bua_sqm

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

        def _update_progress(p: int) -> None:
            if 0 <= p <= 100:
                job.progress = p
                job.save(update_fields=["progress"])

        try:
            result = _build_envelope_plan_result(job, _update_progress)
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


def _build_envelope_plan_result(
    job: PlanJob,
    update_progress: Optional[Callable[[int], None]] = None,
) -> Dict[str, Any]:
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
    inputs: Dict[str, Any] = _normalize_inputs(job.inputs_json or {})
    geom = plot.geom

    # Build ProgramSpec from frontend inputs — wire unit_mix, segment, towerCount,
    # and preferredFloors into the pipeline so they actually influence plan generation.
    from planning.program_spec_mapper import build_program_spec_from_inputs
    program_spec = build_program_spec_from_inputs(inputs)
    logger.info(
        "ProgramSpec: unit_mix=%s preferred_towers=%d max_floors=%d density=%s open_space=%s",
        program_spec.unit_mix,
        program_spec.preferred_towers,
        program_spec.max_floors,
        program_spec.density_priority,
        program_spec.open_space_priority,
    )

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
    road_edges, road_meta = select_governing_road_edges(geom, road_edges)
    logger.info(
        "Road governance: detected=%s selected=%s policy=%s keep_n=%s",
        road_meta.get("total_road_edges_detected"),
        road_meta.get("governing_road_edges"),
        road_meta.get("selection_policy"),
        road_meta.get("max_road_edges_considered"),
    )

    env = compute_envelope(
        plot_wkt=geom.wkt,
        building_height=building_height_m,
        road_width=road_width_m,
        road_facing_edges=road_edges,
        enforce_gc=True,
    )
    if update_progress:
        update_progress(25)

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
    _zone_envelope = env.envelope_polygon  # may become MultiPolygon after road subtraction
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
            # Clip each corridor to the plot boundary so it never extends outside
            # the cadastral boundary when rendered on the frontend.
            try:
                clipped = poly.intersection(plot_polygon)
            except Exception:
                clipped = poly
            if clipped is None or clipped.is_empty:
                continue
            pg = geometry_to_geojson(clipped)
            if pg:
                road_corridors_geojson.append(pg)
        if corridors:
            try:
                corridor_union = unary_union(corridors)
                if corridor_union is not None and not corridor_union.is_empty:
                    _subtracted = final_envelope.difference(corridor_union)
                    if _subtracted.is_empty or (hasattr(_subtracted, "geoms") and not list(_subtracted.geoms)):
                        # Subtraction wiped out everything — keep original
                        _zone_envelope = env.envelope_polygon
                    else:
                        # Preserve the FULL subtracted result (may be MultiPolygon) for
                        # zone generation so both halves become candidate tower zones.
                        # final_envelope keeps the largest single Polygon only for the
                        # fallback placement path and containment validation.
                        _zone_envelope = _subtracted
                        if hasattr(_subtracted, "geoms"):
                            final_envelope = max(_subtracted.geoms, key=lambda g: getattr(g, "area", 0))
                        else:
                            final_envelope = _subtracted
            except Exception:
                _zone_envelope = final_envelope
        else:
            _zone_envelope = final_envelope

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

    # Placement zones — use _zone_envelope (preserves all pieces after road corridor
    # subtraction) so every buildable region becomes a candidate zone.  This allows
    # the optimizer to place towers on both sides of the internal road, eliminating
    # the large empty space that appeared when only the largest piece was used.
    zone_result = generate_placement_zones(_zone_envelope)
    if update_progress:
        update_progress(45)
    tower_zones_geojson: List[Dict[str, Any]] = []
    if zone_result.candidate_zones:
        for z in zone_result.candidate_zones:
            g = geometry_to_geojson(z)
            if g:
                tower_zones_geojson.append(g)

    envelope_geo = geometry_to_geojson(final_envelope) or wkt_to_geojson(final_envelope.wkt)

    # Build COP as a GeoJSON Feature (not bare geometry) so the frontend hover
    # and inspector can display area, dimensions, and GDCR compliance status.
    cop_geo = None
    _cop_poly = getattr(env, "common_plot_polygon", None)
    if _cop_poly is not None and not _cop_poly.is_empty:
        _cop_geom = wkt_to_geojson(_cop_poly.wkt)
        if _cop_geom:
            _cop_area_dxf2 = float(env.common_plot_area_sqft or 0.0)
            _cop_area_sqm = dxf_plane_area_to_sqm(_cop_area_dxf2)
            # Compute bounding-box width/depth to check GDCR minimum dimension.
            _minx, _miny, _maxx, _maxy = _cop_poly.bounds
            _cop_width_m  = round(dxf_to_metres(_maxx - _minx), 2)
            _cop_depth_m  = round(dxf_to_metres(_maxy - _miny), 2)
            _cop_min_dim  = min(_cop_width_m, _cop_depth_m)
            # GDCR: minimum dimension ≥ 7.5 m (GDCR.yaml minimum_dimension_m)
            _gdcr_min_dim = 7.5
            cop_geo = {
                "type": "Feature",
                "geometry": _cop_geom,
                "properties": {
                    "area_sqft":       round(sqm_to_sqft(_cop_area_sqm), 1),
                    "area_sqm":        round(_cop_area_sqm, 1),
                    "width_m":         _cop_width_m,
                    "depth_m":         _cop_depth_m,
                    "min_dimension_m": round(_cop_min_dim, 2),
                    "cop_ok":          _cop_min_dim >= _gdcr_min_dim,
                    "gdcr_min_dim_m":  _gdcr_min_dim,
                    "status":          getattr(env, "common_plot_status", "NA"),
                },
            }
    margin_geo = (
        wkt_to_geojson(env.margin_polygon.wkt)
        if getattr(env, "margin_polygon", None) is not None
        else None
    )

    # ── Metrics pre-pass: FSI ceiling for later configuration search ────────────
    plot_area_sqm = float(plot.plot_area_sqm)
    cop_required_sqm = _cop_required_sqm(plot_area_sqm)
    cop_provided_sqm = dxf_plane_area_to_sqm(
        float(env.common_plot_area_sqft or 0.0)
    )
    max_fsi = None
    fsi_decision = None
    try:
        # Use per-plot corridor-eligible FSI (based on actual road width and distance
        # to wide road) rather than the global maximum across all plots.
        from architecture.regulatory.fsi_policy import resolve_fsi_policy
        fsi_decision = resolve_fsi_policy(plot=plot, road_width_m=road_width_m)
        max_fsi = float(fsi_decision.max_fsi)
        max_bua_sqm = plot_area_sqm * max_fsi
        logger.info(
            "FSI policy: corridor_eligible=%s max_fsi=%.3f (authority=%s zone=%s)",
            fsi_decision.corridor_eligible,
            max_fsi,
            fsi_decision.authority,
            fsi_decision.zone,
        )
    except Exception as e:
        logger.warning("FSI policy lookup failed, falling back to 0: %s", e)
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
    # Use program_spec.preferred_towers if explicitly set (overrides raw input string).
    tower_pref = inputs.get("towerCount", "auto")
    if program_spec.preferred_towers > 0:
        tower_pref = program_spec.preferred_towers

    # User's preferred max floors (0 = unconstrained).
    user_max_floors = max(0, int(program_spec.max_floors or 0))

    # ── AI-powered tower layout (try before deterministic search) ────────────
    generation_source = "deterministic"
    ai_design_rationale = ""

    # Derive max_floors for AI the same way the deterministic solver does.
    height_ceiling = gdcr_max_height_m if gdcr_max_height_m > building_height_m else building_height_m
    ai_max_floors = int(height_ceiling / storey_height_m) if storey_height_m > 0 else 0
    if user_max_floors > 0 and ai_max_floors > user_max_floors:
        ai_max_floors = user_max_floors

    _zone_polys = (zone_result.candidate_zones or []) if zone_result else []
    _zone_polys = [z for z in _zone_polys if z is not None and not z.is_empty and z.is_valid]

    ai_result = None
    try:
        from services.ai_site_plan_service import generate_ai_site_plan
        ai_result = generate_ai_site_plan(
            plot=plot,
            envelope_result=env,
            fsi_decision=fsi_decision,
            inputs=inputs,
            road_info={
                "road_width_m": road_width_m,
                "building_height_m": building_height_m,
                "storey_height_m": storey_height_m,
                "max_floors": ai_max_floors,
                "gdcr_max_height_m": gdcr_max_height_m,
                "corridor_union": corridor_union,
                "max_bua_sqm": max_bua_sqm,
                "max_fsi": max_fsi,
            },
            final_envelope=final_envelope,
            zone_polygons=_zone_polys,
        )
    except Exception as ai_exc:
        logger.exception("AI site plan generation failed: %s", ai_exc)

    if ai_result is not None:
        all_footprints = ai_result["footprints"]
        n_towers_placed = ai_result["n_placed"]
        n_towers_requested = ai_result["n_placed"]
        floor_count = ai_result["floor_count"]
        generation_source = "ai"
        ai_design_rationale = ai_result.get("design_rationale", "")
        logger.info(
            "AI_SITE_PLAN: using AI layout — %d towers, %d floors, rationale=%s",
            n_towers_placed, floor_count, ai_design_rationale[:100],
        )
    else:
        logger.warning(
            "TOWER_SEARCH_START: building_height_m=%.3f tower_pref=%s user_max_floors=%d "
            "storey_height_m=%.3f max_bua_sqm=%.3f gdcr_max_height_m=%.3f",
            building_height_m, tower_pref, user_max_floors, storey_height_m, max_bua_sqm, gdcr_max_height_m,
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
            user_max_floors=user_max_floors,
        )
    logger.warning(
        "TOWER_SEARCH_DONE: source=%s n_placed=%d n_requested=%d floor_count=%d footprints=%d",
        generation_source, n_towers_placed, n_towers_requested, floor_count, len(all_footprints),
    )
    if update_progress:
        update_progress(75)

    # ── Pipeline validation: towers ⊂ envelope ──────────────────────────────────
    # Use _zone_envelope (full MultiPolygon including all zones) not final_envelope
    # (Zone 1 only) so towers placed in Zone 2 pass the containment check.
    _containment_geom = _zone_envelope
    for fp in all_footprints:
        poly = getattr(fp, "footprint_polygon", None)
        if poly is not None and not poly.is_empty:
            if not _containment_geom.contains(poly) and not _containment_geom.covers(poly):
                try:
                    if poly.intersection(_containment_geom).area < poly.area * 0.99:
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

    # ── Layout quality score ─────────────────────────────────────────────────────
    layout_quality_score: Optional[float] = None
    if all_footprints and final_envelope is not None:
        try:
            from placement_engine.scoring.layout_scorer import score_layout
            from placement_engine.geometry.packer import PackingResult as _PR
            from placement_engine.geometry.spacing_enforcer import audit_spacing, any_spacing_fail
            _fps = [fp for fp in all_footprints
                    if getattr(fp, "footprint_polygon", None) is not None]
            if _fps:
                _placed_polys = [fp.footprint_polygon for fp in _fps]
                _audit = audit_spacing(_placed_polys, building_height_m)
                _pr = _PR(
                    mode="FINAL",
                    footprints=_fps,
                    n_placed=len(_fps),
                    total_area_sqft=sum(getattr(fp, "area_sqft", 0.0) for fp in _fps),
                    spacing_audit=_audit,
                    has_spacing_fail=any_spacing_fail(_audit),
                )
                _lqs = score_layout(_pr, final_envelope)
                layout_quality_score = round(_lqs.composite, 3)
        except Exception as _e:
            logger.debug("Layout quality scoring failed: %s", _e)

    # ── Metrics: achieved BUA, FSI, floor count, COP, parking ───────────────────
    total_footprint_sqm = 0.0
    for fp in all_footprints:
        total_footprint_sqm += dxf_plane_area_to_sqm(
            getattr(fp, "area_sqft", 0.0) or 0.0
        )
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
        fp_area_dxf2 = float(getattr(fp, "area_sqft", 0.0) or 0.0)
        fp_width_m   = float(getattr(fp, "width_m",   0.0) or 0.0)
        fp_depth_m   = float(getattr(fp, "depth_m",   0.0) or 0.0)
        fp_area_sqm  = dxf_plane_area_to_sqm(fp_area_dxf2)
        tower_bua_sqm = fp_area_sqm * max(1, floor_count)
        tower_geoms.append(
            {
                "type": "Feature",
                "id": tower_id,
                "geometry": geom,
                "properties": {
                    "towerId":      tower_id,
                    "index":        idx,
                    "floors":       floor_count,
                    "height_m":     round(chosen_building_height_m, 2),
                    "area_sqft":    round(sqm_to_sqft(fp_area_sqm), 1),
                    "area_sqm":     round(fp_area_sqm, 1),
                    "width_m":      round(fp_width_m, 2),
                    "depth_m":      round(fp_depth_m, 2),
                    "bua_sqm":      round(tower_bua_sqm, 1),
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
            "corridorEligible": getattr(fsi_decision, "corridor_eligible", None),
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
            "layoutQualityScore": layout_quality_score,
            "generationSource": generation_source,
            "designRationale": ai_design_rationale or None,
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

