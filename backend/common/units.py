"""
common/units.py
---------------
Canonical area and length conversion for the Architecture AI pipeline.

Unit contract
-------------
- Geometry storage (Plot.geom, envelope, placement polygons): DXF drawing units in
  the CAD plane. For Gujarat TP schemes ingested here, coordinates are in **metres**
  (consistent with "MT" road widths on plans): 1 DXF unit = 1 m.
- Polygon areas from Shapely (Plot.area_geometry, envelope.area, footprint.area):
  square of the drawing unit use ``dxf_plane_area_to_sqm`` to get m² — do **not**
  treat raw area as international sq.ft unless the value is explicitly imperial.
- Regulatory thresholds in GDCR/NBC config: typically sq.m and metres.
- Use the helpers below for any conversion; do not hardcode factors elsewhere.

Reference: international foot/sq.ft conversions remain available for Excel or
reports that are explicitly in imperial units.
"""

from __future__ import annotations

# ── Area (sq.ft ↔ sq.m) ─────────────────────────────────────────────────────

SQFT_TO_SQM: float = 0.09290304
SQM_TO_SQFT: float = 1.0 / SQFT_TO_SQM


def sqft_to_sqm(area_sqft: float) -> float:
    """Convert area from sq.ft (DXF/DB native) to sq.m."""
    return area_sqft * SQFT_TO_SQM


def sqm_to_sqft(area_sqm: float) -> float:
    """Convert area from sq.m to sq.ft."""
    return area_sqm * SQM_TO_SQFT


# ── Length (DXF drawing units ↔ metres) ──────────────────────────────────────
# 1 DXF unit = 1 m for current TP ingestion. If a scheme used feet instead,
# set DXF_TO_METRES = 0.3048 (and adjust envelope MIN_BUILDABLE threshold).

DXF_TO_METRES: float = 1.0
METRES_TO_DXF: float = 1.0


def dxf_to_metres(length_dxf: float) -> float:
    """Convert length from DXF drawing units to metres."""
    return length_dxf * DXF_TO_METRES


def metres_to_dxf(length_m: float) -> float:
    """Convert length from metres to DXF drawing units."""
    return length_m * METRES_TO_DXF


def dxf_plane_area_to_sqm(area_dxf2: float) -> float:
    """Convert a polygon area from DXF plane units² to square metres."""
    f = float(DXF_TO_METRES)
    return float(area_dxf2) * f * f
