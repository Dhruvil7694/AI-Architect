"""
architecture.feasibility.buildability_metrics
---------------------------------------------

Aggregates buildability scalars from envelope, placement, core validation,
and (optionally) floor skeleton. Does not run any pipeline; consumes
existing results only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from common.units import sqft_to_sqm


@dataclass
class BuildabilityMetrics:
    """Buildability-related scalars for feasibility reporting."""

    # From envelope
    envelope_area_sqft: float
    envelope_area_sqm: float

    # From placement (first footprint)
    footprint_width_m: float
    footprint_depth_m: float
    footprint_area_sqft: float

    # From core validation (first tower)
    core_area_sqm: float
    remaining_usable_sqm: float

    # From skeleton (optional; 0/0.0 if skeleton not run)
    efficiency_ratio: float
    core_ratio: float
    circulation_ratio: float


def build_buildability_metrics(
    *,
    envelope_area_sqft: float,
    footprint_width_m: float,
    footprint_depth_m: float,
    footprint_area_sqft: float,
    core_area_sqm: float,
    remaining_usable_sqm: float,
    efficiency_ratio: Optional[float] = None,
    core_ratio: Optional[float] = None,
    circulation_ratio: Optional[float] = None,
) -> BuildabilityMetrics:
    """Build BuildabilityMetrics from pipeline outputs (no heavy computation)."""
    return BuildabilityMetrics(
        envelope_area_sqft=envelope_area_sqft,
        envelope_area_sqm=sqft_to_sqm(envelope_area_sqft),
        footprint_width_m=footprint_width_m,
        footprint_depth_m=footprint_depth_m,
        footprint_area_sqft=footprint_area_sqft,
        core_area_sqm=core_area_sqm,
        remaining_usable_sqm=remaining_usable_sqm,
        efficiency_ratio=efficiency_ratio if efficiency_ratio is not None else 0.0,
        core_ratio=core_ratio if core_ratio is not None else 0.0,
        circulation_ratio=circulation_ratio if circulation_ratio is not None else 0.0,
    )
