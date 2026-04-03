"""
floorplan_engine/corridor/corridor_rules.py
-------------------------------------------
Corridor compliance rules — width, travel distance, dead-end.

These are lightweight checks; the full compliance engine in
``validation/compliance_engine.py`` uses the circulation graph for
more accurate dead-end detection (R2-6).
"""

from __future__ import annotations

from floorplan_engine.config import CoreConfig


def check_corridor_width(corridor_width_m: float, config: CoreConfig) -> bool:
    """Corridor width ≥ configured minimum (1.8 m default)."""
    return corridor_width_m >= config.corridor_width - 1e-6


def check_travel_distance(max_travel_m: float, config: CoreConfig) -> bool:
    """Maximum travel distance ≤ limit (22.5 m non-sprinklered)."""
    return max_travel_m <= config.max_travel_dist_m + 1e-6


def check_dead_end(dead_end_m: float, config: CoreConfig) -> bool:
    """Dead-end length ≤ limit (6.0 m non-sprinklered)."""
    return dead_end_m <= config.max_dead_end_m + 1e-6
