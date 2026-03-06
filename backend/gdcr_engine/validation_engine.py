"""
gdcr_engine.validation_engine
------------------------------

Deterministic validation with full GDCR_DEBUG tracing.

Responsibilities
----------------
- Provide a single entry point for validating a building proposal against
  GDCR rules with step-by-step tracing.
- Format and return a structured GDCR_DEBUG trace string that can be logged
  or printed for debugging and regulatory audit.
- Run parameterised test scenarios to verify compliance engine accuracy.

Usage example
-------------
    from gdcr_engine.validation_engine import validate_proposal, format_debug_report

    result = validate_proposal(
        plot_area_sqm=3678.532,
        road_width_m=60.0,
        building_height_m=42.0,
        total_bua_sqm=14714.128,
        footprint_area_sqm=919.633,
        num_floors=16,
        corridor_eligible=True,
    )
    print(format_debug_report(result))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from gdcr_engine.compliance_engine import (
    ComplianceContext,
    ComplianceReport,
    evaluate_gdcr_compliance,
    PASS, FAIL, INFO, NA, MISSING_DATA,
)
from gdcr_engine.fsi_calculator import (
    compute_fsi_parameters,
    compute_achieved_fsi,
    estimate_bua_from_footprint,
)
from gdcr_engine.setback_calculator import compute_setback_requirements
from gdcr_engine.height_calculator import compute_height_limits

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def validate_proposal(
    *,
    plot_area_sqm: float,
    road_width_m: float,
    building_height_m: float,
    total_bua_sqm: float,
    footprint_area_sqm: float,
    num_floors: int,
    storey_height_m: float = 3.0,
    corridor_eligible: bool = False,
    distance_to_wide_road_m: Optional[float] = None,
    road_margin_provided_m: Optional[float] = None,
    side_margin_provided_m: Optional[float] = None,
    rear_margin_provided_m: Optional[float] = None,
    inter_building_provided_m: Optional[float] = None,
    ground_coverage_pct: Optional[float] = None,
    cop_provided_sqm: Optional[float] = None,
    has_lift: Optional[bool] = None,
    has_basement: bool = False,
    basement_height_m: Optional[float] = None,
    debug: bool = True,
) -> ComplianceReport:
    """
    Validate a building proposal against GDCR rules.

    All area inputs in sq.m, all length inputs in metres.

    Returns a ComplianceReport with per-rule results and debug trace.
    """
    ctx = ComplianceContext(
        plot_area_sqm=plot_area_sqm,
        road_width_m=road_width_m,
        building_height_m=building_height_m,
        total_bua_sqm=total_bua_sqm,
        footprint_area_sqm=footprint_area_sqm,
        num_floors=num_floors,
        storey_height_m=storey_height_m,
        corridor_eligible=corridor_eligible,
        distance_to_wide_road_m=distance_to_wide_road_m,
        road_margin_provided_m=road_margin_provided_m,
        side_margin_provided_m=side_margin_provided_m,
        rear_margin_provided_m=rear_margin_provided_m,
        inter_building_provided_m=inter_building_provided_m,
        ground_coverage_pct=ground_coverage_pct,
        cop_provided_sqm=cop_provided_sqm,
        has_lift=has_lift,
        has_basement=has_basement,
        basement_height_m=basement_height_m,
        debug=debug,
    )
    return evaluate_gdcr_compliance(ctx)


def format_debug_report(report: ComplianceReport) -> str:
    """
    Format a ComplianceReport as a human-readable GDCR_DEBUG report string.

    Example output:
        ============================================================
        GDCR COMPLIANCE REPORT
        ============================================================
        FSI
          base_fsi             = 1.8
          applicable_max_fsi   = 4.0
          achieved_fsi         = 4.0000
          max_fsi_utilization  = 100.00%
          max_bua_applicable   = 14714.1280 sq.m
        ...
    """
    lines = [
        "=" * 60,
        "GDCR COMPLIANCE REPORT",
        "=" * 60,
        "",
        "OVERALL COMPLIANCE",
        f"  compliant          = {report.compliant}",
        f"  total_rules        = {report.total_rules}",
        f"  pass               = {report.pass_count}",
        f"  fail               = {report.fail_count}",
        f"  info               = {report.info_count}",
        f"  na                 = {report.na_count}",
        f"  missing_data       = {report.missing_data_count}",
        "",
        "FSI",
        f"  base_fsi                = {report.base_fsi}",
        f"  applicable_max_fsi      = {report.applicable_max_fsi}",
        f"  achieved_fsi            = {report.achieved_fsi:.4f}",
        f"  max_fsi_utilization_pct = {report.max_fsi_utilization_pct:.2f}%",
        f"  max_bua_applicable_sqm  = {report.max_bua_applicable_sqm:.4f}",
        "",
        "HEIGHT",
        f"  h_road_cap_m        = {report.h_road_cap_m}",
        f"  h_effective_m       = {report.h_effective_m}",
        f"  height_band         = {report.height_band}",
        "",
        "GROUND COVERAGE",
        f"  permissible_gc_pct  = {report.permissible_gc_pct}%",
        f"  achieved_gc_pct     = {report.achieved_gc_pct}%",
        "",
        "COP",
        f"  cop_required_sqm    = {report.cop_required_sqm}",
        f"  cop_provided_sqm    = {report.cop_provided_sqm}",
        "",
        "SETBACK REQUIREMENTS (m)",
    ]
    for dim, req in report.setback_requirements.items():
        lines.append(f"  {dim:<22} = {req:.4f}")

    lines += [
        "",
        "RULE RESULTS",
        f"  {'rule_id':<40} {'status':<14} {'required':>12} {'actual':>12}  note",
        "  " + "-" * 100,
    ]
    for r in report.rule_results:
        req_str = f"{r.required_value:.3f}" if r.required_value is not None else "-"
        act_str = f"{r.actual_value:.3f}" if r.actual_value is not None else "-"
        status_marker = {
            PASS: "[PASS]",
            FAIL: "[FAIL]",
            INFO: "[INFO]",
            NA: "[NA  ]",
            MISSING_DATA: "[MISS]",
        }.get(r.status, f"[{r.status}]")
        note_short = r.note[:80] if r.note else ""
        lines.append(
            f"  {r.rule_id:<40} {status_marker:<14} {req_str:>12} {act_str:>12}  {note_short}"
        )

    if report.debug_trace:
        lines += ["", "DEBUG TRACE", "-" * 60, report.debug_trace]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in test scenarios
# ---------------------------------------------------------------------------

@dataclass
class ValidationScenario:
    """A test scenario for the compliance engine."""
    name: str
    inputs: Dict[str, Any]
    expected_compliant: bool
    expected_achieved_fsi: Optional[float] = None
    fsi_tolerance: float = 0.01
    notes: str = ""


# Standard scenarios from task description and GDCR.yaml values.
STANDARD_SCENARIOS: List[ValidationScenario] = [
    ValidationScenario(
        name="Large plot, 60m road, max FSI corridor",
        inputs=dict(
            plot_area_sqm=3678.532,
            road_width_m=60.0,
            building_height_m=42.0,
            total_bua_sqm=14714.128,   # 3678.532 * 4.0 = 14714.128
            footprint_area_sqm=919.633,
            num_floors=14,
            storey_height_m=3.0,
            corridor_eligible=True,
            ground_coverage_pct=25.0,
            cop_provided_sqm=400.0,
            has_lift=True,
        ),
        expected_compliant=True,
        expected_achieved_fsi=4.0,
        notes="Full FSI utilisation on large plot, 60m road (corridor eligible).",
    ),
    ValidationScenario(
        name="Medium plot, 18m road, no corridor",
        inputs=dict(
            plot_area_sqm=1500.0,
            road_width_m=18.0,
            building_height_m=27.0,
            total_bua_sqm=4050.0,     # 1500 * 2.7 = 4050
            footprint_area_sqm=450.0,
            num_floors=9,
            storey_height_m=3.0,
            corridor_eligible=False,
            ground_coverage_pct=30.0,
            cop_provided_sqm=None,    # Below 2000 sqm threshold
            has_lift=True,
        ),
        expected_compliant=True,
        expected_achieved_fsi=2.7,
        notes="Non-corridor FSI 2.7, road 18m, plot below COP threshold.",
    ),
    ValidationScenario(
        name="Small plot, 9m road, base FSI only",
        inputs=dict(
            plot_area_sqm=400.0,
            road_width_m=9.0,
            building_height_m=10.0,
            total_bua_sqm=720.0,       # 400 * 1.8 = 720
            footprint_area_sqm=180.0,
            num_floors=4,
            storey_height_m=2.5,
            corridor_eligible=False,
            ground_coverage_pct=45.0,  # > 40% — should FAIL gc check
            has_lift=False,
        ),
        expected_compliant=False,  # GC exceeds 40%
        expected_achieved_fsi=1.8,
        notes="Small plot at road edge (9m), GC violation.",
    ),
    ValidationScenario(
        name="FSI overrun violation",
        inputs=dict(
            plot_area_sqm=1000.0,
            road_width_m=18.0,
            building_height_m=30.0,
            total_bua_sqm=4000.0,     # FSI = 4.0, but max is 2.7 (non-corridor)
            footprint_area_sqm=400.0,
            num_floors=10,
            storey_height_m=3.0,
            corridor_eligible=False,
            ground_coverage_pct=40.0,
            has_lift=True,
        ),
        expected_compliant=False,  # FSI 4.0 > max 2.7
        expected_achieved_fsi=4.0,
        notes="FSI exceeds non-corridor maximum.",
    ),
]


def run_standard_scenarios(verbose: bool = True) -> List[Dict[str, Any]]:
    """
    Run all standard validation scenarios and return results.

    Returns a list of dicts: {name, passed, expected, actual, errors}
    """
    outcomes = []

    for scenario in STANDARD_SCENARIOS:
        try:
            report = validate_proposal(**scenario.inputs)

            # Check compliance flag
            compliance_match = report.compliant == scenario.expected_compliant

            # Check achieved FSI (if expected)
            fsi_match = True
            fsi_delta = None
            if scenario.expected_achieved_fsi is not None:
                fsi_delta = abs(report.achieved_fsi - scenario.expected_achieved_fsi)
                fsi_match = fsi_delta <= scenario.fsi_tolerance

            passed = compliance_match and fsi_match
            errors = []
            if not compliance_match:
                errors.append(
                    f"Compliance mismatch: expected {scenario.expected_compliant}, "
                    f"got {report.compliant} (fail_count={report.fail_count})"
                )
            if not fsi_match:
                errors.append(
                    f"FSI mismatch: expected {scenario.expected_achieved_fsi:.4f}, "
                    f"got {report.achieved_fsi:.4f} (delta={fsi_delta:.4f}, "
                    f"tol={scenario.fsi_tolerance})"
                )

            outcome = {
                "name": scenario.name,
                "passed": passed,
                "expected_compliant": scenario.expected_compliant,
                "actual_compliant": report.compliant,
                "expected_fsi": scenario.expected_achieved_fsi,
                "actual_fsi": report.achieved_fsi,
                "errors": errors,
                "fail_rules": [r.rule_id for r in report.rule_results if r.status == FAIL],
                "notes": scenario.notes,
            }

        except Exception as exc:
            outcome = {
                "name": scenario.name,
                "passed": False,
                "errors": [f"Exception: {exc}"],
                "notes": scenario.notes,
            }

        outcomes.append(outcome)

        if verbose:
            status = "PASS" if outcome["passed"] else "FAIL"
            logger.info(
                "VALIDATION_SCENARIO [%s] %s: %s",
                status, scenario.name,
                " | ".join(outcome.get("errors", [])) or "OK",
            )

    return outcomes
