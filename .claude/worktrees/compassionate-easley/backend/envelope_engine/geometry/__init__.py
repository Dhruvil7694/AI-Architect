"""
envelope_engine/geometry/__init__.py
-------------------------------------
Shared constants and typed exceptions for the geometry pipeline.

Unit contract
-------------
Plot.geom is stored in SRID=0 DXF coordinate units.  Based on the PAL TP14
ingestion the DXF drawing unit is FEET (areas match sq.ft from the Excel
metadata with no conversion).

All GDCR margin values are in METRES.  Every geometry operation that applies
a margin must convert:
    margin_dxf = margin_metres * METRES_TO_DXF

If a future scheme is confirmed to use a different unit, swap the constant
here and nothing else needs to change.
"""

from __future__ import annotations

# ── Unit conversion ───────────────────────────────────────────────────────────
DXF_UNIT: str = "feet"
METRES_TO_DXF: float = 1.0 / 0.3048   # 3.28084  feet per metre
DXF_TO_METRES: float = 0.3048         # metres per DXF foot

# Minimum envelope area (sq.ft in DXF units) below which we declare TOO_SMALL.
# ~20 sq.m converted to sq.ft as a sane lower bound for any habitable footprint.
MIN_BUILDABLE_AREA_SQFT: float = 215.0   # ≈ 20 sq.m


# ── Typed exceptions ──────────────────────────────────────────────────────────

class EnvelopeError(Exception):
    """Base class for all envelope computation errors."""


class EnvelopeCollapseError(EnvelopeError):
    """
    Raised when the per-edge margin intersection produces an empty polygon.
    This means the proposed margins are wider than the plot itself.
    """


class EnvelopeTooSmallError(EnvelopeError):
    """
    Raised when the resulting envelope is non-empty but below
    MIN_BUILDABLE_AREA_SQFT.
    """


class InvalidGeometryError(EnvelopeError):
    """
    Raised when the input plot polygon is degenerate or self-intersecting
    and cannot be repaired with a zero-distance buffer.
    """


class InsufficientInputError(EnvelopeError):
    """
    Raised when road_facing_edges is empty — we cannot classify edges
    without knowing which face a road.
    """
