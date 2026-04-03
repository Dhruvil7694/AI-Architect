"""
floorplan_engine/geometry/axis_detection.py
-------------------------------------------
Detect the principal (long / short) axes of a tower footprint polygon.

R2-8: Uses longest edge as primary; falls back to the Minimum Rotated
Rectangle (MRR) longer side when the polygon is curved / chamfered.

R1-10: Accepts an optional ``orientation_deg`` override so the user's
design intent is respected when provided.
"""

from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import Polygon

from common.units import METRES_TO_DXF

from floorplan_engine.models import AxisFrame


def detect_principal_axes(
    footprint_dxf: Polygon,
    orientation_deg: Optional[float] = None,
) -> AxisFrame:
    """
    Determine the L (long) and S (short) axis frame of a footprint.

    Parameters
    ----------
    footprint_dxf : Polygon
        Tower footprint in DXF-feet coordinate space.
    orientation_deg : float | None
        If provided, forces the L-axis to this angle (degrees from +X axis).
        Overrides automatic detection (R1-10).

    Returns
    -------
    AxisFrame
        Contains origin (DXF), L/S unit vectors (DXF per metre),
        footprint dimensions in metres, and rotation angle.
    """
    if orientation_deg is not None:
        rad = math.radians(orientation_deg)
        lx, ly = math.cos(rad), math.sin(rad)
    else:
        lx, ly = _detect_long_axis(footprint_dxf)

    # S axis is 90° counter-clockwise from L
    sx, sy = -ly, lx

    # Project all vertices onto L and S to get extents
    coords = list(footprint_dxf.exterior.coords)
    l_vals = [c[0] * lx + c[1] * ly for c in coords]
    s_vals = [c[0] * sx + c[1] * sy for c in coords]

    l_min, l_max = min(l_vals), max(l_vals)
    s_min, s_max = min(s_vals), max(s_vals)

    # Origin in DXF = point at (l_min, s_min)
    origin_x = l_min * lx + s_min * sx
    origin_y = l_min * ly + s_min * sy

    # Extents in DXF feet → metres
    from common.units import DXF_TO_METRES
    length_dxf = l_max - l_min
    width_dxf = s_max - s_min
    length_m = length_dxf * DXF_TO_METRES
    width_m = width_dxf * DXF_TO_METRES

    # Ensure length ≥ width (swap axes if needed)
    rotation_deg = math.degrees(math.atan2(ly, lx))
    if width_m > length_m:
        length_m, width_m = width_m, length_m
        lx, ly, sx, sy = sx, sy, -lx, -ly
        # Recompute origin with swapped axes
        l_vals = [c[0] * lx + c[1] * ly for c in coords]
        s_vals = [c[0] * sx + c[1] * sy for c in coords]
        l_min = min(l_vals)
        s_min = min(s_vals)
        origin_x = l_min * lx + s_min * sx
        origin_y = l_min * ly + s_min * sy
        rotation_deg = math.degrees(math.atan2(ly, lx))

    # DXF displacement per 1 metre along each axis
    l_vec_dxf = (lx * METRES_TO_DXF, ly * METRES_TO_DXF)
    s_vec_dxf = (sx * METRES_TO_DXF, sy * METRES_TO_DXF)

    return AxisFrame(
        origin_dxf=(origin_x, origin_y),
        l_vec_dxf=l_vec_dxf,
        s_vec_dxf=s_vec_dxf,
        length_m=length_m,
        width_m=width_m,
        rotation_deg=rotation_deg,
    )


# ── Internal helpers ─────────────────────────────────────────────────────────

def _detect_long_axis(footprint_dxf: Polygon) -> tuple[float, float]:
    """
    Detect the L-axis unit vector from the footprint polygon.

    R2-8 algorithm:
      1. Primary: longest edge of the outer ring.
      2. Validate: if longest edge < 30% of MRR longer side, the polygon
         is curved/chamfered → use MRR instead.
      3. Canonical direction: lx ≥ 0 (or ly ≥ 0 when lx ≈ 0).
    """
    coords = list(footprint_dxf.exterior.coords)
    ring = coords[:-1] if len(coords) > 1 and coords[0] == coords[-1] else coords

    # Find longest edge
    max_len = 0.0
    best_lx, best_ly = 1.0, 0.0
    for i in range(len(ring)):
        j = (i + 1) % len(ring)
        dx = ring[j][0] - ring[i][0]
        dy = ring[j][1] - ring[i][1]
        length = math.hypot(dx, dy)
        if length > max_len:
            max_len = length
            best_lx = dx / length
            best_ly = dy / length

    # R2-8: validate against MRR
    mrr = footprint_dxf.minimum_rotated_rectangle
    if mrr is not None and not mrr.is_empty:
        mrr_coords = list(mrr.exterior.coords)
        mrr_edges = []
        for i in range(len(mrr_coords) - 1):
            dx = mrr_coords[i + 1][0] - mrr_coords[i][0]
            dy = mrr_coords[i + 1][1] - mrr_coords[i][1]
            mrr_edges.append(math.hypot(dx, dy))
        mrr_long = max(mrr_edges) if mrr_edges else max_len

        if max_len < 0.30 * mrr_long:
            # Polygon is curved/chamfered — use MRR longer side
            best_edge_idx = mrr_edges.index(max(mrr_edges))
            dx = mrr_coords[best_edge_idx + 1][0] - mrr_coords[best_edge_idx][0]
            dy = mrr_coords[best_edge_idx + 1][1] - mrr_coords[best_edge_idx][1]
            length = math.hypot(dx, dy)
            if length > 1e-9:
                best_lx = dx / length
                best_ly = dy / length

    # Canonical direction: lx ≥ 0; if lx ≈ 0, ly ≥ 0
    if best_lx < -1e-9 or (abs(best_lx) < 1e-9 and best_ly < 0):
        best_lx, best_ly = -best_lx, -best_ly

    return (best_lx, best_ly)
