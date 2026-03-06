"""
architecture.engines.placement_zone_engine
------------------------------------------
Splits buildable envelope into candidate zones for tower placement.

Responsibilities:
  - Split envelope into polygon islands (after COP and road corridor subtraction)
  - Filter zones by minimum tower size (area)
  - Rank zones by area (largest first)

Used before tower placement so placement runs per zone or over ranked zones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from shapely.geometry import Polygon

logger = logging.getLogger(__name__)

# Minimum zone area to consider for tower placement (~20 sq.m in sq.ft)
DEFAULT_MIN_ZONE_AREA_SQFT = 215.0


@dataclass
class PlacementZoneResult:
    """Result of placement zone generation."""
    status: str  # "VALID" | "NO_ZONES" | "ERROR"
    candidate_zones: List[Polygon] = field(default_factory=list)
    min_zone_area_sqft: float = DEFAULT_MIN_ZONE_AREA_SQFT
    error_message: str = ""


def generate_placement_zones(
    envelope_polygon: Polygon,
    *,
    min_zone_area_sqft: float = DEFAULT_MIN_ZONE_AREA_SQFT,
) -> PlacementZoneResult:
    """
    Split envelope into candidate zones for tower placement.

    Steps:
      1. If envelope is MultiPolygon, take each component; else single polygon → one zone.
      2. Filter: keep only zones with area >= min_zone_area_sqft.
      3. Rank by area descending (largest first).

    Parameters
    ----------
    envelope_polygon : buildable envelope (after COP and road subtraction), DXF feet
    min_zone_area_sqft : minimum zone area to consider (default ~215 sq.ft)

    Returns
    -------
    PlacementZoneResult with candidate_zones (list of Shapely Polygon), ranked by area.
    """
    result = PlacementZoneResult(
        status="ERROR",
        min_zone_area_sqft=min_zone_area_sqft,
    )
    if envelope_polygon is None or envelope_polygon.is_empty:
        result.error_message = "Envelope is empty"
        return result
    if not envelope_polygon.is_valid:
        try:
            envelope_polygon = envelope_polygon.buffer(0)
            if envelope_polygon.is_empty or not envelope_polygon.is_valid:
                result.error_message = "Envelope could not be repaired"
                return result
        except Exception as e:
            result.error_message = str(e)
            return result

    zones: List[Polygon] = []
    if hasattr(envelope_polygon, "geoms"):
        zones = [g for g in envelope_polygon.geoms if isinstance(g, Polygon) and not g.is_empty and g.is_valid]
    else:
        zones = [envelope_polygon]

    filtered = [z for z in zones if z.area >= min_zone_area_sqft]
    filtered.sort(key=lambda p: p.area, reverse=True)
    result.candidate_zones = filtered
    result.status = "VALID" if filtered else "NO_ZONES"
    result.error_message = "" if filtered else "No zones meet minimum area"
    logger.info(
        "Placement zones: %d candidate(s) (min area %.0f sq.ft), total area %.0f sq.ft.",
        len(filtered),
        min_zone_area_sqft,
        sum(z.area for z in filtered),
    )
    return result
