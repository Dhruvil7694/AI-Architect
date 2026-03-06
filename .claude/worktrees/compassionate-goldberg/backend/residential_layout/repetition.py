"""
residential_layout/repetition.py — Phase 3 Band Repetition Engine.

Deterministic slice count (N), translation-only slice frames, one resolve_unit_layout
per slice, BandLayoutContract output. No Phase 2 or template changes. No skeleton coupling.

Architectural invariant (Phase 3 assumption):
  The parent band zone is RECTANGULAR in the local (band, depth) frame. Slice zones
  are built as rectangles [slice_start, slice_end] × [0, band_depth_m] in that frame.
  If the skeleton ever produces a non-rectangular band (e.g. L-shaped or tapered zone),
  this repetition engine breaks: slice boundaries and corridor clipping assume a
  rectangular band. Callers must ensure band zones are rectangular.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from shapely.geometry import Polygon

from floor_skeleton.models import UnitZone
from floor_skeleton.unit_local_frame import UnitLocalFrame

from residential_layout.errors import UnresolvedLayoutError
from residential_layout.frames import ComposerFrame
from residential_layout.models import UnitLayoutContract
from residential_layout.orchestrator import resolve_unit_layout

# ── Constants (plan Section 3) ───────────────────────────────────────────────────

MIN_RESIDUAL_M = 0.4
DEFAULT_MODULE_WIDTH_M = 3.6
MAX_UNITS_PER_BAND = 64
_TOL = 1e-6


# ── Exceptions ──────────────────────────────────────────────────────────────────

class BandRepetitionError(Exception):
    """Raised when any slice raises UnresolvedLayoutError. No partial BandLayoutContract."""

    def __init__(
        self,
        message: str,
        band_id: int,
        slice_index: int,
        cause: Optional[UnresolvedLayoutError] = None,
    ):
        super().__init__(message)
        self.band_id = band_id
        self.slice_index = slice_index
        self.cause = cause


class BandRepetitionValidationError(Exception):
    """Raised when post-loop validation fails (slice boundary, containment, width)."""

    def __init__(self, message: str, reason: Optional[str] = None):
        super().__init__(message)
        self.reason = reason


# ── Output contract ─────────────────────────────────────────────────────────────

@dataclass
class BandLayoutContract:
    """Phase 3 output: one band, N units, residual and band length."""

    band_id: int
    units: List[UnitLayoutContract]
    n_units: int
    residual_width_m: float
    band_length_m: float


# ── N and residual (plan Section 4, Option B, hard cap) ──────────────────────────

def _compute_n_and_residual(
    band_length_m: float,
    module_width_m: float,
) -> tuple[int, float]:
    """
    Deterministic N and residual. Option B: residual reduction only when N_raw >= 2.
    Hard cap at MAX_UNITS_PER_BAND; after cap, residual is not re-evaluated against MIN_RESIDUAL_M.
    """
    if band_length_m < module_width_m:
        return 0, band_length_m

    N_raw = int(math.floor(band_length_m / module_width_m))
    residual_raw = band_length_m - N_raw * module_width_m

    if N_raw == 0:
        return 0, band_length_m

    # Reduce only when there is a positive sliver below threshold (not when residual is 0)
    if N_raw >= 2 and residual_raw > _TOL and residual_raw < (MIN_RESIDUAL_M - _TOL):
        N = N_raw - 1
        residual_width_m = band_length_m - N * module_width_m
    else:
        N = N_raw
        residual_width_m = residual_raw

    N = min(N, MAX_UNITS_PER_BAND)
    residual_width_m = band_length_m - N * module_width_m
    return N, residual_width_m


# ── Slice zone (plan Section 5) ──────────────────────────────────────────────────

def _band_depth_to_world(
    origin: tuple[float, float],
    repeat_axis: tuple[float, float],
    depth_axis: tuple[float, float],
    band: float,
    depth: float,
) -> tuple[float, float]:
    """(band, depth) in local coords to (x, y) world."""
    ox, oy = origin[0], origin[1]
    rx, ry = repeat_axis[0], repeat_axis[1]
    dx, dy = depth_axis[0], depth_axis[1]
    return (ox + band * rx + depth * dx, oy + band * ry + depth * dy)


def _build_slice_zone(
    zone: UnitZone,
    frame: ComposerFrame,
    i: int,
    module_width_m: float,
) -> UnitZone:
    """Build slice zone for index i: rectangle [slice_start, slice_end] x [0, band_depth_m] in world."""
    slice_start = i * module_width_m
    slice_end = slice_start + module_width_m
    origin = frame.origin
    R = frame.repeat_axis
    D = frame.depth_axis
    band_depth_m = frame.band_depth_m

    p0 = _band_depth_to_world(origin, R, D, slice_start, 0)
    p1 = _band_depth_to_world(origin, R, D, slice_end, 0)
    p2 = _band_depth_to_world(origin, R, D, slice_end, band_depth_m)
    p3 = _band_depth_to_world(origin, R, D, slice_start, band_depth_m)
    slice_polygon = Polygon([p0, p1, p2, p3])

    return UnitZone(
        polygon=slice_polygon,
        orientation_axis=zone.orientation_axis,
        zone_width_m=module_width_m,
        zone_depth_m=band_depth_m,
        band_id=zone.band_id,
    )


# ── Corridor clip in band-axis scalar space (plan Section 5) ─────────────────────

def _clip_corridor_edge_for_slice(
    parent_origin: tuple[float, float],
    repeat_axis: tuple[float, float],
    depth_axis: tuple[float, float],
    corridor_edge: Optional[tuple[tuple[float, float], tuple[float, float]]],
    slice_start: float,
    slice_end: float,
) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    """
    Clip parent corridor_edge to [slice_start, slice_end] in band-axis scalar space.
    (1) Project endpoints onto band axis; (2) intersect with [slice_start, slice_end];
    (3) convert back to world. Returns None if clipped interval empty.
    """
    if corridor_edge is None:
        return None
    p0, p1 = corridor_edge[0], corridor_edge[1]
    # Band coordinate = dot(point - origin, repeat_axis)
    b0 = (p0[0] - parent_origin[0]) * repeat_axis[0] + (p0[1] - parent_origin[1]) * repeat_axis[1]
    b1 = (p1[0] - parent_origin[0]) * repeat_axis[0] + (p1[1] - parent_origin[1]) * repeat_axis[1]
    if b0 > b1:
        b0, b1 = b1, b0
    c0 = max(b0, slice_start)
    c1 = min(b1, slice_end)
    if c0 >= c1 - _TOL:
        return None
    # Depth of corridor edge (constant for the segment)
    depth_c = (p0[0] - parent_origin[0]) * depth_axis[0] + (p0[1] - parent_origin[1]) * depth_axis[1]
    q0 = _band_depth_to_world(parent_origin, repeat_axis, depth_axis, c0, depth_c)
    q1 = _band_depth_to_world(parent_origin, repeat_axis, depth_axis, c1, depth_c)
    return (q0, q1)


# ── Slice frame (plan Section 5, translation-only) ───────────────────────────────

def _build_slice_frame(
    frame: ComposerFrame,
    i: int,
    module_width_m: float,
) -> ComposerFrame:
    """Build ComposerFrame for slice i: translation-only from parent; corridor clipped in band-axis space."""
    slice_start = i * module_width_m
    slice_end = slice_start + module_width_m
    origin = frame.origin
    R = frame.repeat_axis
    D = frame.depth_axis
    band_depth_m = frame.band_depth_m

    origin_slice = _band_depth_to_world(origin, R, D, slice_start, 0)

    # Frontage: segment at depth = band_depth_m from slice_start to slice_end
    frontage_start = _band_depth_to_world(origin, R, D, slice_start, band_depth_m)
    frontage_end = _band_depth_to_world(origin, R, D, slice_end, band_depth_m)
    frontage_edge = (frontage_start, frontage_end)

    # Core edge: segment at depth = 0
    core_start = _band_depth_to_world(origin, R, D, slice_start, 0)
    core_end = _band_depth_to_world(origin, R, D, slice_end, 0)
    core_edge = (core_start, core_end)

    corridor_edge = _clip_corridor_edge_for_slice(
        origin, R, D, frame.corridor_edge, slice_start, slice_end
    )

    # Wet wall: axis-aligned line through origin_slice along repeat_axis
    if frame.band_axis == "X":
        wet_wall_line = ("y", origin_slice[1])
    else:
        wet_wall_line = ("x", origin_slice[0])

    # UnitLocalFrame for slice (required by ComposerFrame)
    slice_ulf = UnitLocalFrame(
        band_id=frame.band_id,
        origin=origin_slice,
        repeat_axis=R,
        depth_axis=D,
        band_length_m=module_width_m,
        band_depth_m=band_depth_m,
        core_facing_edge=core_edge,
        corridor_facing_edge=corridor_edge,
    )

    return ComposerFrame(
        frame=slice_ulf,
        band_axis=frame.band_axis,
        frontage_edge=frontage_edge,
        wet_wall_line=wet_wall_line,
        core_edge=core_edge,
        corridor_edge=corridor_edge,
    )


# ── Validation (plan Section 8, O(N)) ────────────────────────────────────────────

def _validate_band(
    N: int,
    module_width_m: float,
    band_length_m: float,
    residual_width_m: float,
    slice_zones: List[UnitZone],
) -> None:
    """
    Structural invariants: slice boundary alignment, width accounting.
    Optionally containment; no pairwise room intersection.
    """
    # Slice boundary alignment: slice_start_{i+1} == slice_end_i
    for i in range(N - 1):
        slice_end_i = (i + 1) * module_width_m
        slice_start_next = (i + 1) * module_width_m
        if abs(slice_end_i - slice_start_next) > _TOL:
            raise BandRepetitionValidationError(
                f"Slice boundary misalignment at i={i}: slice_end_i={slice_end_i} != slice_start_{{i+1}}={slice_start_next}",
                reason="slice_boundary_misalignment",
            )

    # Width accounting
    total = N * module_width_m + residual_width_m
    if abs(total - band_length_m) > _TOL:
        raise BandRepetitionValidationError(
            f"Width accounting failed: n_units*module_width_m + residual = {total}, band_length_m = {band_length_m}",
            reason="width_accounting",
        )

    # Optional: slice zones disjoint (by construction they are adjacent; no overlap)
    for i in range(len(slice_zones)):
        for j in range(i + 1, len(slice_zones)):
            inter = slice_zones[i].polygon.intersection(slice_zones[j].polygon)
            if inter.is_empty:
                continue
            if inter.area > _TOL:
                raise BandRepetitionValidationError(
                    f"Slice zones overlap i={i} j={j}",
                    reason="slice_zones_overlap",
                )


# ── Public API ───────────────────────────────────────────────────────────────────

def repeat_band(
    zone: UnitZone,
    frame: ComposerFrame,
    module_width_m: Optional[float] = None,
) -> BandLayoutContract:
    """
    Phase 3 entry point: slice band into N segments, resolve one unit per slice, return BandLayoutContract.

    Caller should pass explicit module_width_m when density matters; None uses DEFAULT_MODULE_WIDTH_M.
    On any slice UnresolvedLayoutError, aborts entire band (BandRepetitionError).
    """
    if module_width_m is None:
        module_width_m = DEFAULT_MODULE_WIDTH_M

    band_length_m = frame.band_length_m
    band_id = frame.band_id

    N, residual_width_m = _compute_n_and_residual(band_length_m, module_width_m)

    if N == 0:
        return BandLayoutContract(
            band_id=band_id,
            units=[],
            n_units=0,
            residual_width_m=band_length_m,
            band_length_m=band_length_m,
        )

    slice_zones: List[UnitZone] = []
    units: List[UnitLayoutContract] = []

    for i in range(N):
        slice_zone = _build_slice_zone(zone, frame, i, module_width_m)
        slice_zones.append(slice_zone)
        slice_frame = _build_slice_frame(frame, i, module_width_m)
        try:
            contract = resolve_unit_layout(slice_zone, slice_frame)
            contract.unit_id = f"{band_id}_{i}"
            units.append(contract)
        except UnresolvedLayoutError as e:
            raise BandRepetitionError(
                f"Slice {i} unresolved for band_id={band_id}: {e}",
                band_id=band_id,
                slice_index=i,
                cause=e,
            ) from e

    _validate_band(N, module_width_m, band_length_m, residual_width_m, slice_zones)

    return BandLayoutContract(
        band_id=band_id,
        units=units,
        n_units=len(units),
        residual_width_m=residual_width_m,
        band_length_m=band_length_m,
    )
