"""
envelope_engine/geometry/__init__.py
-------------------------------------
Shared constants and typed exceptions for the geometry pipeline.

Unit contract
-------------
Plot.geom is in SRID=0 **metre-based** DXF coordinates (1 DXF unit = 1 m), matching
PAL/SUDA TP drawings and ``common.units.DXF_TO_METRES``.

All GDCR margin values are in METRES. Every geometry operation applies:
    margin_dxf = margin_metres * METRES_TO_DXF
"""

from __future__ import annotations

from common.units import DXF_TO_METRES, METRES_TO_DXF

# ── Unit conversion (single source: common.units) ────────────────────────────
DXF_UNIT: str = "metres"

# Minimum envelope polygon area in DXF plane units² (m² when using metre DXF).
MIN_BUILDABLE_AREA_SQFT: float = 20.0  # ≈ 215 sq.ft — habitable footprint floor


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
