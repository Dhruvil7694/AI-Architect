"""
residential_layout/frames.py — Phase 2 frame adapter.

Extends UnitLocalFrame with band_axis, frontage_edge, wet_wall_line.
Uses zone geometry only; no placement_label or skeleton internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, List

from shapely.geometry import Polygon

from floor_skeleton.frame_deriver import derive_local_frame
from floor_skeleton.models import FloorSkeleton, UnitZone
from floor_skeleton.unit_local_frame import UnitLocalFrame

_COORD_ROUND = 6
_TOL = 1e-6


def _normalize_seg(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Lexicographic (start, end) for segment identity."""
    a = (round(p1[0], _COORD_ROUND), round(p1[1], _COORD_ROUND))
    b = (round(p2[0], _COORD_ROUND), round(p2[1], _COORD_ROUND))
    return (a, b) if a <= b else (b, a)


def _zone_boundary_segments(poly: Polygon) -> List[tuple[tuple[float, float], tuple[float, float]]]:
    """Ordered list of normalized (start, end) segments of poly.exterior."""
    if poly is None or poly.is_empty or not poly.exterior:
        return []
    coords = list(poly.exterior.coords)
    if len(coords) < 2:
        return []
    out = []
    for i in range(len(coords) - 1):
        seg = _normalize_seg(
            (coords[i][0], coords[i][1]),
            (coords[i + 1][0], coords[i + 1][1]),
        )
        if seg[0] != seg[1]:
            out.append(seg)
    return out


def _segment_eq(
    a: tuple[tuple[float, float], tuple[float, float]],
    b: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    if a is None or b is None:
        return a is b
    return (
        abs(a[0][0] - b[0][0]) < _TOL and abs(a[0][1] - b[0][1]) < _TOL
        and abs(a[1][0] - b[1][0]) < _TOL and abs(a[1][1] - b[1][1]) < _TOL
    )


@dataclass
class ComposerFrame:
    """
    Phase 2 frame: UnitLocalFrame + band_axis, frontage_edge, wet_wall_line.

    band_axis: "X" | "Y" from repeat_axis.
    frontage_edge: Zone boundary edge opposite core (entry side for END_CORE).
    wet_wall_line: ("x", k) or ("y", k) — axis-aligned line through core edge.
    core_edge: Same as frame.core_facing_edge.
    corridor_edge: Same as frame.corridor_facing_edge; None for END_CORE.
    """

    frame: UnitLocalFrame
    band_axis: str  # "X" | "Y"
    frontage_edge: tuple[tuple[float, float], tuple[float, float]]
    wet_wall_line: tuple[str, float]  # ("x", k) or ("y", k)
    core_edge: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
    corridor_edge: Optional[tuple[tuple[float, float], tuple[float, float]]] = None

    @property
    def origin(self) -> tuple[float, float]:
        return self.frame.origin

    @property
    def repeat_axis(self) -> tuple[float, float]:
        return self.frame.repeat_axis

    @property
    def depth_axis(self) -> tuple[float, float]:
        return self.frame.depth_axis

    @property
    def band_length_m(self) -> float:
        return self.frame.band_length_m

    @property
    def band_depth_m(self) -> float:
        return self.frame.band_depth_m

    @property
    def band_id(self) -> int:
        return self.frame.band_id


def derive_unit_local_frame(
    skeleton: FloorSkeleton,
    zone_index: int,
) -> ComposerFrame:
    """
    Derive Phase 2 ComposerFrame for skeleton.unit_zones[zone_index].

    Calls frame_deriver.derive_local_frame, then adds band_axis,
    frontage_edge, wet_wall_line. END_CORE: corridor_edge is None;
    entry uses frontage_edge.
    """
    zone = skeleton.unit_zones[zone_index]
    frame = derive_local_frame(skeleton, zone)

    # band_axis from repeat_axis
    rx, ry = frame.repeat_axis[0], frame.repeat_axis[1]
    if abs(rx) >= abs(ry):
        band_axis = "X"
    else:
        band_axis = "Y"

    # core_edge
    core_edge = frame.core_facing_edge
    corridor_edge = frame.corridor_facing_edge

    # frontage_edge: zone boundary edge opposite to core
    segments = _zone_boundary_segments(zone.polygon)
    frontage_edge = (frame.origin, frame.origin)  # fallback
    if core_edge is not None and len(segments) >= 2:
        for i, seg in enumerate(segments):
            if _segment_eq(seg, core_edge):
                # Opposite edge in a quadrilateral
                idx_opp = (i + 2) % len(segments)
                frontage_edge = segments[idx_opp]
                break
    elif len(segments) >= 1:
        # No core edge (e.g. no core polygon); use longest as frontage
        frontage_edge = max(segments, key=lambda s: (s[1][0] - s[0][0]) ** 2 + (s[1][1] - s[0][1]) ** 2)

    # wet_wall_line: axis-aligned line at depth=0 in local (back strip backs on this).
    # Depth 0 runs through origin along band (repeat) direction.
    if band_axis == "X":
        # repeat along X → depth=0 line is y = origin[1]
        wet_wall_line = ("y", frame.origin[1])
    else:
        # repeat along Y → depth=0 line is x = origin[0]
        wet_wall_line = ("x", frame.origin[0])

    return ComposerFrame(
        frame=frame,
        band_axis=band_axis,
        frontage_edge=frontage_edge,
        wet_wall_line=wet_wall_line,
        core_edge=core_edge,
        corridor_edge=corridor_edge,
    )
