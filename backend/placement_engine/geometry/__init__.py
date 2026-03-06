"""
placement_engine/geometry/__init__.py
--------------------------------------
Shared constants, dataclasses, and typed exceptions for the placement
geometry pipeline.

Unit contract
-------------
All geometry operates in DXF feet (SRID=0), consistent with Plot.geom and
PlotEnvelope.envelope_geom.  GDCR margin values are always in metres and
converted via METRES_TO_DXF before any geometric operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Re-export unit constants from envelope_engine to avoid duplication ─────────
from envelope_engine.geometry import (
    METRES_TO_DXF,
    DXF_TO_METRES,
    DXF_UNIT,
    MIN_BUILDABLE_AREA_SQFT,
)

# ── Grid resolution limits ─────────────────────────────────────────────────────
TARGET_CELLS_PER_AXIS: int   = 200       # grid never exceeds 200×200 cells
MIN_RESOLUTION_DXF:   float = 0.25      # 0.25 ft ≈ 7.5 cm — fine enough for any plot
MAX_RESOLUTION_DXF:   float = 2.00      # 2.0 ft ≈ 60 cm — coarse enough for large plots

# ── Multi-building packing limits ─────────────────────────────────────────────
MAX_TOWERS:     int = 4    # hard cap — more than 4 towers on a TP plot is unusual
MAX_COMPONENTS: int = 10   # max MultiPolygon components to evaluate per step

# ── Minimum footprint dimensions (can be overridden per command call) ──────────
MIN_FOOTPRINT_WIDTH_M:  float = 5.0    # 16.4 ft — narrowest buildable slab
MIN_FOOTPRINT_DEPTH_M:  float = 4.0    # 13.1 ft — minimum habitable room depth
MIN_FOOTPRINT_AREA_SQFT: float = MIN_BUILDABLE_AREA_SQFT  # ≈ 215 sq.ft (20 sq.m)

# ── Aspect ratio tie-break preference (width:depth) ───────────────────────────
PREFERRED_ASPECT_RATIO: float = 2.0    # 2:1 is the most practical slab shape


# ── Typed exceptions ───────────────────────────────────────────────────────────

class PlacementError(Exception):
    """Base class for all placement computation errors."""


class NoFitError(PlacementError):
    """
    Raised when not even one building footprint can fit inside the envelope.
    Causes status = NO_FIT.
    """


class TooTightError(PlacementError):
    """
    Raised when fewer towers were placed than requested due to spacing
    constraints.  Causes status = TOO_TIGHT.
    """


class InvalidInputError(PlacementError):
    """
    Raised for bad inputs: n_towers < 1, building_height_m <= 0, or a
    degenerate/null envelope polygon.
    """


# ── FootprintCandidate dataclass ───────────────────────────────────────────────

@dataclass
class FootprintCandidate:
    """
    Represents a single candidate building footprint discovered by
    InscribedRectangle at a given orientation angle.

    All linear dimensions are in DXF feet; areas in sq.ft.
    """
    footprint_polygon:       object   # Shapely Polygon
    area_sqft:               float
    width_dxf:               float    # dimension along orientation angle
    depth_dxf:               float    # dimension perpendicular to orientation
    width_m:                 float
    depth_m:                 float
    orientation_angle_deg:   float    # angle used for grid rotation
    orientation_label:       str      # "PRIMARY" | "PERPENDICULAR"
    grid_resolution_dxf:     float    # adaptive resolution used
    source_component_index:  int = 0  # which MultiPolygon component (0 = not multi)

    # ── Derived audit helpers ──────────────────────────────────────────────────
    @property
    def aspect_ratio(self) -> float:
        """width / depth; always >= 1."""
        if self.depth_dxf <= 0:
            return float("inf")
        return max(self.width_dxf, self.depth_dxf) / min(self.width_dxf, self.depth_dxf)

    @property
    def aspect_ratio_score(self) -> float:
        """Closeness to PREFERRED_ASPECT_RATIO; lower = better."""
        return abs(self.aspect_ratio - PREFERRED_ASPECT_RATIO)

    def to_audit_dict(self) -> dict:
        return {
            "area_sqft":              round(self.area_sqft, 2),
            "width_dxf":              round(self.width_dxf, 3),
            "depth_dxf":              round(self.depth_dxf, 3),
            "width_m":                round(self.width_m, 3),
            "depth_m":                round(self.depth_m, 3),
            "orientation_angle_deg":  round(self.orientation_angle_deg, 4),
            "orientation_label":      self.orientation_label,
            "aspect_ratio":           round(self.aspect_ratio, 3),
            "grid_resolution_dxf":    round(self.grid_resolution_dxf, 4),
            "source_component_index": self.source_component_index,
        }
