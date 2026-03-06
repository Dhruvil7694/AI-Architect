"""
residential_layout/errors.py — Phase 2 exception hierarchy.

Structured reason codes: zone_too_small, room_min_dim_fail, connectivity_fail,
wet_wall_alignment_fail, width_budget_fail. No silent degradation.
"""

from __future__ import annotations


class ResidentialLayoutError(Exception):
    """Base for all residential layout errors."""

    def __init__(self, message: str, reason_code: str | None = None, template_name: str | None = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.template_name = template_name


class UnitZoneTooSmallError(ResidentialLayoutError):
    """
    Zone dimensions below template minima.

    reason_code: "zone_too_small"
    """

    def __init__(
        self,
        message: str,
        template_name: str | None = None,
        which: str | None = None,
    ):
        super().__init__(message, reason_code="zone_too_small", template_name=template_name)
        self.which = which  # "width" | "depth"


class LayoutCompositionError(ResidentialLayoutError):
    """
    Deterministic cut/validation failed.

    reason_code: room_min_dim_fail | connectivity_fail | wet_wall_alignment_fail | width_budget_fail
    """

    def __init__(
        self,
        message: str,
        reason_code: str,
        template_name: str | None = None,
        room_type: str | None = None,
    ):
        super().__init__(message, reason_code=reason_code, template_name=template_name)
        self.room_type = room_type


class UnresolvedLayoutError(ResidentialLayoutError):
    """
    All fallback templates exhausted (orchestrator only).

    reason_code: "unresolved"
    """

    def __init__(self, message: str, failure_reasons: list[dict] | None = None):
        super().__init__(message, reason_code="unresolved")
        self.failure_reasons = failure_reasons or []
