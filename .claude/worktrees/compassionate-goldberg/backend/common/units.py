"""
common/units.py
---------------
Canonical area and length conversion for the Architecture AI pipeline.

Unit contract
-------------
- Geometry storage (Plot.geom, envelope, placement polygons): DXF feet.
- Stored areas in DB (Plot.area_geometry, envelope_area_sqft, total_bua, etc.): sq.ft (DXF native).
- Regulatory thresholds in GDCR/NBC config: often sq.m and metres.
- Use the helpers below for any conversion; do not hardcode factors elsewhere.

Reference: 1 international foot = 0.3048 m  =>  1 sq.ft = 0.09290304 sq.m.
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


# ── Length (DXF feet ↔ metres) ──────────────────────────────────────────────
# Linear DXF is defined in envelope_engine.geometry; we re-export here so
# feasibility and reporting have one place to import from when both area and
# length are needed. Avoids scattering conversion factors.

DXF_TO_METRES: float = 0.3048
METRES_TO_DXF: float = 1.0 / DXF_TO_METRES


def dxf_to_metres(length_dxf: float) -> float:
    """Convert length from DXF feet to metres."""
    return length_dxf * DXF_TO_METRES


def metres_to_dxf(length_m: float) -> float:
    """Convert length from metres to DXF feet."""
    return length_m * METRES_TO_DXF
