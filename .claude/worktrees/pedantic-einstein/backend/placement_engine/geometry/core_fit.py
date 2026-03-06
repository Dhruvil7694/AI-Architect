"""
placement_engine/geometry/core_fit.py
--------------------------------------
Pure-dimensional Core Fit Validator.

Given a building footprint (width_m x depth_m) and the proposed height,
determines whether an NBC/GDCR-compliant building core can physically fit
inside that footprint using only arithmetic checks — no Shapely geometry.

All three layout patterns are always evaluated in full; the highest-priority
passing pattern is then selected (DOUBLE_LOADED > SINGLE_LOADED > END_CORE).
This guarantees the audit_log always contains exactly 3 entries regardless of
which pattern is chosen or whether any pattern passes.

  DOUBLE_LOADED — units on both sides of a central corridor, core at one end.
                  Requires deep footprints (>= 10.66 m).

  SINGLE_LOADED — units along one side, core + corridor on the other.
                  Requires moderate depth (>= 6.16 m).

  END_CORE      — core strip at one short end, units fill remaining width.
                  The most compact option for narrow slabs.
                  Depth requirement is stair_run_m only (bypasses
                  min_unit_depth_m; units run the full slab depth).

If none fit: NO_CORE_FIT.

All dimension constants are encapsulated in CoreDimensions (configurable)
so future authority-specific overrides require no code changes.

Future AI hook
--------------
The public signature validate_core_fit(width_m, depth_m, building_height_m,
dims) is stable.  A future AI layout generator replaces the body; the rest of
the pipeline (PlacementResult, FootprintRecord, command report) is unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


# ── Status / pattern constants ─────────────────────────────────────────────────

CORE_VALID        = "VALID"
NO_CORE_FIT       = "NO_CORE_FIT"

PATTERN_DOUBLE    = "DOUBLE_LOADED"
PATTERN_SINGLE    = "SINGLE_LOADED"
PATTERN_END       = "END_CORE"
PATTERN_NONE      = "NONE"


# ── CoreDimensions configurable dataclass ─────────────────────────────────────

@dataclass
class CoreDimensions:
    """
    All NBC/GDCR dimensional constants used by the core fit algorithm.

    All values in metres.  Override individual fields to model a different
    authority or building type without subclassing.

    Sources
    -------
    stair_width_m      : GDCR Table 13.2  (residential apartment = 1.0 m)
    stair_run_m        : NBC 2016 Part 3  (1 flight + landing ≈ 3.6 m in plan)
    landing_m          : NBC 2016          (equal to stair width, minimum 1.0 m)
    lift_w_m / lift_d_m: NBC 2016 standard single-car shaft (1.5 × 1.5 m)
    lift_lobby_m       : NBC 2016          (1.5 m clear in front of lift)
    lift_threshold_m   : GDCR lift_requirement (lift required if H > 10 m)
    highrise_threshold_m: NBC Part 4       (2nd staircase required if H > 15 m)
    corridor_m         : NBC 2016 egress   (minimum 1.2 m)
    min_unit_depth_m   : NBC habitable room (minimum room + wall depth ≈ 4.5 m)
    min_unit_width_m   : Practical 1BHK module minimum (3.0 m)
    wall_t_m           : Standard 230 mm brick wall
    clearance_m        : Operational clearance between core components
    """
    stair_width_m:        float = 1.0
    stair_run_m:          float = 3.6
    landing_m:            float = 1.0
    lift_w_m:             float = 1.5
    lift_d_m:             float = 1.5
    lift_lobby_m:         float = 1.5
    lift_threshold_m:     float = 10.0   # GDCR: lift required above this height
    highrise_threshold_m: float = 15.0   # NBC: 2nd staircase above this height
    corridor_m:           float = 1.2
    min_unit_depth_m:     float = 4.5
    min_unit_width_m:     float = 3.0
    wall_t_m:             float = 0.23
    clearance_m:          float = 0.30


# ── CoreValidationResult dataclass ────────────────────────────────────────────

@dataclass
class CoreValidationResult:
    """
    Result of validate_core_fit().

    All area values in sq.m, all linear dimensions in metres.
    audit_log contains one entry per pattern tried (all three are always
    recorded, even the skipped ones) so every dimension shortfall is traceable.
    """
    core_fit_status:        str          # CORE_VALID | NO_CORE_FIT
    selected_pattern:       str          # DOUBLE_LOADED | SINGLE_LOADED | END_CORE | NONE
    core_area_estimate_sqm: float        # area consumed by core package
    remaining_usable_sqm:   float        # footprint area minus core and corridor
    lift_required:          bool
    n_staircases_required:  int
    core_pkg_width_m:       float        # computed core package width
    core_pkg_depth_m:       float        # computed core package depth
    audit_log:              list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Serialise to a plain dict for JSON storage in FootprintRecord.

        Round-trips through json.dumps/loads to ensure every value is a
        JSON-native Python type (str, int, float, list, dict, bool, None).
        This avoids psycopg2 serialization issues on Python 3.13 where its
        custom JSON adapter may not handle Python booleans directly.
        """
        raw = {
            "core_fit_status":        self.core_fit_status,
            "selected_pattern":       self.selected_pattern,
            "core_area_estimate_sqm": round(self.core_area_estimate_sqm, 3),
            "remaining_usable_sqm":   round(self.remaining_usable_sqm, 3),
            "lift_required":          bool(self.lift_required),
            "n_staircases_required":  int(self.n_staircases_required),
            "core_pkg_width_m":       round(float(self.core_pkg_width_m), 3),
            "core_pkg_depth_m":       round(float(self.core_pkg_depth_m), 3),
            "audit_log":              self.audit_log,
        }
        return json.loads(json.dumps(raw))


# ── Public API ─────────────────────────────────────────────────────────────────

def validate_core_fit(
    width_m:           float,
    depth_m:           float,
    building_height_m: float,
    dims:              CoreDimensions = None,
) -> CoreValidationResult:
    """
    Validate whether a building footprint can accommodate an NBC/GDCR-compliant
    building core.

    All three layout patterns (DOUBLE_LOADED, SINGLE_LOADED, END_CORE) are
    always evaluated in full.  An audit entry is recorded for every pattern
    regardless of outcome, so audit_log always contains exactly 3 entries.
    After all checks the highest-priority passing pattern is selected:
    DOUBLE_LOADED > SINGLE_LOADED > END_CORE.  If none pass: NO_CORE_FIT.

    Parameters
    ----------
    width_m           : Footprint width in metres.
    depth_m           : Footprint depth in metres.
    building_height_m : Proposed building height in metres.
    dims              : CoreDimensions instance (default values used if None).

    Returns
    -------
    CoreValidationResult — fully populated with status, pattern, areas, audit.
    """
    if dims is None:
        dims = CoreDimensions()

    # ── Guard ──────────────────────────────────────────────────────────────────
    if building_height_m <= 0 or width_m <= 0 or depth_m <= 0:
        return _no_fit_result(dims, width_m, depth_m, building_height_m,
                              reason="Invalid dimensions (must all be > 0)")

    # ── Derived values ─────────────────────────────────────────────────────────
    lift_required = building_height_m > dims.lift_threshold_m
    n_stairs      = 2 if building_height_m > dims.highrise_threshold_m else 1

    # Core "package" width — all components placed side by side:
    #   n stairs | wall | lift shaft | wall | clearance
    core_pkg_w = (
        n_stairs * dims.stair_width_m
        + dims.wall_t_m
        + (dims.lift_w_m + dims.wall_t_m if lift_required else 0.0)
        + dims.clearance_m
    )

    # Core "package" depth — dominated by stair run length
    # (lift lobby of 1.5 m always fits within the 3.6 m stair run zone)
    core_pkg_d = dims.stair_run_m

    audit_log: list[dict] = []

    # ── Pattern 1: DOUBLE_LOADED ───────────────────────────────────────────────
    dl_depth_req = (2.0 * dims.min_unit_depth_m
                    + dims.corridor_m
                    + 2.0 * dims.wall_t_m)
    dl_width_req = core_pkg_w + 2.0 * dims.min_unit_width_m

    dl_depth_ok = depth_m >= dl_depth_req
    dl_width_ok = width_m >= dl_width_req
    dl_pass     = dl_depth_ok and dl_width_ok

    audit_log.append({
        "pattern":     PATTERN_DOUBLE,
        "depth_check": _check(dl_depth_req, depth_m, dl_depth_ok),
        "width_check": _check(dl_width_req, width_m, dl_width_ok),
        "outcome":     "PASS" if dl_pass else "FAIL",
    })

    # ── Pattern 2: SINGLE_LOADED ───────────────────────────────────────────────
    sl_depth_req = (dims.min_unit_depth_m
                    + dims.corridor_m
                    + 2.0 * dims.wall_t_m)
    sl_width_req = core_pkg_w + dims.wall_t_m

    sl_depth_ok = depth_m >= sl_depth_req
    sl_width_ok = width_m >= sl_width_req
    sl_pass     = sl_depth_ok and sl_width_ok

    audit_log.append({
        "pattern":     PATTERN_SINGLE,
        "depth_check": _check(sl_depth_req, depth_m, sl_depth_ok),
        "width_check": _check(sl_width_req, width_m, sl_width_ok),
        "outcome":     "PASS" if sl_pass else "FAIL",
    })

    # ── Pattern 3: END_CORE ────────────────────────────────────────────────────
    ec_width_req = core_pkg_w + dims.min_unit_width_m
    ec_depth_req = core_pkg_d

    ec_width_ok = width_m >= ec_width_req
    ec_depth_ok = depth_m >= ec_depth_req
    ec_pass     = ec_width_ok and ec_depth_ok

    audit_log.append({
        "pattern":     PATTERN_END,
        "depth_check": _check(ec_depth_req, depth_m, ec_depth_ok),
        "width_check": _check(ec_width_req, width_m, ec_width_ok),
        "outcome":     "PASS" if ec_pass else "FAIL",
    })

    # ── Select best passing pattern (DOUBLE > SINGLE > END) ───────────────────
    if dl_pass:
        # Remaining usable area: both unit sides minus corridor strip.
        # Corridor spans only the non-core zone (width - core_pkg_w).
        unit_area     = (width_m - core_pkg_w) * depth_m
        corridor_area = dims.corridor_m * (width_m - core_pkg_w)
        remaining     = max(0.0, unit_area - corridor_area)
        core_area     = core_pkg_w * depth_m
        return CoreValidationResult(
            core_fit_status=CORE_VALID,
            selected_pattern=PATTERN_DOUBLE,
            core_area_estimate_sqm=core_area,
            remaining_usable_sqm=remaining,
            lift_required=lift_required,
            n_staircases_required=n_stairs,
            core_pkg_width_m=core_pkg_w,
            core_pkg_depth_m=core_pkg_d,
            audit_log=audit_log,
        )

    if sl_pass:
        # Remaining usable: unit side minus corridor
        unit_depth = depth_m - dims.corridor_m
        remaining  = max(0.0, (width_m - core_pkg_w) * unit_depth)
        core_area  = core_pkg_w * depth_m
        return CoreValidationResult(
            core_fit_status=CORE_VALID,
            selected_pattern=PATTERN_SINGLE,
            core_area_estimate_sqm=core_area,
            remaining_usable_sqm=remaining,
            lift_required=lift_required,
            n_staircases_required=n_stairs,
            core_pkg_width_m=core_pkg_w,
            core_pkg_depth_m=core_pkg_d,
            audit_log=audit_log,
        )

    if ec_pass:
        remaining_w = width_m - core_pkg_w
        remaining   = max(0.0, remaining_w * depth_m)
        core_area   = core_pkg_w * depth_m
        return CoreValidationResult(
            core_fit_status=CORE_VALID,
            selected_pattern=PATTERN_END,
            core_area_estimate_sqm=core_area,
            remaining_usable_sqm=remaining,
            lift_required=lift_required,
            n_staircases_required=n_stairs,
            core_pkg_width_m=core_pkg_w,
            core_pkg_depth_m=core_pkg_d,
            audit_log=audit_log,
        )

    # ── No pattern fitted ──────────────────────────────────────────────────────
    return CoreValidationResult(
        core_fit_status=NO_CORE_FIT,
        selected_pattern=PATTERN_NONE,
        core_area_estimate_sqm=0.0,
        remaining_usable_sqm=0.0,
        lift_required=lift_required,
        n_staircases_required=n_stairs,
        core_pkg_width_m=core_pkg_w,
        core_pkg_depth_m=core_pkg_d,
        audit_log=audit_log,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _check(required: float, actual: float, passed: bool) -> dict:
    return {
        "required_m":  round(float(required), 3),
        "actual_m":    round(float(actual), 3),
        "shortfall_m": round(float(max(0.0, required - actual)), 3),
        "pass":        bool(passed),
    }


def _no_fit_result(
    dims:              CoreDimensions,
    width_m:           float,
    depth_m:           float,
    building_height_m: float,
    reason:            str,
) -> CoreValidationResult:
    """Return a NO_CORE_FIT result for invalid inputs."""
    return CoreValidationResult(
        core_fit_status=NO_CORE_FIT,
        selected_pattern=PATTERN_NONE,
        core_area_estimate_sqm=0.0,
        remaining_usable_sqm=0.0,
        lift_required=building_height_m > dims.lift_threshold_m,
        n_staircases_required=2 if building_height_m > dims.highrise_threshold_m else 1,
        core_pkg_width_m=0.0,
        core_pkg_depth_m=0.0,
        audit_log=[{"reason": reason}],
    )
