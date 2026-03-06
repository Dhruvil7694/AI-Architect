"""
architecture.proposal_inputs
----------------------------

Proposal-style inputs for end-to-end regulatory simulation.
Validation rules: no hardcoded defaults inside logic; caller supplies values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProposalInput:
    """Real proposal-style inputs for simulate_project_proposal."""

    tp_scheme: int
    fp_number: int
    building_height_m: float
    road_width_m: float
    zone_code: str
    authority: str
    unit_mix_preference: Optional[str] = None
    rah_scheme: bool = False
    preferred_storey_height_m: Optional[float] = None
    jantri_rate: Optional[float] = None

    def validate(self) -> list[str]:
        """
        Validate fields. Returns list of error messages (empty if valid).
        Do not hardcode defaults; only validate presence and ranges.
        """
        errors: list[str] = []
        if self.building_height_m <= 0:
            errors.append("building_height_m must be > 0")
        if self.road_width_m <= 0:
            errors.append("road_width_m must be > 0")
        if self.preferred_storey_height_m is not None and self.preferred_storey_height_m <= 0:
            errors.append("preferred_storey_height_m must be > 0 when provided")
        if not (self.zone_code or "").strip():
            errors.append("zone_code must not be empty")
        if not (self.authority or "").strip():
            errors.append("authority must not be empty")
        return errors
