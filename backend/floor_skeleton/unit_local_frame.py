"""
floor_skeleton/unit_local_frame.py
----------------------------------
Deterministic per-band spatial abstraction for Phase 1.5.

UnitLocalFrame is frozen (immutable). Axis vectors are aligned with the
footprint coordinate frame only; rotated footprints are not supported in Phase 1.5.
Origin is purely geometric (min corner of zone bounds), not functional—Phase 2
must not assume semantic meaning (e.g. core-facing corner or repeat-start corner).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UnitLocalFrame:
    """
    Deterministic local frame for one unit band.

    origin: Purely geometric—min corner of zone bounds. Not functional;
        Phase 2 must not assume it is core-facing or repeat-start corner.
    repeat_axis, depth_axis: Normalized direction vectors. Aligned with
        footprint coordinate frame only; rotated footprints not supported in Phase 1.5.
    core_facing_edge, corridor_facing_edge: Longest shared segment (start, end),
        normalized for stable ordering; None if no shared boundary or length < tol.
        Both may be non-None when the band touches both core and corridor (geometry
        reflects real adjacency; Phase 2 applies semantic use e.g. wet-wall vs entry).
    """

    band_id: int
    origin: tuple[float, float]
    repeat_axis: tuple[float, float]
    depth_axis: tuple[float, float]
    band_length_m: float
    band_depth_m: float
    core_facing_edge: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
    corridor_facing_edge: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
