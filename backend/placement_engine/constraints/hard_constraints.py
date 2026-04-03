"""
placement_engine/constraints/hard_constraints.py
-------------------------------------------------
Fail-fast constraint checker for spatial planner layouts.

These are NOT scoring metrics — they produce PASS/FAIL verdicts.
Any FATAL violation means the layout is rejected immediately.

Hard constraints
----------------
1. SPACING       — inter-tower gap ≥ required per GDCR height band table
2. FIRE_INTRUSION — no tower may overlap the fire-tender access loop
3. COP_DIMENSION  — COP must meet minimum usable width and depth
4. ORIENTATION     — tower angle must be within tolerance of road-aligned or orthogonal
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from shapely.geometry import Polygon

from placement_engine.geometry import DXF_TO_METRES
from placement_engine.geometry.fire_loop import validate_fire_loop_intact
from placement_engine.geometry.spacing_enforcer import required_spacing_m
from rules_engine.rules.loader import get_gdcr_config

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class ConstraintViolation:
    """A single hard-constraint violation."""
    name: str           # "SPACING" | "FIRE_INTRUSION" | "COP_DIMENSION" | "ORIENTATION"
    description: str    # human-readable explanation
    tower_indices: List[int] = field(default_factory=list)
    severity: str = "FATAL"


@dataclass
class ConstraintResult:
    """Aggregate result of all hard-constraint checks."""
    is_valid: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    constraint_level: int = 0  # 0 = full compliance, 1-3 = relaxed, 4 = legacy


# ── COP config helper ────────────────────────────────────────────────────────


def _get_cop_min_dimensions_m() -> tuple[float, float]:
    """Return (min_width_m, min_depth_m) from GDCR.yaml common_open_plot."""
    try:
        gdcr = get_gdcr_config()
        cop_cfg = gdcr.get("common_open_plot", {}) or {}
        geom = cop_cfg.get("geometry_constraints", {}) or {}
        width = float(geom.get("minimum_width_m", 10.0))
        depth = float(geom.get("minimum_depth_m", 10.0))
        return width, depth
    except Exception:
        return 10.0, 10.0


# ── Individual constraint checks ─────────────────────────────────────────────


def _check_spacing(
    footprints: List[Polygon],
    building_height_m: float,
) -> List[ConstraintViolation]:
    """
    Verify that every pair of towers meets the GDCR inter-building spacing.

    Uses spacing_enforcer.required_spacing_m() for the height-band lookup.
    """
    violations: List[ConstraintViolation] = []

    if len(footprints) < 2:
        return violations

    req_m = required_spacing_m(building_height_m)

    for i in range(len(footprints)):
        for j in range(i + 1, len(footprints)):
            gap_dxf = footprints[i].distance(footprints[j])
            gap_m = gap_dxf * DXF_TO_METRES

            if gap_m < req_m - 1e-6:  # small tolerance for FP
                violations.append(ConstraintViolation(
                    name="SPACING",
                    description=(
                        f"Towers {i}-{j}: gap {gap_m:.2f}m < required {req_m:.2f}m "
                        f"(height={building_height_m:.1f}m)"
                    ),
                    tower_indices=[i, j],
                ))

    return violations


def _check_fire_access(
    footprints: List[Polygon],
    fire_loop: Optional[Polygon],
) -> List[ConstraintViolation]:
    """Verify no tower intrudes into the fire-tender access loop."""
    violations: List[ConstraintViolation] = []

    if fire_loop is None or fire_loop.is_empty:
        return violations

    for idx, fp in enumerate(footprints):
        overlap = fire_loop.intersection(fp)
        if not overlap.is_empty and overlap.area > 1.0:  # > 1 sqft tolerance
            violations.append(ConstraintViolation(
                name="FIRE_INTRUSION",
                description=(
                    f"Tower {idx} intrudes into fire loop by "
                    f"{overlap.area * DXF_TO_METRES**2:.2f} sqm"
                ),
                tower_indices=[idx],
            ))

    return violations


def _check_cop_integrity(
    cop: Optional[Polygon],
    footprints: List[Polygon],
    min_width_m: float,
    min_depth_m: float,
    enforce_dimensions: bool = True,
) -> List[ConstraintViolation]:
    """
    Verify COP meets minimum usable dimensions and does not overlap towers.

    Minimum dimension is measured as the width of the minimum rotated
    rectangle (MBR) of the COP polygon.
    """
    violations: List[ConstraintViolation] = []

    if cop is None or cop.is_empty:
        return violations  # no COP to validate

    # Check overlap with towers
    for idx, fp in enumerate(footprints):
        overlap = cop.intersection(fp)
        if not overlap.is_empty and overlap.area > 1.0:
            violations.append(ConstraintViolation(
                name="COP_DIMENSION",
                description=f"Tower {idx} overlaps COP by {overlap.area:.0f} sqft",
                tower_indices=[idx],
            ))

    # Check minimum usable dimensions via MBR
    if enforce_dimensions:
        try:
            mbr = cop.minimum_rotated_rectangle
            coords = list(mbr.exterior.coords)
            # MBR has 5 coords (closed ring), edges are [0-1], [1-2]
            edge1_len = math.sqrt(
                (coords[1][0] - coords[0][0]) ** 2 +
                (coords[1][1] - coords[0][1]) ** 2
            ) * DXF_TO_METRES
            edge2_len = math.sqrt(
                (coords[2][0] - coords[1][0]) ** 2 +
                (coords[2][1] - coords[1][1]) ** 2
            ) * DXF_TO_METRES

            cop_width = min(edge1_len, edge2_len)
            cop_depth = max(edge1_len, edge2_len)

            if cop_width < min_width_m - 0.1:  # 0.1m tolerance
                violations.append(ConstraintViolation(
                    name="COP_DIMENSION",
                    description=(
                        f"COP min width {cop_width:.1f}m < required {min_width_m:.1f}m"
                    ),
                ))
            if cop_depth < min_depth_m - 0.1:
                violations.append(ConstraintViolation(
                    name="COP_DIMENSION",
                    description=(
                        f"COP min depth {cop_depth:.1f}m < required {min_depth_m:.1f}m"
                    ),
                ))
        except Exception as exc:
            logger.warning("COP dimension check failed: %s", exc)

    return violations


def _check_orientation(
    tower_angles_deg: List[float],
    road_angles_deg: List[float],
    tolerance_deg: float = 5.0,
) -> List[ConstraintViolation]:
    """
    Verify each tower is aligned within ±tolerance of road-aligned or
    orthogonal (road + 90°).

    The deviation is measured as the minimum angular distance to any of
    {road, road+90, road+180, road+270} for each road angle, normalized
    to [0, 45] degrees (since 0° and 90° alignments are equivalent for
    rectangular towers).
    """
    violations: List[ConstraintViolation] = []

    if not road_angles_deg:
        return violations  # no road info → skip orientation check

    for idx, tower_angle in enumerate(tower_angles_deg):
        best_deviation = 90.0  # worst case

        for road_angle in road_angles_deg:
            # Normalize difference to [0, 180)
            diff = abs(tower_angle - road_angle) % 180.0
            # Distance to nearest 90° alignment (0° or 90°)
            deviation = min(diff % 90.0, 90.0 - diff % 90.0)
            best_deviation = min(best_deviation, deviation)

        if best_deviation > tolerance_deg + 1e-6:
            violations.append(ConstraintViolation(
                name="ORIENTATION",
                description=(
                    f"Tower {idx}: orientation deviation {best_deviation:.1f}° "
                    f"> tolerance {tolerance_deg:.1f}°"
                ),
                tower_indices=[idx],
            ))

    return violations


# ── Main entry point ─────────────────────────────────────────────────────────


def check_hard_constraints(
    footprints: List[Polygon],
    fire_loop: Optional[Polygon],
    cop: Optional[Polygon],
    building_height_m: float,
    road_angles_deg: Optional[List[float]] = None,
    tower_angles_deg: Optional[List[float]] = None,
    constraint_level: int = 0,
) -> ConstraintResult:
    """
    Fail-fast validation of a candidate layout.

    NO scoring. Just pass/fail on each hard constraint.

    Parameters
    ----------
    footprints        : Placed tower footprint polygons (DXF feet).
    fire_loop         : Fire-tender access loop polygon (DXF feet).
    cop               : Common open plot polygon (DXF feet).
    building_height_m : Building height in metres.
    road_angles_deg   : Direction angles of road-facing edges (degrees).
    tower_angles_deg  : Orientation angle of each placed tower (degrees).
    constraint_level  : Relaxation level (0=full, 1-3=relaxed, 4=legacy).

    Returns
    -------
    ConstraintResult with is_valid=True if all constraints pass.
    """
    all_violations: List[ConstraintViolation] = []

    # 1. Spacing — always checked (never relaxed)
    all_violations.extend(_check_spacing(footprints, building_height_m))

    # 2. Fire access — checked at levels 0-3
    if constraint_level <= 3:
        all_violations.extend(_check_fire_access(footprints, fire_loop))

    # 3. COP integrity — dimensions enforced at levels 0-1, area-only at 2-3
    cop_min_w, cop_min_d = _get_cop_min_dimensions_m()
    enforce_dims = constraint_level <= 1
    all_violations.extend(_check_cop_integrity(
        cop, footprints, cop_min_w, cop_min_d,
        enforce_dimensions=enforce_dims,
    ))

    # 4. Orientation — tolerance varies by level
    if tower_angles_deg and road_angles_deg:
        tolerance = {0: 5.0, 1: 5.0, 2: 5.0, 3: 15.0}.get(constraint_level, 90.0)
        all_violations.extend(_check_orientation(
            tower_angles_deg, road_angles_deg, tolerance,
        ))

    is_valid = len(all_violations) == 0

    if not is_valid:
        logger.info(
            "Hard constraints FAILED (level=%d): %d violations — %s",
            constraint_level,
            len(all_violations),
            "; ".join(v.name for v in all_violations[:3]),
        )

    return ConstraintResult(
        is_valid=is_valid,
        violations=all_violations,
        constraint_level=constraint_level,
    )
