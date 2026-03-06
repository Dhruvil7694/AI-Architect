"""
floor_skeleton/models.py
------------------------
Pure-Python dataclasses for the Floor Skeleton Generator.

No Django ORM.  All geometry is Shapely in a local metres frame.

Three dataclasses:

    CoreCandidate   — one of the 5 discrete core strip positions
    UnitZone        — a unit zone polygon tagged with explicit orientation
    FloorSkeleton   — full skeleton result for one candidate (or the winner)

Constants:

    AXIS_WIDTH_DOMINANT / AXIS_DEPTH_DOMINANT   — UnitZone orientation tags
    VIABILITY_THRESHOLD                         — efficiency floor for the
                                                  is_architecturally_viable flag
    LABEL_ORDER                                 — canonical tie-break ordering
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from shapely.geometry import Polygon

if TYPE_CHECKING:
    from floor_skeleton.unit_local_frame import UnitLocalFrame


# ── Orientation axis constants ─────────────────────────────────────────────────

AXIS_WIDTH_DOMINANT = "WIDTH_DOMINANT"   # unit long axis runs along X (width)
AXIS_DEPTH_DOMINANT = "DEPTH_DOMINANT"   # unit long axis runs along Y (depth)

# ── Placement label constants ──────────────────────────────────────────────────

LABEL_END_CORE_LEFT              = "END_CORE_LEFT"
LABEL_END_CORE_RIGHT             = "END_CORE_RIGHT"
LABEL_CENTER_CORE                = "CENTER_CORE"
LABEL_SIDE_CORE_ALONG_LONG_EDGE  = "SIDE_CORE_ALONG_LONG_EDGE"
LABEL_SIDE_CORE_ALONG_SHORT_EDGE = "SIDE_CORE_ALONG_SHORT_EDGE"

# Canonical tie-break order — lower index = higher priority
LABEL_ORDER: list[str] = [
    LABEL_END_CORE_LEFT,
    LABEL_END_CORE_RIGHT,
    LABEL_CENTER_CORE,
    LABEL_SIDE_CORE_ALONG_LONG_EDGE,
    LABEL_SIDE_CORE_ALONG_SHORT_EDGE,
]

# ── Viability threshold ────────────────────────────────────────────────────────

VIABILITY_THRESHOLD: float = 0.35   # efficiency_ratio floor for is_architecturally_viable

# ── NO_SKELETON sentinel ───────────────────────────────────────────────────────

NO_SKELETON_PATTERN = "NO_SKELETON"
NO_SKELETON_LABEL   = "NONE"


# ── CoreCandidate ──────────────────────────────────────────────────────────────

@dataclass
class CoreCandidate:
    """
    One of the five discrete core strip positions evaluated by the builder.

    Attributes
    ----------
    label         : Placement label (one of LABEL_* constants above).
    core_box      : Shapely box polygon in local metres frame.
    is_horizontal : True when the core strip is parallel to the X axis (width).
    """
    label:         str
    core_box:      Polygon
    is_horizontal: bool


# ── UnitZone ───────────────────────────────────────────────────────────────────

@dataclass
class UnitZone:
    """
    A unit zone polygon tagged with explicit orientation metadata.

    Explicit zone_width_m / zone_depth_m fields are set by the builder so
    downstream validation never has to infer axis direction from polygon.bounds.

    For POC v1 all zones are axis-aligned rectangles, so these values equal the
    bounding box dimensions.  The explicit fields allow a future release to
    support rotated or non-rectangular zones by updating the builder alone.

    Attributes
    ----------
    polygon          : Shapely polygon in local metres frame.
    orientation_axis : AXIS_WIDTH_DOMINANT | AXIS_DEPTH_DOMINANT
                       WIDTH_DOMINANT — long axis along X (horizontal core)
                       DEPTH_DOMINANT — long axis along Y (vertical core)
    zone_width_m     : Explicit dimension along X.
    zone_depth_m     : Explicit dimension along Y.
    band_id          : Stable band index (unit_zones[i].band_id == i). Default 0 for backward compatibility.
    local_frame      : UnitLocalFrame attached post-build by services; read-only once set. Do not mutate.
    """
    polygon:          Polygon
    orientation_axis: str    # AXIS_WIDTH_DOMINANT | AXIS_DEPTH_DOMINANT
    zone_width_m:     float
    zone_depth_m:     float
    band_id:          int = 0
    local_frame:      Optional["UnitLocalFrame"] = None


# ── FloorSkeleton ──────────────────────────────────────────────────────────────

@dataclass
class FloorSkeleton:
    """
    Complete floor skeleton result for one candidate placement.

    Geometry
    --------
    footprint_polygon : (0,0)→(W,D) axis-aligned box in local metres frame.
    core_polygon      : Core strip polygon.
    corridor_polygon  : Corridor strip polygon, or None for END_CORE pattern.
    unit_zones        : List of UnitZone objects (1 or 2 zones).

    Identity
    --------
    pattern_used    : DOUBLE_LOADED / SINGLE_LOADED / END_CORE / NO_SKELETON
    placement_label : Which of the 5 candidates produced this skeleton.

    Metrics
    -------
    area_summary    : Full area breakdown dict (see skeleton_evaluator).
    efficiency_ratio: unit_area / footprint_area.

    Feasibility flags
    -----------------
    is_geometry_valid        : Structural checks (4a) all pass.
    passes_min_unit_guard    : Dimensional habitability (4b) satisfied.
    is_architecturally_viable: efficiency_ratio >= VIABILITY_THRESHOLD (flag only,
                               never used as a scoring gate).

    Audit
    -----
    audit_log: One entry per candidate tried, recording pass/fail reason.
    """
    # ── Geometry ───────────────────────────────────────────────────────────────
    footprint_polygon:     Polygon
    core_polygon:          Polygon
    corridor_polygon:      Optional[Polygon]
    unit_zones:            list[UnitZone]

    # ── Identity ───────────────────────────────────────────────────────────────
    pattern_used:          str
    placement_label:       str

    # ── Metrics ────────────────────────────────────────────────────────────────
    area_summary:          dict
    efficiency_ratio:      float

    # ── Feasibility flags ──────────────────────────────────────────────────────
    is_geometry_valid:         bool
    passes_min_unit_guard:     bool
    is_architecturally_viable: bool

    # ── Audit ──────────────────────────────────────────────────────────────────
    audit_log:             list[dict] = field(default_factory=list)
