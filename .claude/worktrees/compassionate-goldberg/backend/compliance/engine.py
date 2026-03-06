from __future__ import annotations

"""
backend.compliance.engine
-------------------------

Deterministic, geometry-free ComplianceEngine that evaluates a set of CGDCR
rules against a precomputed ComplianceContext and produces a ComplianceResult.

This initial implementation focuses on core DW3 checks (FSI and height vs.
road width) and is structured to scale to additional rule groups without
introducing giant if/else blocks or dynamic eval.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List

import json

from .context import ComplianceContext


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    group_id: str
    status: str  # PASS / FAIL / WARNING
    severity: str  # INFO / LOW / MEDIUM / HIGH / CRITICAL
    expected_value: Dict[str, Any]
    provided_value: Dict[str, Any]
    explanation_key: str


@dataclass(frozen=True)
class ComplianceResult:
    """
    Deterministic evaluation output matching the ComplianceResult JSON contract.
    """

    schema_version: str
    engine: Dict[str, str]
    input_refs: Dict[str, str]
    overall: Dict[str, Any]
    groups: List[Dict[str, Any]]
    rules: List[RuleEvaluation]
    errors: List[Dict[str, Any]]
    result_hash: str
    generated_at: str


class RuleGroupEvaluator:
    group_id: str

    def evaluate(self, context: ComplianceContext) -> List[RuleEvaluation]:
        raise NotImplementedError


class FsiRuleEvaluator(RuleGroupEvaluator):
    group_id = "fsi"

    def evaluate(self, context: ComplianceContext) -> List[RuleEvaluation]:
        required_max = context.building_fsi_limit
        provided = context.building_fsi
        status = "PASS" if provided <= required_max + 1e-4 else "FAIL"
        return [
            RuleEvaluation(
                rule_id="DW3-FSI-MAX",
                group_id=self.group_id,
                status=status,
                severity="HIGH",
                expected_value={
                    "kind": "NUMERIC_THRESHOLD",
                    "metric": "building_fsi",
                    "operator": "<=",
                    "value": required_max,
                    "unit": "",
                },
                provided_value={
                    "metric": "building_fsi",
                    "value": provided,
                    "unit": "",
                },
                explanation_key="FSI_MAX_EXCEEDED",
            )
        ]


class HeightRuleEvaluator(RuleGroupEvaluator):
    group_id = "height"

    def evaluate(self, context: ComplianceContext) -> List[RuleEvaluation]:
        required_max = context.building_height_limit_m
        provided = context.building_height_m
        status = "PASS" if provided <= required_max + 1e-4 else "FAIL"
        return [
            RuleEvaluation(
                rule_id="DW3-HEIGHT-VS-ROAD",
                group_id=self.group_id,
                status=status,
                severity="HIGH",
                expected_value={
                    "kind": "NUMERIC_THRESHOLD",
                    "metric": "building_height_m",
                    "operator": "<=",
                    "value": required_max,
                    "unit": "m",
                },
                provided_value={
                    "metric": "building_height_m",
                    "value": provided,
                    "unit": "m",
                },
                explanation_key="HEIGHT_EXCEEDS_ROAD_WIDTH_CAP",
            )
        ]


class GroundCoverageRuleEvaluator(RuleGroupEvaluator):
    group_id = "ground_coverage"

    def evaluate(self, context: ComplianceContext) -> List[RuleEvaluation]:
        if not context.building_ground_coverage_present:
            # Mandatory metric missing for configured limit; treat as ERROR.
            return [
                RuleEvaluation(
                    rule_id="DW3-GC-MISSING-METRIC",
                    group_id=self.group_id,
                    status="ERROR",
                    severity="MEDIUM",
                    expected_value={},
                    provided_value={},
                    explanation_key="GROUND_COVERAGE_METRIC_MISSING",
                )
            ]

        required_max = context.building_ground_coverage_limit_pct
        provided = context.building_ground_coverage_pct
        if provided is None:
            return [
                RuleEvaluation(
                    rule_id="DW3-GC-MISSING-METRIC",
                    group_id=self.group_id,
                    status="ERROR",
                    severity="MEDIUM",
                    expected_value={},
                    provided_value={},
                    explanation_key="GROUND_COVERAGE_METRIC_MISSING",
                )
            ]
        status = "PASS" if provided <= required_max + 1e-4 else "FAIL"
        return [
            RuleEvaluation(
                rule_id="DW3-GC-MAX",
                group_id=self.group_id,
                status=status,
                severity="MEDIUM",
                expected_value={
                    "kind": "NUMERIC_THRESHOLD",
                    "metric": "building_ground_coverage_pct",
                    "operator": "<=",
                    "value": required_max,
                    "unit": "percent",
                },
                provided_value={
                    "metric": "building_ground_coverage_pct",
                    "value": provided,
                    "unit": "percent",
                },
                explanation_key="GROUND_COVERAGE_EXCEEDS_MAX",
            )
        ]


class RuleRegistry:
    """
    Static registry mapping logical rule groups to evaluator instances.
    """

    def __init__(self) -> None:
        self._evaluators: Dict[str, RuleGroupEvaluator] = {
            "fsi": FsiRuleEvaluator(),
            "height": HeightRuleEvaluator(),
            "ground_coverage": GroundCoverageRuleEvaluator(),
        }

    def iter_evaluators(self) -> List[RuleGroupEvaluator]:
        # Deterministic ordering by group_id
        return [self._evaluators[k] for k in sorted(self._evaluators.keys())]


class ComplianceEngine:
    """
    Pure validation layer that operates only on ComplianceContext and
    configuration-derived thresholds. It does not access geometry, layout
    contracts, or YAML directly.
    """

    def __init__(self, registry: RuleRegistry | None = None) -> None:
        self._registry = registry or RuleRegistry()

    def evaluate(self, context: ComplianceContext) -> ComplianceResult:
        # Per-rule evaluation -------------------------------------------------
        rule_results: List[RuleEvaluation] = []
        errors: List[Dict[str, Any]] = []
        for evaluator in self._registry.iter_evaluators():
            try:
                rule_results.extend(evaluator.evaluate(context))
            except Exception as exc:  # noqa: BLE001
                # Fail-safe: capture evaluator error as engine-level error and
                # inject a synthetic ERROR rule so aggregation reflects it.
                errors.append(
                    {
                        "code": "EVALUATOR_EXCEPTION",
                        "group_id": evaluator.group_id,
                        "message": str(exc),
                    }
                )
                rule_results.append(
                    RuleEvaluation(
                        rule_id=f"ENGINE-{evaluator.group_id}-ERROR",
                        group_id=evaluator.group_id,
                        status="ERROR",
                        severity="CRITICAL",
                        expected_value={},
                        provided_value={},
                        explanation_key="ENGINE_EVALUATOR_EXCEPTION",
                    )
                )

        # Deterministic ordering of rules
        ordered_rules = sorted(rule_results, key=lambda r: (r.group_id, r.rule_id))

        # Aggregation and checksums -------------------------------------------
        overall = _aggregate_overall(ordered_rules)
        groups = _aggregate_groups(ordered_rules)

        # Context checksum for audit
        context_canonical = json.dumps(
            asdict(context),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        context_checksum = sha256(context_canonical).hexdigest()

        input_refs: Dict[str, str] = {
            "context_checksum": context_checksum,
            "ruleset_id": context.ruleset_id,
            "ruleset_version": context.ruleset_version,
        }

        engine_meta = {"name": "CGDCRComplianceEngine", "version": "0.1.0"}

        core_payload = {
            "schema_version": "1.0.0",
            "engine": engine_meta,
            "input_refs": input_refs,
            "overall": overall,
            "groups": groups,
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "group_id": r.group_id,
                    "status": r.status,
                    "severity": r.severity,
                    "expected_value": r.expected_value,
                    "provided_value": r.provided_value,
                    "explanation_key": r.explanation_key,
                }
                for r in ordered_rules
            ],
            "errors": errors,
        }

        canonical = json.dumps(
            core_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        result_hash = sha256(canonical).hexdigest()
        generated_at = datetime.now(timezone.utc).isoformat()

        return ComplianceResult(
            schema_version=core_payload["schema_version"],
            engine=engine_meta,
            input_refs=input_refs,
            overall=overall,
            groups=groups,
            rules=ordered_rules,
            errors=errors,
            result_hash=result_hash,
            generated_at=generated_at,
        )


SEVERITY_WEIGHTS: Dict[str, int] = {
    "CRITICAL": 40,
    "HIGH": 25,
    "MEDIUM": 10,
    "LOW": 5,
    "INFO": 0,
}


def _aggregate_overall(rules: List[RuleEvaluation]) -> Dict[str, Any]:
    """
    Deterministic aggregation with precedence:
      ERROR > FAIL > PARTIAL > PASS > NOT_APPLICABLE

    Score:
      - Start from 100, subtract severity-weighted penalties for FAIL rules.
      - If any ERROR, score is None.
    """
    severity_counts: Dict[str, int] = {
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "INFO": 0,
    }
    rule_counts: Dict[str, int] = {
        "total": 0,
        "evaluated": 0,
        "passed": 0,
        "failed": 0,
        "warnings": 0,
        "not_applicable": 0,
        "errors": 0,
    }

    any_error = False
    any_fail_blocking = False
    any_fail_advisory = False

    score = 100.0

    for r in rules:
        rule_counts["total"] += 1
        status = r.status.upper()

        if status in {"PASS", "FAIL", "WARNING"}:
            rule_counts["evaluated"] += 1
        if status == "PASS":
            rule_counts["passed"] += 1
        elif status == "FAIL":
            rule_counts["failed"] += 1
            sev = r.severity.upper()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            score -= SEVERITY_WEIGHTS.get(sev, 0)
            if sev in {"CRITICAL", "HIGH"}:
                any_fail_blocking = True
            else:
                any_fail_advisory = True
        elif status == "WARNING":
            rule_counts["warnings"] += 1
        elif status == "NOT_APPLICABLE":
            rule_counts["not_applicable"] += 1
        elif status == "ERROR":
            rule_counts["errors"] += 1
            any_error = True

    score = max(0.0, min(100.0, score))

    if any_error:
        overall_status = "ERROR"
        overall_score = None
    elif any_fail_blocking:
        overall_status = "FAIL"
        overall_score = score
    elif any_fail_advisory:
        overall_status = "PARTIAL"
        overall_score = score
    elif rule_counts["passed"] > 0:
        overall_status = "PASS"
        overall_score = score
    else:
        overall_status = "NOT_APPLICABLE"
        overall_score = None

    return {
        "status": overall_status,
        "score": overall_score,
        "severity_aggregates": severity_counts,
        "rule_counts": rule_counts,
    }


def _aggregate_groups(rules: List[RuleEvaluation]) -> List[Dict[str, Any]]:
    """
    Group-level aggregation mirroring overall logic but scoped per group_id.
    """
    by_group: Dict[str, List[RuleEvaluation]] = {}
    for r in rules:
        by_group.setdefault(r.group_id, []).append(r)

    groups: List[Dict[str, Any]] = []
    for group_id in sorted(by_group.keys()):
        subset = by_group[group_id]
        overall = _aggregate_overall(subset)
        groups.append(
            {
                "group_id": group_id,
                "title": group_id,
                "status": overall["status"],
                "score": overall["score"],
                "severity_aggregates": overall["severity_aggregates"],
                "rule_ids": [r.rule_id for r in subset],
            }
        )
    return groups

