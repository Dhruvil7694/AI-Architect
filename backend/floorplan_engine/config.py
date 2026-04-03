"""
floorplan_engine/config.py
--------------------------
Single source of truth for all dimensional constants used by the
procedural floor-plan circulation core generator.

Values here are the *user-specified architectural defaults*, which differ
from the existing GDCR/NBC constants in ``placement_engine.geometry.core_fit``
and ``services.floor_plan_service``.  The engine uses these unless overridden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Core-type constants ──────────────────────────────────────────────────────

POINT_CORE = "POINT_CORE"
SINGLE_CORRIDOR = "SINGLE_CORRIDOR"
DOUBLE_CORRIDOR = "DOUBLE_CORRIDOR"
DOUBLE_CORE = "DOUBLE_CORE"

CORE_TYPES = (POINT_CORE, SINGLE_CORRIDOR, DOUBLE_CORRIDOR, DOUBLE_CORE)


@dataclass(frozen=True)
class CoreConfig:
    """Immutable configuration for the floor-plan core engine."""

    # ── Lifts ────────────────────────────────────────────────────────────────
    lift_shaft_w: float = 2.2          # metres — shaft clear width
    lift_shaft_d: float = 2.2          # metres — shaft clear depth

    # ── Lobby ────────────────────────────────────────────────────────────────
    lobby_min_width: float = 2.4       # metres
    lobby_min_depth: float = 3.0       # metres

    # ── Stairs ───────────────────────────────────────────────────────────────
    min_fire_stairs: int = 2           # always ≥ 2 fire escape stairs
    stair_width: float = 1.5           # metres — clear width per stair
    stair_depth: float = 3.5           # metres — straight flight + mid-landing
    stair_wall_sep: float = 0.15       # metres — separation wall between wells

    # ── Stair separation (fire rule) ─────────────────────────────────────────
    stair_sep_ratio: float = 1.0 / 3.0  # ≥ 1/3 of building diagonal

    # ── Corridor ─────────────────────────────────────────────────────────────
    corridor_width: float = 1.8        # metres

    # ── Travel distance (NBC) ────────────────────────────────────────────────
    max_travel_dist_m: float = 22.5    # non-sprinklered
    max_dead_end_m: float = 6.0        # non-sprinklered
    travel_sample_interval_m: float = 2.0  # R2-4: centerline sample spacing

    # ── Core-type selection thresholds (sqm) ─────────────────────────────────
    point_core_max_area: float = 500.0       # < 500  → POINT_CORE
    single_corridor_max_area: float = 900.0  # < 900  → SINGLE_CORRIDOR
    double_corridor_max_area: float = 1600.0 # < 1600 → DOUBLE_CORRIDOR
    # ≥ 1600 → DOUBLE_CORE

    # ── Misc ─────────────────────────────────────────────────────────────────
    wall_t: float = 0.23              # metres — 230 mm brick wall
    clearance: float = 0.30           # metres — operational clearance

    # ── Capacity estimation defaults ─────────────────────────────────────────
    occupancy_per_unit: float = 3.5   # persons per dwelling unit


# ── Lift count resolver ──────────────────────────────────────────────────────

def resolve_lift_count(n_floors: int) -> int:
    """
    Deterministic lift count from floor count.

    Uses the *minimum* of each architectural range:
        <  8 floors → 2 lifts
        8–15 floors → 2 lifts
       16–30 floors → 3 lifts
        > 30 floors → 4 lifts
    """
    if n_floors <= 15:
        return 2
    if n_floors <= 30:
        return 3
    return 4


# ── Radial arm count (POINT_CORE) ───────────────────────────────────────────

def resolve_arm_count(target_units_per_floor: int) -> int:
    """
    R2-3: POINT_CORE radial corridor arm count from unit target.

        ≤ 4 units → 2 arms
        5–8 units → 3 arms
        > 8 units → 4 arms
    """
    if target_units_per_floor <= 4:
        return 2
    if target_units_per_floor <= 8:
        return 3
    return 4


# ── Capacity metrics ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CapacityMetrics:
    """Simple circulation capacity estimates (not simulation-based)."""

    people_per_lift: float
    stair_capacity_persons_per_min: float
    corridor_density_persons_per_m: float


def compute_capacity(
    n_lifts: int,
    stair_width_m: float,
    n_stairs: int,
    corridor_length_m: float,
    n_floors: int,
    units_per_floor: int,
    occupancy_per_unit: float = 3.5,
) -> CapacityMetrics:
    """Estimate circulation capacity metrics."""
    population = n_floors * units_per_floor * occupancy_per_unit
    return CapacityMetrics(
        people_per_lift=population / max(n_lifts, 1),
        stair_capacity_persons_per_min=60.0 * stair_width_m * n_stairs,
        corridor_density_persons_per_m=population / max(corridor_length_m, 1.0),
    )
