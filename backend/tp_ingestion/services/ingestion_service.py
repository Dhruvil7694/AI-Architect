"""
ingestion_service.py
--------------------
Orchestrates the full TP ingestion pipeline:

    1. Read DXF  → polygons + labels
    2. Read Excel → {fp_number: area_excel}
    3. Match labels to polygons spatially
    4. Validate area for each matched plot
    5. Save valid (and optionally invalid) records via Django ORM

This module is the single entry-point called by the management command.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from django.contrib.gis.geos import Point as GEOSPoint, Polygon as GEOSPolygon

from shapely.ops import polygonize, polygonize_full, unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid
from shapely.geometry import Polygon

from tp_ingestion.models import Plot, BlockLabel
from tp_ingestion.services.area_validator import validate_area, DEFAULT_TOLERANCE
from tp_ingestion.services.dxf_reader import read_dxf
from tp_ingestion.services.excel_reader import read_excel_all_areas
from tp_ingestion.services.geometry_matcher import match_fp_to_polygons, _is_fp_number
from tp_ingestion.geometry_utils import get_label_point

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    """Summary of a completed ingestion run."""

    city: str
    tp_scheme: str
    total_polygons: int = 0
    total_labels: int = 0
    matched: int = 0
    unmatched_labels: List[str] = field(default_factory=list)
    fp_numbers_not_in_excel: List[str] = field(default_factory=list)
    validated_ok: int = 0
    validated_fail: int = 0
    saved: int = 0
    updated: int = 0
    skipped_duplicates: int = 0

    def print_summary(self) -> None:
        lines = [
            "",
            "=" * 60,
            f"  Ingestion Report — {self.city} / {self.tp_scheme}",
            "=" * 60,
            f"  DXF polygons extracted : {self.total_polygons}",
            f"  Text labels found      : {self.total_labels}",
            f"  Labels matched         : {self.matched}",
            f"  Labels unmatched       : {len(self.unmatched_labels)}",
            f"  FP not in Excel        : {len(self.fp_numbers_not_in_excel)}",
            f"  Area validation OK     : {self.validated_ok}",
            f"  Area validation FAIL   : {self.validated_fail}",
            f"  Records saved          : {self.saved}",
            f"  Records updated         : {self.updated}",
            f"  Duplicates skipped      : {self.skipped_duplicates}",
            "=" * 60,
        ]
        for line in lines:
            logger.info(line)


def run_ingestion(
    dxf_path: str | Path,
    excel_path: str | Path,
    city: str,
    tp_scheme: str,
    area_tolerance: float = DEFAULT_TOLERANCE,
    snap_tolerance: float = 1.0,
    save_invalid: bool = False,
    dry_run: bool = False,
    update_existing: bool = False,
    polygon_layers: list | None = None,
    label_layers: list | None = None,
    debug_geojson_dir: str | Path | None = None,
    snap_decimals: int = 2,
    polygonize_buffer: float = 0.0,
    include_block_labels: bool = False,
) -> IngestionReport:
    """
    Execute the full TP/FP ingestion pipeline.

    Parameters
    ----------
    dxf_path        : path to the TP scheme DXF file
    excel_path      : path to the corresponding Excel metadata file (.xlsx, .xls, or .csv)
    city            : city name (e.g. "Ahmedabad")
    tp_scheme       : TP scheme identifier (e.g. "TP14")
    area_tolerance  : relative area error threshold (default 5 %)
    snap_tolerance  : max distance for label–polygon snap fallback (DXF units)
    save_invalid    : if True, records that fail area validation are still saved
    dry_run         : if True, parse and validate but do NOT write to the database
    update_existing : if True, update geometry (and area) for existing plots instead of skipping
    polygon_layers  : restrict polygon extraction to these DXF layer names
    label_layers    : restrict label extraction to these DXF layer names

    Returns
    -------
    IngestionReport
    """
    report = IngestionReport(city=city, tp_scheme=tp_scheme)

    # ── Step 1: Read DXF ────────────────────────────────────────────────────
    dxf_result = read_dxf(
        dxf_path,
        polygon_layers=polygon_layers,
        label_layers=label_layers,
        debug_output_dir=debug_geojson_dir,
        snap_decimals=snap_decimals,
        polygonize_buffer=polygonize_buffer,
    )
    report.total_polygons = len(dxf_result.polygons)
    report.total_labels = len(dxf_result.labels)
    dxf_segments = dxf_result.segments

    # ── Step 2: Read Excel (all areas per FP for duplicate-row resolution) ───
    fp_areas_map = read_excel_all_areas(excel_path)

    # ── Step 3: Spatial matching ────────────────────────────────────────────
    matched_plots, unmatched = match_fp_to_polygons(
        dxf_result.polygons,
        dxf_result.labels,
        snap_tolerance=snap_tolerance,
    )
    report.matched = len(matched_plots)
    report.unmatched_labels = unmatched

    segments_tree = STRtree(dxf_segments) if dxf_segments else None

    # ── Step 3b: Recover unmatched numeric FP labels via segment polygonization ──
    # Build a label lookup so we can find the insertion point for unmatched FPs
    label_lookup: dict[str, Point] = {}
    for txt, pt in dxf_result.labels:
        if _is_fp_number(txt) and txt not in label_lookup:
            label_lookup[txt] = pt

    already_matched_fps = {mp.fp_number for mp in matched_plots}

    # Build augmented segment list: DXF segments + boundary edges of
    # extracted polygons (closed LWPOLYLINEs become polygons in Tier 1
    # and their edges are NOT in dxf_segments — needed for subdivision).
    from shapely.geometry import LineString as _LS
    augmented_segments = list(dxf_segments)
    for poly in dxf_result.polygons:
        coords = list(poly.exterior.coords)
        for i in range(len(coords) - 1):
            edge = _LS([coords[i], coords[i + 1]])
            if edge.length > 1e-6:
                augmented_segments.append(edge)
    augmented_tree = STRtree(augmented_segments) if augmented_segments else None

    def _recover_polygon_for_label_point(
        label_point,
        *,
        local_min_area: float,
        target_area: float,
    ) -> Polygon | None:
        """
        Recover a missing thin/conface plot polygon by polygonizing only
        the subset of DXF segments near the label insertion point.
        """
        if not augmented_tree:
            return None

        # Try a small then a larger local window; thin polygons often need
        # a slightly larger context to close their boundary.
        radii = [max(10.0, snap_tolerance * 2.5), max(50.0, snap_tolerance * 5.0), 100.0, 150.0]
        for radius in radii:
            idxs = augmented_tree.query(label_point.buffer(radius))
            candidates = [
                augmented_segments[i]
                for i in idxs
                if label_point.distance(augmented_segments[i]) <= radius
            ]
            if not candidates:
                continue

            # Strategy 1: raw polygonize (exact coordinates)
            polys = [p for p in polygonize(candidates) if p.area >= local_min_area]

            if not polys:
                merged_local = unary_union(candidates)
                polys = [p for p in polygonize(merged_local) if p.area >= local_min_area]

            if not polys:
                merged_local = unary_union(candidates)
                full_polys, _dangles, _cuts, _invalids = polygonize_full(merged_local)
                raw = list(full_polys.geoms) if hasattr(full_polys, "geoms") else list(full_polys)
                polys = [p for p in raw if p.area >= local_min_area]

            # Strategy 2: integer-snap polygonize (closes tiny gaps)
            if not polys:
                from shapely.geometry import LineString as _LS
                snapped = []
                for seg in candidates:
                    coords = [(round(c[0]), round(c[1])) for c in seg.coords]
                    if len(set(coords)) >= 2:
                        snapped.append(_LS(coords))
                if snapped:
                    merged_snap = unary_union(snapped)
                    polys = [p for p in polygonize(merged_snap) if p.area >= local_min_area]

            if not polys:
                continue

            scored: list = []
            for p in polys:
                if p.area < local_min_area:
                    continue
                if not p.is_valid:
                    p = make_valid(p)
                    if not p.is_valid:
                        p = p.buffer(0)
                if not p.is_valid or p.area <= 0:
                    continue
                scored.append((abs(p.area - target_area), p.distance(label_point), p))

            if not scored:
                continue

            scored.sort(key=lambda t: (t[0], t[1]))
            best = scored[0][2]

            # Strategy 3: if best polygon is too small, find the
            # combination of touching polygons that best matches target area.
            if best.area < target_area * 0.7:
                # BFS to find all polygons reachable via touching
                reachable = [best]
                seen = {id(best)}
                queue = [best]
                while queue:
                    curr = queue.pop()
                    for p in polys:
                        if id(p) in seen or p.area < local_min_area:
                            continue
                        if curr.touches(p) or curr.distance(p) < 2:
                            seen.add(id(p))
                            reachable.append(p)
                            queue.append(p)

                # Brute-force best subset (must include best/main poly)
                if len(reachable) <= 12:
                    from itertools import combinations
                    best_diff = abs(best.area - target_area)
                    best_combo = [best]
                    for r in range(2, len(reachable) + 1):
                        for combo in combinations(range(1, len(reachable)), r - 1):
                            total = best.area + sum(reachable[i].area for i in combo)
                            diff = abs(total - target_area)
                            if diff < best_diff:
                                best_diff = diff
                                best_combo = [best] + [reachable[i] for i in combo]
                    if len(best_combo) > 1:
                        best = unary_union(best_combo)

            # If still >30% off target, try next (larger) radius
            if abs(best.area - target_area) / target_area > 0.30:
                continue

            return best

        return None

    # ── Step 3c: Recover unmatched numeric FPs via segment polygonization ──
    from tp_ingestion.services.geometry_matcher import MatchedPlot

    for fp_text in list(unmatched):
        if not _is_fp_number(fp_text):
            continue
        if fp_text in already_matched_fps:
            continue
        label_pt = label_lookup.get(fp_text)
        if label_pt is None:
            continue
        target_area = None
        if fp_text in fp_areas_map:
            target_area = min(fp_areas_map[fp_text])
        if target_area is None:
            continue

        recovered = _recover_polygon_for_label_point(
            label_pt,
            local_min_area=50.0,
            target_area=target_area,
        )
        if recovered is not None:
            matched_plots.append(
                MatchedPlot(
                    fp_number=fp_text,
                    polygon=recovered,
                    label_point=label_pt,
                    match_method="segment-recovery",
                )
            )
            already_matched_fps.add(fp_text)
            logger.info("Recovered FP %s via segment polygonization (area=%.0f)", fp_text, recovered.area)

    report.matched = len(matched_plots)

    # ── Step 4: Area validation + save ─────────────────────────────────────
    # Deduplicate: if a DXF has the same FP label on multiple entities
    # (e.g. a label placed on a block boundary shared by two plots), keep
    # only the first spatial match for each FP number.
    seen_fp: set[str] = set()
    unique_matched: List = []
    for mp in matched_plots:
        if mp.fp_number not in seen_fp:
            seen_fp.add(mp.fp_number)
            unique_matched.append(mp)
        else:
            logger.debug("Duplicate FP label '%s' skipped (keeping first match).", mp.fp_number)
    matched_plots = unique_matched

    plots_to_create: List[Plot] = []

    for mp in matched_plots:
        fp_num = mp.fp_number

        if fp_num not in fp_areas_map:
            logger.info("FP %s matched geometrically but not found in Excel — saving with geometry area.", fp_num)
            report.fp_numbers_not_in_excel.append(fp_num)
            area_excel = mp.polygon.area
        else:
            # When the same FP has multiple Excel rows (e.g. OP contributors), pick area closest to geometry
            areas = fp_areas_map[fp_num]
            area_excel = min(areas, key=lambda a: abs(a - mp.polygon.area))
        vr = validate_area(fp_num, mp.polygon, area_excel, tolerance=area_tolerance)

        if vr.is_valid:
            report.validated_ok += 1
        else:
            # Recovery strategy 1: segment-based polygonization near label
            recovered_polygon = None
            if hasattr(mp, "label_point") and mp.label_point:
                recovered_polygon = _recover_polygon_for_label_point(
                    mp.label_point,
                    local_min_area=50.0,
                    target_area=area_excel,
                )

            if recovered_polygon is not None:
                vr2 = validate_area(
                    fp_num, recovered_polygon, area_excel, tolerance=area_tolerance
                )
                if vr2.is_valid:
                    mp.polygon = recovered_polygon
                    vr = vr2
                    report.validated_ok += 1
                else:
                    recovered_polygon = None  # fall through to strategy 2

            # Recovery strategy 2: find a nearby extracted polygon that
            # directly matches the target area, or combine touching polygons.
            if recovered_polygon is None and hasattr(mp, "label_point") and mp.label_point:
                from itertools import combinations as _combinations
                lp = mp.label_point
                anchor = mp.polygon

                # 2a: Check if a nearby polygon (within 20 units of label) has the right area
                best_swap = None
                best_swap_err = abs(anchor.area - area_excel) / area_excel
                seen_swap = {tuple(round(b, 0) for b in anchor.bounds)}
                for epoly in dxf_result.polygons:
                    if epoly.area < 50:
                        continue
                    bkey = tuple(round(b, 0) for b in epoly.bounds)
                    if bkey in seen_swap:
                        continue
                    if lp.distance(epoly) > 20:
                        continue
                    err = abs(epoly.area - area_excel) / area_excel
                    if err < best_swap_err:
                        best_swap_err = err
                        best_swap = epoly
                        seen_swap.add(bkey)

                if best_swap is not None and best_swap_err <= area_tolerance:
                    vr_swap = validate_area(fp_num, best_swap, area_excel, tolerance=area_tolerance)
                    if vr_swap.is_valid:
                        mp.polygon = best_swap
                        vr = vr_swap
                        report.validated_ok += 1
                        recovered_polygon = best_swap

                # 2b: Combine touching polygons
                if recovered_polygon is None:
                    remaining_area = area_excel - anchor.area

                    direct_neighbors = []
                    seen_bounds = set()
                    anchor_bounds_key = tuple(round(b, 0) for b in anchor.bounds)
                    seen_bounds.add(anchor_bounds_key)

                    for epoly in dxf_result.polygons:
                        if epoly.area < 50 or epoly.area > remaining_area * 1.5:
                            continue
                        bkey = tuple(round(b, 0) for b in epoly.bounds)
                        if bkey in seen_bounds:
                            continue
                        if anchor.touches(epoly) or anchor.distance(epoly) < 2:
                            seen_bounds.add(bkey)
                            direct_neighbors.append(epoly)

                    if direct_neighbors and len(direct_neighbors) <= 20:
                        best_diff = abs(anchor.area - area_excel)
                        best_combo = [anchor]
                        max_r = min(len(direct_neighbors) + 1, 5)
                        for r in range(1, max_r):
                            for combo in _combinations(range(len(direct_neighbors)), r):
                                total = anchor.area + sum(direct_neighbors[i].area for i in combo)
                                diff = abs(total - area_excel)
                                if diff < best_diff:
                                    best_diff = diff
                                    best_combo = [anchor] + [direct_neighbors[i] for i in combo]
                        if len(best_combo) > 1:
                            merged_poly = unary_union(best_combo)
                            vr3 = validate_area(fp_num, merged_poly, area_excel, tolerance=area_tolerance)
                            if vr3.is_valid:
                                mp.polygon = merged_poly
                                vr = vr3
                                report.validated_ok += 1
                                recovered_polygon = merged_poly

            if recovered_polygon is None:
                report.validated_fail += 1
                if not save_invalid:
                    continue

        # Convert Shapely Polygon/MultiPolygon → Django GEOSPolygon (SRID=0)
        shapely_poly = mp.polygon
        if shapely_poly.geom_type == "MultiPolygon":
            # Try buffer trick to merge touching/near polygons into single Polygon
            merged = shapely_poly.buffer(0.5).buffer(-0.5)
            if merged.geom_type == "Polygon" and merged.area > 0:
                shapely_poly = merged
            elif merged.geom_type == "MultiPolygon":
                # Still multi — try larger buffer
                merged2 = shapely_poly.buffer(2.0).buffer(-2.0)
                if merged2.geom_type == "Polygon" and merged2.area > 0:
                    shapely_poly = merged2
                else:
                    # Last resort: use largest polygon from the collection
                    largest = max(shapely_poly.geoms, key=lambda g: g.area)
                    shapely_poly = largest
        exterior_coords = list(shapely_poly.exterior.coords)
        geos_poly = GEOSPolygon(exterior_coords, srid=0)
        
        # Compute optimal label placement point using representative_point
        label_pt = get_label_point(mp.polygon)
        geos_label_pt = GEOSPoint(label_pt.x, label_pt.y, srid=0)

        plots_to_create.append(
            Plot(
                city=city,
                tp_scheme=tp_scheme,
                fp_number=fp_num,
                area_excel=vr.area_excel,
                area_geometry=vr.area_geometry,
                geom=geos_poly,
                label_point=geos_label_pt,
                validation_status=vr.is_valid,
            )
        )

    if not dry_run:
        report.saved, report.updated, report.skipped_duplicates = _save_plots(
            plots_to_create, city, tp_scheme, update_existing=update_existing
        )
    else:
        logger.info("Dry-run mode — skipping database writes (%d records prepared).", len(plots_to_create))

    # ── Step 5: Optional BLOCK_NO overlay labels ──────────────────────────
    if include_block_labels and not dry_run:
        # Clean previous overlay labels for this site.
        BlockLabel.objects.filter(plot__city=city, plot__tp_scheme=tp_scheme).delete()

        # Load saved plot geometries once; mapping is done in-memory using
        # GEOS operations (strict contains → buffered contains → nearest).
        plots_qs = list(Plot.objects.filter(city=city, tp_scheme=tp_scheme).only("id", "geom"))

        # Note: dxf_result.block_labels is extracted from layer "BLOCK_NO"
        # independent of label_layers used for FP labels.
        block_labels_to_create: list[BlockLabel] = []
        buffered_contains_radius = 0.5
        nearest_threshold = max(1.5, snap_tolerance * 2.0)

        # Convert once: points are in DXF local coordinates (SRID=0).
        for text, pt in dxf_result.block_labels:
            label_point = GEOSPoint(pt.x, pt.y, srid=0)

            strict_hits = [
                p for p in plots_qs if p.geom is not None and p.geom.contains(label_point)
            ]
            if strict_hits:
                best = min(strict_hits, key=lambda p: label_point.distance(p.geom.centroid))
                block_labels_to_create.append(
                    BlockLabel(text=text, geom=label_point, plot=best)
                )
                continue

            buffered_hits = [
                p
                for p in plots_qs
                if p.geom is not None and p.geom.contains(label_point.buffer(buffered_contains_radius))
            ]
            if buffered_hits:
                best = min(
                    buffered_hits,
                    key=lambda p: label_point.distance(p.geom.centroid),
                )
                block_labels_to_create.append(
                    BlockLabel(text=text, geom=label_point, plot=best)
                )
                continue

            # Nearest fallback.
            best = None
            best_dist = float("inf")
            for p in plots_qs:
                dist = p.geom.distance(label_point)
                if dist < best_dist:
                    best_dist = dist
                    best = p
            if best is not None and best_dist <= nearest_threshold:
                block_labels_to_create.append(
                    BlockLabel(text=text, geom=label_point, plot=best)
                )
            else:
                block_labels_to_create.append(
                    BlockLabel(text=text, geom=label_point, plot=None)
                )

        if block_labels_to_create:
            BlockLabel.objects.bulk_create(block_labels_to_create, batch_size=500)

    report.print_summary()
    return report


def _save_plots(
    plots: List[Plot],
    city: str,
    tp_scheme: str,
    update_existing: bool = False,
) -> tuple[int, int, int]:
    """
    Create new Plot records and optionally update existing ones (geometry + area).
    Returns (saved_count, updated_count, skipped_count).
    """
    existing = {
        (p.fp_number, p.city, p.tp_scheme): p
        for p in Plot.objects.filter(city=city, tp_scheme=tp_scheme)
    }
    new_plots: List[Plot] = []
    to_update: List[Plot] = []

    for p in plots:
        key = (p.fp_number, city, tp_scheme)
        if key in existing:
            if update_existing:
                old = existing[key]
                old.geom = p.geom
                old.area_excel = p.area_excel
                old.area_geometry = p.area_geometry
                old.validation_status = p.validation_status
                to_update.append(old)
            # else: skip (duplicate)
        else:
            new_plots.append(p)

    if new_plots:
        Plot.objects.bulk_create(new_plots, batch_size=500)
    if to_update:
        # Recompute label_point for updated plots
        for p in to_update:
            from shapely.geometry import Polygon as ShapelyPolygon
            coords = [(pt[0], pt[1]) for pt in p.geom.coords[0]]
            shapely_poly = ShapelyPolygon(coords)
            label_pt = get_label_point(shapely_poly)
            p.label_point = GEOSPoint(label_pt.x, label_pt.y, srid=0)
        
        Plot.objects.bulk_update(
            to_update,
            ["geom", "area_excel", "area_geometry", "validation_status", "label_point"],
            batch_size=500,
        )

    skipped = len(plots) - len(new_plots) - len(to_update)
    logger.info(
        "Saved %d new, updated %d existing, skipped %d.",
        len(new_plots),
        len(to_update),
        skipped,
    )
    return len(new_plots), len(to_update), skipped
