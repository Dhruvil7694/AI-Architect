"""
placement_engine/geometry/multipolygon_handler.py
--------------------------------------------------
After subtracting an exclusion zone from the remaining envelope, the result
may be a MultiPolygon.  This module:

  1. Extracts valid polygon components from any geometry type.
  2. Filters out slivers below MIN_FOOTPRINT_AREA_SQFT.
  3. Orders components deterministically: descending area, then ascending
     centroid.x as a tie-break.
  4. Caps the list at MAX_COMPONENTS to bound evaluation cost.
  5. Evaluates each component with find_best_inscribed_rect and returns the
     best FootprintCandidate across all components.

Determinism guarantee
---------------------
Sorting by (-area, centroid.x) is fully reproducible for fixed geometry.
Same input geometry → same component ordering → same candidate selection.
"""

from __future__ import annotations

from typing import Optional

from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry

from placement_engine.geometry import (
    MAX_COMPONENTS,
    MIN_FOOTPRINT_AREA_SQFT,
    FootprintCandidate,
)
from placement_engine.geometry.inscribed_rectangle import (
    find_best_inscribed_rect,
    find_top_n_inscribed_rects,
)


def extract_components(
    geom: BaseGeometry,
    min_area_sqft: float = MIN_FOOTPRINT_AREA_SQFT,
) -> list[Polygon]:
    """
    Return an ordered list of Polygon components from *geom*.

    Ordering: descending area, ascending centroid.x for ties.
    Components with area < *min_area_sqft* are discarded as slivers.
    Result is capped at MAX_COMPONENTS.

    Parameters
    ----------
    geom          : Any Shapely geometry (Polygon, MultiPolygon, or other).
    min_area_sqft : Lower area bound; slivers below this are discarded.

    Returns
    -------
    List of at most MAX_COMPONENTS Polygon objects.
    """
    if geom is None or geom.is_empty:
        return []

    if isinstance(geom, Polygon):
        raw = [geom]
    elif isinstance(geom, MultiPolygon):
        raw = list(geom.geoms)
    else:
        # GeometryCollection or other — collect Polygon sub-parts
        raw = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]

    # Filter slivers
    valid = [g for g in raw if g.is_valid and not g.is_empty and g.area >= min_area_sqft]

    # Deterministic ordering: descending area, ascending centroid.x
    valid.sort(key=lambda g: (-g.area, g.centroid.x))

    return valid[:MAX_COMPONENTS]


def find_top_n_in_components(
    geom:          BaseGeometry,
    min_width_dxf: float,
    min_depth_dxf: float,
    force_angle:   Optional[float] = None,
    min_area_sqft: float = MIN_FOOTPRINT_AREA_SQFT,
    n:             int = 10,
) -> list[FootprintCandidate]:
    """
    Return up to *n* candidates across all valid components, sorted by area.

    Each component is evaluated with find_top_n_inscribed_rects.  All
    candidates from all components are pooled, sorted by area descending, and
    the top-N returned.  The scoring layer (placement_scorer.select_best_candidate)
    then applies heuristic ranking to choose the architecturally best one.

    Parameters
    ----------
    geom          : Any Shapely geometry (Polygon, MultiPolygon, or collection).
    min_width_dxf : Minimum footprint width (DXF feet).
    min_depth_dxf : Minimum footprint depth (DXF feet).
    force_angle   : If given, only test this angle per component.
    min_area_sqft : Sliver filter threshold.
    n             : Maximum candidates to return.

    Returns
    -------
    List of FootprintCandidate sorted by area descending, capped at *n*.
    """
    components = extract_components(geom, min_area_sqft)
    if not components:
        return []

    all_candidates: list[FootprintCandidate] = []
    for idx, component in enumerate(components):
        for c in find_top_n_inscribed_rects(
            polygon=component,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            n=n,
            force_angle=force_angle,
        ):
            c.source_component_index = idx
            all_candidates.append(c)

    all_candidates.sort(key=lambda c: -c.area_sqft)
    return all_candidates[:n]


def find_best_in_components(
    geom:          BaseGeometry,
    min_width_dxf: float,
    min_depth_dxf: float,
    force_angle:   Optional[float] = None,
    min_area_sqft: float = MIN_FOOTPRINT_AREA_SQFT,
) -> Optional[FootprintCandidate]:
    """
    Evaluate all valid components of *geom* and return the FootprintCandidate
    with the largest footprint area.

    The source_component_index on the winning candidate records which component
    it came from (0-based, in the ordering returned by extract_components).

    Parameters
    ----------
    geom          : Any Shapely geometry (result of envelope.difference(...)).
    min_width_dxf : Minimum footprint width (DXF feet).
    min_depth_dxf : Minimum footprint depth (DXF feet).
    force_angle   : If given, pass to find_best_inscribed_rect (COL_WISE mode).
    min_area_sqft : Sliver filter threshold.

    Returns
    -------
    Best FootprintCandidate across all components, or None if no component fits.
    """
    components = extract_components(geom, min_area_sqft)
    if not components:
        return None

    best: Optional[FootprintCandidate] = None

    for idx, component in enumerate(components):
        candidate = find_best_inscribed_rect(
            polygon=component,
            min_width_dxf=min_width_dxf,
            min_depth_dxf=min_depth_dxf,
            force_angle=force_angle,
        )
        if candidate is None:
            continue

        candidate.source_component_index = idx

        if best is None or candidate.area_sqft > best.area_sqft:
            best = candidate

    return best
