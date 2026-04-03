"""
placement_engine/geometry/fire_loop.py
--------------------------------------
Carves a continuous fire-tender access loop inside the buildable envelope.

GDCR Reference
--------------
GDCR.yaml → residential_norms.site_planning.min_fire_tender_access_m: 4.5
NBC fire-tender movement clearance: 4.5 m minimum width.

The fire loop is an annular ring between the envelope boundary and an inset
boundary.  It is "sacred space" — no tower footprint may overlap it.  The
remaining interior (`buildable_core`) is where towers and COP are placed.

For non-highrise buildings (height < 15 m), the fire access width can be
relaxed to `min_pedestrian_path_m` (1.8 m) when the full 4.5 m width causes
the buildable core to collapse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from placement_engine.geometry import METRES_TO_DXF, DXF_TO_METRES
from rules_engine.rules.loader import get_gdcr_config

logger = logging.getLogger(__name__)

# ── GDCR config helpers ──────────────────────────────────────────────────────


def _get_fire_tender_width_m() -> float:
    """Return the fire-tender access width in metres from GDCR.yaml."""
    try:
        gdcr = get_gdcr_config()
        norms = gdcr.get("residential_norms", {})
        site = norms.get("site_planning", {}) if norms else {}
        return float(site.get("min_fire_tender_access_m", 4.5))
    except Exception:
        return 4.5


def _get_pedestrian_path_width_m() -> float:
    """Fallback reduced width for non-highrise buildings."""
    try:
        gdcr = get_gdcr_config()
        norms = gdcr.get("residential_norms", {})
        site = norms.get("site_planning", {}) if norms else {}
        return float(site.get("min_pedestrian_path_m", 1.8))
    except Exception:
        return 1.8


# ── Dataclass ─────────────────────────────────────────────────────────────────


@dataclass
class FireLoopResult:
    """Result of carving the fire-tender access loop."""

    fire_loop_polygon: Optional[Polygon]  # annular ring (sacred space)
    buildable_core: Optional[Polygon]     # envelope minus fire loop
    fire_tender_width_m: float            # actual width used
    fire_tender_width_dxf: float
    is_continuous: bool                   # True if loop forms a complete ring
    core_area_sqft: float
    loop_area_sqft: float
    status: str                           # "CARVED" | "COLLAPSED" | "SKIPPED"


# ── Core functions ────────────────────────────────────────────────────────────


def _largest_polygon(geom) -> Optional[Polygon]:
    """Extract the largest Polygon from a geometry (handles MultiPolygon)."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        polys = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        return max(polys, key=lambda p: p.area) if polys else None
    return None


def carve_fire_loop(
    envelope: Polygon,
    fire_width_m: Optional[float] = None,
    building_height_m: float = 0.0,
) -> FireLoopResult:
    """
    Inset the buildable envelope by `fire_width_m` to create a continuous
    perimeter access ring.

    Parameters
    ----------
    envelope          : Legal buildable envelope polygon (DXF feet, SRID=0).
    fire_width_m      : Fire-tender access width in metres.
                        None → read from GDCR.yaml (default 4.5 m).
    building_height_m : Building height in metres — used to decide whether
                        reduced width is acceptable for non-highrise.

    Returns
    -------
    FireLoopResult with the annular fire loop and the remaining buildable core.
    """
    if fire_width_m is None:
        fire_width_m = _get_fire_tender_width_m()

    fire_width_dxf = fire_width_m * METRES_TO_DXF

    # Negative buffer = inset (shrink inward)
    core_raw = envelope.buffer(-fire_width_dxf)
    core = _largest_polygon(core_raw)

    # If the core collapsed, try reduced width for non-highrise
    if (core is None or core.is_empty) and building_height_m < 15.0:
        reduced_m = _get_pedestrian_path_width_m()
        reduced_dxf = reduced_m * METRES_TO_DXF
        core_raw = envelope.buffer(-reduced_dxf)
        core = _largest_polygon(core_raw)

        if core is not None and not core.is_empty:
            logger.info(
                "Fire loop at %.1fm collapsed core; reduced to %.1fm for non-highrise.",
                fire_width_m, reduced_m,
            )
            fire_width_m = reduced_m
            fire_width_dxf = reduced_dxf
        else:
            logger.warning(
                "Fire loop carve collapsed even at reduced %.1fm — skipping.",
                reduced_m,
            )
            return FireLoopResult(
                fire_loop_polygon=None,
                buildable_core=envelope,
                fire_tender_width_m=0.0,
                fire_tender_width_dxf=0.0,
                is_continuous=False,
                core_area_sqft=envelope.area,
                loop_area_sqft=0.0,
                status="COLLAPSED",
            )
    elif core is None or core.is_empty:
        logger.warning(
            "Fire loop carve at %.1fm collapsed core for highrise (%.1fm) — COLLAPSED.",
            fire_width_m, building_height_m,
        )
        return FireLoopResult(
            fire_loop_polygon=None,
            buildable_core=None,
            fire_tender_width_m=fire_width_m,
            fire_tender_width_dxf=fire_width_dxf,
            is_continuous=False,
            core_area_sqft=0.0,
            loop_area_sqft=0.0,
            status="COLLAPSED",
        )

    # Fire loop = annular ring between envelope and core
    fire_loop = envelope.difference(core)
    fire_loop_poly = _largest_polygon(fire_loop) if isinstance(fire_loop, MultiPolygon) else fire_loop

    # Continuity check: the fire loop should be a single connected ring.
    # If the inset produced a clean single polygon core, the ring is continuous.
    is_continuous = isinstance(core_raw, Polygon) and not core_raw.is_empty

    core_area = core.area if core else 0.0
    loop_area = fire_loop.area if fire_loop and not fire_loop.is_empty else 0.0

    logger.info(
        "Fire loop carved: width=%.1fm (%.1f dxf), core=%.0f sqft, loop=%.0f sqft, "
        "continuous=%s",
        fire_width_m, fire_width_dxf, core_area, loop_area, is_continuous,
    )

    return FireLoopResult(
        fire_loop_polygon=fire_loop_poly,
        buildable_core=core,
        fire_tender_width_m=fire_width_m,
        fire_tender_width_dxf=fire_width_dxf,
        is_continuous=is_continuous,
        core_area_sqft=core_area,
        loop_area_sqft=loop_area,
        status="CARVED",
    )


def validate_fire_loop_intact(
    fire_loop: Optional[Polygon],
    tower_footprints: List[Polygon],
    tolerance_sqft: float = 1.0,
) -> bool:
    """
    Post-placement hard check: verify no tower intrudes into the fire loop.

    Returns True if the fire loop is intact (no tower overlaps it).
    A small tolerance (default 1 sqft) is allowed for floating-point edge cases.
    """
    if fire_loop is None or fire_loop.is_empty:
        return True  # no fire loop to violate

    if not tower_footprints:
        return True

    tower_union = unary_union(tower_footprints)
    overlap = fire_loop.intersection(tower_union)

    if overlap.is_empty:
        return True

    overlap_area = overlap.area
    if overlap_area <= tolerance_sqft:
        return True

    logger.warning(
        "Fire loop intrusion detected: %.1f sqft overlap (tolerance=%.1f sqft).",
        overlap_area, tolerance_sqft,
    )
    return False
