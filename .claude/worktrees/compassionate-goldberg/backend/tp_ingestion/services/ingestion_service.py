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

from django.contrib.gis.geos import Polygon as GEOSPolygon

from tp_ingestion.models import Plot
from tp_ingestion.services.area_validator import validate_area, DEFAULT_TOLERANCE
from tp_ingestion.services.dxf_reader import read_dxf
from tp_ingestion.services.excel_reader import read_excel_all_areas
from tp_ingestion.services.geometry_matcher import match_fp_to_polygons

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
    dxf_result = read_dxf(dxf_path, polygon_layers=polygon_layers, label_layers=label_layers)
    report.total_polygons = len(dxf_result.polygons)
    report.total_labels = len(dxf_result.labels)

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
            logger.warning("FP %s matched geometrically but not found in Excel — skipping.", fp_num)
            report.fp_numbers_not_in_excel.append(fp_num)
            continue

        # When the same FP has multiple Excel rows (e.g. OP contributors), pick area closest to geometry
        areas = fp_areas_map[fp_num]
        area_excel = min(areas, key=lambda a: abs(a - mp.polygon.area))
        vr = validate_area(fp_num, mp.polygon, area_excel, tolerance=area_tolerance)

        if vr.is_valid:
            report.validated_ok += 1
        else:
            report.validated_fail += 1
            if not save_invalid:
                continue

        # Convert Shapely Polygon → Django GEOSPolygon (SRID=0)
        exterior_coords = list(mp.polygon.exterior.coords)
        geos_poly = GEOSPolygon(exterior_coords, srid=0)

        plots_to_create.append(
            Plot(
                city=city,
                tp_scheme=tp_scheme,
                fp_number=fp_num,
                area_excel=vr.area_excel,
                area_geometry=vr.area_geometry,
                geom=geos_poly,
                validation_status=vr.is_valid,
            )
        )

    if not dry_run:
        report.saved, report.updated, report.skipped_duplicates = _save_plots(
            plots_to_create, city, tp_scheme, update_existing=update_existing
        )
    else:
        logger.info("Dry-run mode — skipping database writes (%d records prepared).", len(plots_to_create))

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
        Plot.objects.bulk_update(
            to_update,
            ["geom", "area_excel", "area_geometry", "validation_status"],
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
