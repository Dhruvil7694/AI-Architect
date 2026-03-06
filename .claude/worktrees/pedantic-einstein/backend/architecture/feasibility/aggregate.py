"""
architecture.feasibility.aggregate
----------------------------------

FeasibilityAggregate: single structured object that aggregates plot,
regulatory, buildability, and compliance metrics for client presentation.
No geometry duplication; all values are scalars or small dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from architecture.feasibility.plot_metrics import PlotMetrics
from architecture.feasibility.buildability_metrics import BuildabilityMetrics
from architecture.feasibility.regulatory_metrics import RegulatoryMetrics
from architecture.feasibility.compliance_summary import ComplianceSummary


@dataclass
class AuditMetadata:
    """Audit trail for the feasibility run."""

    tp_scheme: str
    fp_number: str
    building_height_m: float
    road_width_m: float
    proposal_id: Optional[int] = None
    generated_at: Optional[str] = None  # ISO timestamp if set by caller


@dataclass
class FeasibilityAggregate:
    """
    Single structured feasibility report: plot + regulatory + buildability + compliance.
    Deterministic; no geometry; suitable for REST API serialization.
    """

    plot_metrics: PlotMetrics
    regulatory_metrics: RegulatoryMetrics
    buildability_metrics: BuildabilityMetrics
    compliance_summary: Optional[ComplianceSummary] = None
    audit_metadata: Optional[AuditMetadata] = None
    # Transparency for FSI assumptions (storey height / floor count used)
    storey_height_used_m: Optional[float] = None
    num_floors_estimated: Optional[int] = None

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON/API (nested dataclasses as dicts)."""
        from dataclasses import asdict
        return {
            "plot_metrics": asdict(self.plot_metrics),
            "regulatory_metrics": asdict(self.regulatory_metrics),
            "buildability_metrics": asdict(self.buildability_metrics),
            "compliance_summary": asdict(self.compliance_summary) if self.compliance_summary else None,
            "audit_metadata": asdict(self.audit_metadata) if self.audit_metadata else None,
            "storey_height_used_m": self.storey_height_used_m,
            "num_floors_estimated": self.num_floors_estimated,
        }
