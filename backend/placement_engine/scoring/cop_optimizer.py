"""
placement_engine/scoring/cop_optimizer.py
------------------------------------------
Post-placement COP (Common Open Plot) region optimizer.

After towers are placed, this module locates the largest connected leftover
polygon (envelope minus tower exclusion zones) and inscribes a compliant
COP rectangle inside it.

This is a fully ADDITIVE layer — it never modifies the COP already carved by
the envelope engine.  The result is exposed as an extra GeoJSON debug feature
(layer: "optimized_cop") in the development pipeline output so it can be
visualised alongside the existing carved COP.

Algorithm (Step 7)
------------------
1. leftover = envelope.difference(union of all H/3 exclusion zones)
2. Extract connected components of leftover (descending area).
3. For each component, inscribe the maximum rectangle with:
       width >= min_dimension_m  AND  depth >= min_dimension_m
       area  >= required_cop_area_sqft
4. Return the first valid COP found (largest-component-first order).

GDCR reference: common_open_plot.geometry_constraints.minimum_dimension_m = 6 m
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from shapely.geometry import Polygon
from shapely.ops import unary_union

from placement_engine.geometry import (
    DXF_TO_METRES,
    METRES_TO_DXF,
    FootprintCandidate,
)
from placement_engine.geometry.multipolygon_handler import extract_components
from placement_engine.geometry.inscribed_rectangle import find_best_inscribed_rect
from placement_engine.geometry.spacing_enforcer import compute_exclusion_zone

logger = logging.getLogger(__name__)

# GDCR minimum COP dimension (metres) — also checked in envelope engine
COP_MIN_DIMENSION_M: float = 6.0


@dataclass
class CopOptimizationResult:
    """Result of the post-placement COP optimization attempt."""

    found: bool
    cop_polygon: Optional[object]   # Shapely Polygon or None
    area_sqft: float
    min_dimension_m: float
    component_index: int            # 0-based rank of leftover component used
    note: str                       # human-readable explanation for debug/logging


# ── Public API ─────────────────────────────────────────────────────────────────

def find_optimized_cop(
    envelope: Polygon,
    placed_footprints: List[Polygon],
    building_height_m: float,
    required_cop_area_sqft: float,
    min_dimension_m: float = COP_MIN_DIMENSION_M,
) -> CopOptimizationResult:
    """
    Find the optimal COP placement in leftover space after tower placement.

    Parameters
    ----------
    envelope               : Buildable envelope polygon (DXF feet, SRID=0).
    placed_footprints      : Placed tower footprint polygons (DXF feet).
    building_height_m      : Tower height in metres — drives H/3 exclusion zone.
    required_cop_area_sqft : Minimum COP area (sq.ft) that must be satisfied.
    min_dimension_m        : Minimum COP side length in metres (default 6 m).

    Returns
    -------
    CopOptimizationResult — always returned; check `.found` to test success.
    """

    def _fail(note: str) -> CopOptimizationResult:
        return CopOptimizationResult(
            found=False, cop_polygon=None, area_sqft=0.0,
            min_dimension_m=0.0, component_index=-1, note=note,
        )

    if not placed_footprints:
        return _fail("No towers placed — cannot derive leftover for COP")

    # ── Step 1: Compute leftover polygon ──────────────────────────────────────
    try:
        exclusion_zones = [
            compute_exclusion_zone(fp, building_height_m)
            for fp in placed_footprints
        ]
        leftover = envelope.difference(unary_union(exclusion_zones))
    except Exception as exc:        # noqa: BLE001
        return _fail(f"Geometry error computing leftover: {exc}")

    if leftover is None or leftover.is_empty:
        return _fail("No leftover space remains after tower exclusion zones")

    logger.debug(
        "[CopOptimizer] leftover area=%.0f sqft (required COP=%.0f sqft)",
        leftover.area, required_cop_area_sqft,
    )

    # ── Step 2: Extract connected components (largest first) ──────────────────
    # Allow components slightly below required area — the inscribed rect may
    # still fit once the component shape is evaluated.
    min_component_sqft = max(required_cop_area_sqft * 0.5, 1.0)
    components = extract_components(leftover, min_area_sqft=min_component_sqft)

    if not components:
        return _fail(
            f"All leftover components are too small "
            f"(< {min_component_sqft:.0f} sqft) for COP"
        )

    # ── Step 3: Inscribe COP rectangle in each component ─────────────────────
    min_dim_dxf = min_dimension_m * METRES_TO_DXF

    for idx, component in enumerate(components):
        candidate = find_best_inscribed_rect(
            polygon=component,
            min_width_dxf=min_dim_dxf,
            min_depth_dxf=min_dim_dxf,
        )
        if candidate is None:
            logger.debug(
                "[CopOptimizer] component %d (%.0f sqft): no inscribed rect found",
                idx, component.area,
            )
            continue

        # Validate area requirement
        if candidate.area_sqft < required_cop_area_sqft:
            logger.debug(
                "[CopOptimizer] component %d: area %.0f < required %.0f sqft — skip",
                idx, candidate.area_sqft, required_cop_area_sqft,
            )
            continue

        # Validate minimum dimension (both sides >= min_dimension_m)
        actual_min_m = min(candidate.width_m, candidate.depth_m)
        if actual_min_m < min_dimension_m - 1e-4:
            logger.debug(
                "[CopOptimizer] component %d: min_dim %.2f m < %.1f m — skip",
                idx, actual_min_m, min_dimension_m,
            )
            continue

        logger.debug(
            "[CopOptimizer] COP found in component %d: "
            "area=%.0f sqft, min_dim=%.2f m, width=%.2f m, depth=%.2f m",
            idx, candidate.area_sqft, actual_min_m,
            candidate.width_m, candidate.depth_m,
        )

        return CopOptimizationResult(
            found=True,
            cop_polygon=candidate.footprint_polygon,
            area_sqft=round(candidate.area_sqft, 2),
            min_dimension_m=round(actual_min_m, 3),
            component_index=idx,
            note=(
                f"Inscribed in leftover component {idx} "
                f"(area rank); area={candidate.area_sqft:.0f} sqft, "
                f"min_dim={actual_min_m:.2f} m"
            ),
        )

    return _fail(
        f"No leftover component satisfies COP constraints "
        f"(required: {required_cop_area_sqft:.0f} sqft, "
        f"min_dim: {min_dimension_m:.1f} m) "
        f"across {len(components)} component(s)"
    )
