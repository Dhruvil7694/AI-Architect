"""
architecture.feasibility.compliance_summary
-------------------------------------------

Builds a structured compliance summary from rule results or from
persisted ComplianceResult rows. Uses rules_engine.services.report.as_dict
so the format is identical to the compliance report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from rules_engine.rules.base import RuleResult
from rules_engine.services.report import as_dict


@dataclass
class ComplianceSummary:
    """Structured compliance summary for FeasibilityAggregate."""

    total: int
    pass_count: int
    fail_count: int
    info_count: int
    na_count: int
    missing_data_count: int
    compliant: bool
    results: List[dict] = field(default_factory=list)


def build_compliance_summary_from_rule_results(results: List[RuleResult]) -> ComplianceSummary:
    """Build ComplianceSummary from a list of RuleResult (e.g. after evaluate_all())."""
    d = as_dict(results)
    summary = d["summary"]
    return ComplianceSummary(
        total=summary["total"],
        pass_count=summary["pass"],
        fail_count=summary["fail"],
        info_count=summary["info"],
        na_count=summary["na"],
        missing_data_count=summary["missing_data"],
        compliant=summary["compliant"],
        results=d["results"],
    )


def rule_result_from_compliance_result(cr) -> RuleResult:
    """Build a RuleResult from a ComplianceResult model instance."""
    return RuleResult(
        rule_id=cr.rule_id,
        source=cr.rule_source or "GDCR",
        category=cr.category or "",
        description=cr.description or "",
        status=cr.status,
        required_value=cr.required_value,
        actual_value=cr.actual_value,
        unit=cr.unit or "",
        note=cr.note or "",
    )


def build_compliance_summary_from_db(compliance_results) -> ComplianceSummary:
    """
    Build ComplianceSummary from a queryset or list of ComplianceResult.
    Does not re-run rules; only reuses stored values.
    """
    results = [rule_result_from_compliance_result(cr) for cr in compliance_results]
    return build_compliance_summary_from_rule_results(results)
