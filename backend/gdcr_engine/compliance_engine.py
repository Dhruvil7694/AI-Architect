"""
gdcr_engine.compliance_engine
------------------------------

Full GDCR compliance evaluation pipeline.

Architecture
------------
    1. Accepts a ComplianceContext (all required inputs as a flat dict or
       structured object).
    2. Calls fsi_calculator, setback_calculator, height_calculator for
       deterministic regulatory metric derivation.
    3. Runs all applicable GDCR rules via a structured rule registry.
    4. Returns a ComplianceReport with per-rule results, summary counts,
       and a GDCR_DEBUG trace string.

Design principles
-----------------
    - Pure function: no Django ORM, no side effects.
    - Deterministic: identical inputs always produce identical outputs.
    - All internal calculations in SI units (sq.m, metres).
    - FSI calculations use correct dynamic caps from premium_tiers.
    - COP threshold check included (applies only when plot > 2000 sqm).
    - Missing inputs do not crash the engine; they produce INFO/NA results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from common.units import sqft_to_sqm, sqm_to_sqft

from gdcr_engine.fsi_calculator import (
    compute_fsi_parameters,
    compute_achieved_fsi,
)
from gdcr_engine.setback_calculator import (
    compute_setback_requirements,
    validate_setbacks,
)
from gdcr_engine.height_calculator import (
    compute_height_limits,
    get_height_band,
)
from gdcr_engine.rules_loader import (
    get_gdcr_config,
    get_base_fsi,
    get_max_gc_pct,
    get_cop_config,
    get_min_road_width_dw3,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
INFO = "INFO"
NA = "NA"
MISSING_DATA = "MISSING_DATA"


# ---------------------------------------------------------------------------
# Input/Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ComplianceContext:
    """
    All inputs required for GDCR compliance evaluation.

    Units
    -----
    - Areas: sq.m  (convert from sq.ft using common.units.sqft_to_sqm before passing)
    - Lengths / heights / widths: metres
    - FSI: dimensionless
    - Percentages: 0–100 (not 0–1)

    Optional fields that are None are treated as "not provided" — the engine
    returns INFO or NA for those rules rather than FAIL.
    """

    # Plot
    plot_area_sqm: float
    road_width_m: float

    # Building
    building_height_m: float
    total_bua_sqm: float                    # Gross BUA (before FSI exclusions)
    footprint_area_sqm: float               # Single-tower footprint
    num_floors: int

    # Corridor eligibility
    corridor_eligible: bool = False
    distance_to_wide_road_m: Optional[float] = None

    # Setback dimensions (provided / actual)
    road_margin_provided_m: Optional[float] = None
    side_margin_provided_m: Optional[float] = None
    rear_margin_provided_m: Optional[float] = None
    inter_building_provided_m: Optional[float] = None

    # Ground coverage
    ground_coverage_pct: Optional[float] = None  # footprint / plot_area * 100

    # COP (Common Open Plot)
    cop_provided_sqm: Optional[float] = None

    # Building services
    has_lift: Optional[bool] = None
    has_basement: bool = False
    basement_height_m: Optional[float] = None

    # Staircase
    stair_width_m: Optional[float] = None

    # Storey height (for floor count derivation)
    storey_height_m: float = 3.0

    # Debug
    debug: bool = False


@dataclass
class RuleCheckResult:
    """Result of a single GDCR rule check."""

    rule_id: str
    category: str
    description: str
    status: str                          # PASS | FAIL | INFO | NA | MISSING_DATA
    required_value: Optional[float] = None
    actual_value: Optional[float] = None
    unit: str = ""
    note: str = ""


@dataclass
class ComplianceReport:
    """
    Full GDCR compliance report for a building proposal.
    """

    # Summary
    compliant: bool
    total_rules: int
    pass_count: int
    fail_count: int
    info_count: int
    na_count: int
    missing_data_count: int

    # Derived regulatory metrics (for reporting)
    base_fsi: float
    applicable_max_fsi: float
    achieved_fsi: float
    max_fsi_utilization_pct: float
    max_bua_applicable_sqm: float
    permissible_gc_pct: float
    achieved_gc_pct: Optional[float]
    cop_required_sqm: Optional[float]
    cop_provided_sqm: Optional[float]
    height_band: str
    h_road_cap_m: float
    h_effective_m: float
    setback_requirements: Dict[str, float]  # dimension → required_m

    # Per-rule results (ordered deterministically by rule_id)
    rule_results: List[RuleCheckResult] = field(default_factory=list)

    # Debug trace (GDCR_DEBUG formatted string)
    debug_trace: str = ""


# ---------------------------------------------------------------------------
# Main compliance engine
# ---------------------------------------------------------------------------

def evaluate_gdcr_compliance(ctx: ComplianceContext) -> ComplianceReport:
    """
    Evaluate full GDCR compliance for a building proposal.

    Parameters
    ----------
    ctx : ComplianceContext with all required and optional inputs.

    Returns
    -------
    ComplianceReport with per-rule results and summary.
    """
    debug = ctx.debug
    trace_lines: List[str] = []

    def trace(msg: str) -> None:
        if debug:
            trace_lines.append(msg)
            logger.info("GDCR_DEBUG:%s", msg)

    trace(
        f"EVALUATION_START plot_area_sqm={ctx.plot_area_sqm:.4f}"
        f" road_width_m={ctx.road_width_m:.3f}"
        f" building_height_m={ctx.building_height_m:.3f}"
        f" total_bua_sqm={ctx.total_bua_sqm:.4f}"
        f" footprint_area_sqm={ctx.footprint_area_sqm:.4f}"
        f" num_floors={ctx.num_floors}"
        f" corridor_eligible={ctx.corridor_eligible}"
    )

    # ── Regulatory metric derivation ─────────────────────────────────────────
    fsi_params = compute_fsi_parameters(
        plot_area_sqm=ctx.plot_area_sqm,
        corridor_eligible=ctx.corridor_eligible,
        debug=debug,
    )
    fsi_result = compute_achieved_fsi(
        plot_area_sqm=ctx.plot_area_sqm,
        total_bua_sqm=ctx.total_bua_sqm,
        corridor_eligible=ctx.corridor_eligible,
        debug=debug,
    )
    setbacks = compute_setback_requirements(
        road_width_m=ctx.road_width_m,
        building_height_m=ctx.building_height_m,
        debug=debug,
    )
    height_limits = compute_height_limits(
        road_width_m=ctx.road_width_m,
        plot_area_sqm=ctx.plot_area_sqm,
        footprint_area_sqm=ctx.footprint_area_sqm,
        max_fsi=fsi_params.applicable_max_fsi,
        storey_height_m=ctx.storey_height_m,
        debug=debug,
    )
    height_band = get_height_band(ctx.building_height_m)

    trace(
        f"REGULATORY_METRICS"
        f" base_fsi={fsi_params.base_fsi}"
        f" applicable_max_fsi={fsi_params.applicable_max_fsi}"
        f" achieved_fsi={fsi_result.achieved_fsi:.4f}"
        f" max_bua_applicable_sqm={fsi_params.max_bua_applicable_sqm:.4f}"
        f" h_road_cap_m={height_limits.h_road_cap_m:.4f}"
        f" h_effective_m={height_limits.h_effective_m:.4f}"
        f" height_band={height_band}"
    )

    # ── COP calculation ─────────────────────────────────────────────────────
    cop_cfg = get_cop_config()
    cop_threshold_sqm = float(cop_cfg.get("applies_if_plot_area_above_sqm", 2000.0))
    cop_required_sqm: Optional[float] = None
    if ctx.plot_area_sqm > cop_threshold_sqm:
        cop_fraction = float(cop_cfg.get("required_fraction", 0.10))
        cop_min_sqm = float(cop_cfg.get("minimum_total_area_sqm", 200.0))
        cop_required_sqm = max(ctx.plot_area_sqm * cop_fraction, cop_min_sqm)

    trace(
        f"COP"
        f" threshold_sqm={cop_threshold_sqm}"
        f" cop_required_sqm={cop_required_sqm}"
        f" cop_provided_sqm={ctx.cop_provided_sqm}"
    )

    # ── Rule evaluation ──────────────────────────────────────────────────────
    results: List[RuleCheckResult] = []

    results.extend(_check_access_rules(ctx, debug=debug))
    results.extend(_check_fsi_rules(ctx, fsi_params, fsi_result, debug=debug))
    results.extend(_check_height_rules(ctx, height_limits, debug=debug))
    results.extend(_check_setback_rules(ctx, setbacks, debug=debug))
    results.extend(_check_gc_rules(ctx, debug=debug))
    results.extend(_check_cop_rules(ctx, cop_required_sqm, debug=debug))
    results.extend(_check_service_rules(ctx, debug=debug))
    results.extend(_check_fire_rules(ctx, debug=debug))

    # Deterministic sort by rule_id
    results.sort(key=lambda r: r.rule_id)

    # ── Summary ─────────────────────────────────────────────────────────────
    pass_count = sum(1 for r in results if r.status == PASS)
    fail_count = sum(1 for r in results if r.status == FAIL)
    info_count = sum(1 for r in results if r.status == INFO)
    na_count = sum(1 for r in results if r.status == NA)
    missing_count = sum(1 for r in results if r.status == MISSING_DATA)
    compliant = fail_count == 0

    trace(
        f"SUMMARY total={len(results)}"
        f" pass={pass_count} fail={fail_count} info={info_count}"
        f" na={na_count} missing_data={missing_count}"
        f" compliant={compliant}"
    )

    # ── Debug FSI trace block ────────────────────────────────────────────────
    from gdcr_engine.fsi_calculator import debug_fsi_trace
    fsi_debug_str = debug_fsi_trace(
        plot_area_sqm=ctx.plot_area_sqm,
        road_width_m=ctx.road_width_m,
        max_fsi=fsi_params.applicable_max_fsi,
        total_bua_sqm=ctx.total_bua_sqm,
        achieved_fsi=fsi_result.achieved_fsi,
        max_bua_sqm=fsi_params.max_bua_applicable_sqm,
    )
    full_trace = "\n".join(trace_lines) if trace_lines else ""

    return ComplianceReport(
        compliant=compliant,
        total_rules=len(results),
        pass_count=pass_count,
        fail_count=fail_count,
        info_count=info_count,
        na_count=na_count,
        missing_data_count=missing_count,
        base_fsi=fsi_params.base_fsi,
        applicable_max_fsi=fsi_params.applicable_max_fsi,
        achieved_fsi=fsi_result.achieved_fsi,
        max_fsi_utilization_pct=fsi_result.max_fsi_utilization_pct,
        max_bua_applicable_sqm=fsi_params.max_bua_applicable_sqm,
        permissible_gc_pct=get_max_gc_pct(),
        achieved_gc_pct=ctx.ground_coverage_pct,
        cop_required_sqm=round(cop_required_sqm, 4) if cop_required_sqm is not None else None,
        cop_provided_sqm=ctx.cop_provided_sqm,
        height_band=height_band,
        h_road_cap_m=height_limits.h_road_cap_m,
        h_effective_m=height_limits.h_effective_m,
        setback_requirements={
            "road_margin_m": setbacks.road_margin_required_m,
            "side_margin_m": setbacks.side_margin_required_m,
            "rear_margin_m": setbacks.rear_margin_required_m,
            "inter_building_m": setbacks.inter_building_required_m,
        },
        rule_results=results,
        debug_trace=fsi_debug_str + ("\n\n" + full_trace if full_trace else ""),
    )


# ---------------------------------------------------------------------------
# Rule check helpers
# ---------------------------------------------------------------------------

def _r(rule_id: str, category: str, description: str, status: str,
        required=None, actual=None, unit: str = "", note: str = "") -> RuleCheckResult:
    return RuleCheckResult(
        rule_id=rule_id, category=category, description=description,
        status=status, required_value=required, actual_value=actual,
        unit=unit, note=note,
    )


def _check_access_rules(ctx: ComplianceContext, *, debug: bool) -> List[RuleCheckResult]:
    results = []
    gdcr = get_gdcr_config()
    min_rw = get_min_road_width_dw3()  # 9 m

    # gdcr.access.road_width — minimum road width for DW3
    status = PASS if ctx.road_width_m >= min_rw else FAIL
    results.append(_r(
        "gdcr.access.road_width",
        "access",
        "Minimum road width for DW3 (Apartments) is 9 m.",
        status,
        required=float(min_rw), actual=ctx.road_width_m, unit="m",
        note="" if status == PASS else
        f"Road width {ctx.road_width_m} m < {min_rw} m; DW3 Apartments not permitted.",
    ))

    # gdcr.height.road_dw3 — DW3 height cap when road < 9 m
    if ctx.road_width_m >= min_rw:
        results.append(_r(
            "gdcr.height.road_dw3", "height",
            "If road width < 9 m, DW3 is not permitted and max height is 10 m.",
            NA,
            note=f"Road width {ctx.road_width_m} m >= {min_rw} m; DW3 restriction not triggered.",
        ))
    else:
        cap_h = float(gdcr["access_rules"]["if_road_width_less_than_9"]["max_height"])
        s = PASS if ctx.building_height_m <= cap_h else FAIL
        results.append(_r(
            "gdcr.height.road_dw3", "height",
            "If road width < 9 m, DW3 is not permitted and max height is 10 m.",
            s, required=cap_h, actual=ctx.building_height_m, unit="m",
            note=f"Road width {ctx.road_width_m} m < 9 m: height capped at {cap_h} m.",
        ))

    return results


def _check_fsi_rules(ctx: ComplianceContext, fsi_params, fsi_result,
                     *, debug: bool) -> List[RuleCheckResult]:
    results = []

    # gdcr.fsi.base — informational: exceeding base FSI is allowed when premium
    # FSI is purchased (up to applicable_max_fsi).  This rule signals that
    # premium FSI payment is required; it is not a hard compliance violation.
    if not fsi_result.exceeds_base:
        _base_s = PASS
        _base_note = ""
    elif not fsi_result.exceeds_max:
        # Within applicable max — premium FSI in use, INFO only.
        _base_s = INFO
        _base_note = (
            f"FSI {fsi_result.achieved_fsi:.4f} exceeds base FSI "
            f"{fsi_params.base_fsi} — premium FSI component required. "
            f"Within applicable max {fsi_params.applicable_max_fsi}."
        )
    else:
        # Exceeded both base and applicable max — hard FAIL (also caught by fsi.max).
        _base_s = FAIL
        _base_note = (
            f"FSI {fsi_result.achieved_fsi:.4f} exceeds base FSI "
            f"{fsi_params.base_fsi} and applicable max "
            f"{fsi_params.applicable_max_fsi}."
        )
    results.append(_r(
        "gdcr.fsi.base", "fsi",
        "Base FSI is 1.8; premium FSI component requires payment (up to applicable max).",
        _base_s,
        required=fsi_params.base_fsi, actual=fsi_result.achieved_fsi,
        note=_base_note,
    ))

    # gdcr.fsi.max — uses applicable_max_fsi (accounts for corridor eligibility)
    s = PASS if not fsi_result.exceeds_max else FAIL
    results.append(_r(
        "gdcr.fsi.max", "fsi",
        f"Proposed FSI must not exceed maximum FSI of {fsi_params.applicable_max_fsi}.",
        s,
        required=fsi_params.applicable_max_fsi, actual=fsi_result.achieved_fsi,
        note="" if s == PASS else
        f"FSI {fsi_result.achieved_fsi:.4f} exceeds maximum FSI {fsi_params.applicable_max_fsi}.",
    ))

    # gdcr.fsi.incentive_eligibility — informational
    tiers = fsi_params
    if fsi_params.corridor_eligible:
        results.append(_r(
            "gdcr.fsi.incentive_eligibility", "fsi",
            "Corridor FSI incentive eligibility (road >= 36 m, within 200 m buffer).",
            INFO,
            note=f"Plot is corridor-eligible. Maximum FSI up to {fsi_params.max_fsi_with_corridor} is applicable.",
        ))
    else:
        results.append(_r(
            "gdcr.fsi.incentive_eligibility", "fsi",
            "Corridor FSI incentive eligibility (road >= 36 m, within 200 m buffer).",
            NA,
            note="Plot is not corridor-eligible. Maximum non-corridor FSI applies.",
        ))

    return results


def _check_height_rules(ctx: ComplianceContext, height_limits,
                         *, debug: bool) -> List[RuleCheckResult]:
    results = []

    # gdcr.height.max — road-width cap
    s = PASS if ctx.building_height_m <= height_limits.h_road_cap_m + 1e-6 else FAIL
    results.append(_r(
        "gdcr.height.max", "height",
        "Maximum building height is determined by adjacent road width (Table 6.23).",
        s,
        required=height_limits.h_road_cap_m, actual=ctx.building_height_m, unit="m",
        note="" if s == PASS else
        f"Height {ctx.building_height_m} m exceeds road-width cap {height_limits.h_road_cap_m} m.",
    ))

    return results


def _check_setback_rules(ctx: ComplianceContext, setbacks,
                          *, debug: bool) -> List[RuleCheckResult]:
    results = []

    # gdcr.margin.road_side — road-side (front) margin: max(H/5, table, 1.5)
    road_margin_required = setbacks.road_margin_required_m
    if ctx.road_margin_provided_m is None:
        results.append(_r(
            "gdcr.margin.road_side", "margins",
            "Minimum road-side margin = max(H/5, Table 6.24 value, 1.5 m).",
            INFO,
            required=road_margin_required, unit="m",
            note=(
                f"Required road-side margin for H={ctx.building_height_m} m, "
                f"road={ctx.road_width_m} m: "
                f"{road_margin_required:.3f} m "
                f"[table={setbacks.road_margin_table_m:.3f} m, "
                f"H/5={setbacks.road_margin_height_m:.3f} m]. "
                "Actual margin not provided; confirm in drawing."
            ),
        ))
    else:
        s = PASS if ctx.road_margin_provided_m >= road_margin_required - 1e-6 else FAIL
        results.append(_r(
            "gdcr.margin.road_side", "margins",
            "Minimum road-side margin = max(H/5, Table 6.24 value, 1.5 m).",
            s,
            required=road_margin_required, actual=ctx.road_margin_provided_m, unit="m",
            note="" if s == PASS else
            f"Road-side margin {ctx.road_margin_provided_m:.3f} m < required {road_margin_required:.3f} m.",
        ))

    # gdcr.margin.side_rear — side/rear margins (Table 6.26, height-based)
    side_req = setbacks.side_margin_required_m
    rear_req = setbacks.rear_margin_required_m

    if ctx.side_margin_provided_m is None and ctx.rear_margin_provided_m is None:
        results.append(_r(
            "gdcr.margin.side_rear", "margins",
            "Minimum side/rear margins are determined by building height (Table 6.26).",
            INFO,
            required=side_req, unit="m",
            note=(
                f"Required side and rear margin for H={ctx.building_height_m} m: "
                f"{side_req:.3f} m. Actual margins not provided."
            ),
        ))
    else:
        fails = []
        actuals = []
        if ctx.side_margin_provided_m is not None:
            actuals.append(ctx.side_margin_provided_m)
            if ctx.side_margin_provided_m < side_req - 1e-6:
                fails.append(f"side {ctx.side_margin_provided_m:.3f} m < {side_req:.3f} m")
        if ctx.rear_margin_provided_m is not None:
            actuals.append(ctx.rear_margin_provided_m)
            if ctx.rear_margin_provided_m < rear_req - 1e-6:
                fails.append(f"rear {ctx.rear_margin_provided_m:.3f} m < {rear_req:.3f} m")

        actual_min = min(actuals) if actuals else None
        s = FAIL if fails else PASS
        results.append(_r(
            "gdcr.margin.side_rear", "margins",
            "Minimum side/rear margins are determined by building height (Table 6.26).",
            s,
            required=side_req, actual=actual_min, unit="m",
            note="; ".join(fails) if fails else "",
        ))

    return results


def _check_gc_rules(ctx: ComplianceContext, *, debug: bool) -> List[RuleCheckResult]:
    results = []
    max_gc = get_max_gc_pct()

    if ctx.ground_coverage_pct is None:
        results.append(_r(
            "gdcr.gc.max", "ground_coverage",
            f"Maximum ground coverage for DW3 is {max_gc}% of plot area.",
            INFO,
            required=max_gc, unit="%",
            note=f"Ground coverage not provided. Maximum permissible: {max_gc:.1f}%.",
        ))
    else:
        s = PASS if ctx.ground_coverage_pct <= max_gc + 1e-6 else FAIL
        results.append(_r(
            "gdcr.gc.max", "ground_coverage",
            f"Maximum ground coverage for DW3 is {max_gc}% of plot area.",
            s,
            required=max_gc, actual=ctx.ground_coverage_pct, unit="%",
            note="" if s == PASS else
            f"Ground coverage {ctx.ground_coverage_pct:.2f}% exceeds max {max_gc:.1f}%.",
        ))

    return results


def _check_cop_rules(ctx: ComplianceContext, cop_required_sqm: Optional[float],
                      *, debug: bool) -> List[RuleCheckResult]:
    results = []
    cop_cfg = get_cop_config()
    threshold = float(cop_cfg.get("applies_if_plot_area_above_sqm", 2000.0))

    if ctx.plot_area_sqm <= threshold:
        results.append(_r(
            "gdcr.cop.required", "cop",
            "Common Open Plot (COP) is required when plot area > 2000 sq.m.",
            NA,
            note=f"Plot area {ctx.plot_area_sqm:.2f} sq.m <= {threshold:.0f} sq.m; COP not required.",
        ))
        return results

    # COP required for this plot
    if ctx.cop_provided_sqm is None:
        results.append(_r(
            "gdcr.cop.required", "cop",
            "Common Open Plot (COP) minimum 10% of plot area (or 200 sq.m) required.",
            INFO,
            required=cop_required_sqm, unit="sq.m",
            note=f"COP required: {cop_required_sqm:.2f} sq.m. Actual not provided; confirm in layout.",
        ))
    else:
        s = PASS if ctx.cop_provided_sqm >= (cop_required_sqm or 0.0) - 1e-6 else FAIL
        results.append(_r(
            "gdcr.cop.required", "cop",
            "Common Open Plot (COP) minimum 10% of plot area (or 200 sq.m) required.",
            s,
            required=cop_required_sqm, actual=ctx.cop_provided_sqm, unit="sq.m",
            note="" if s == PASS else
            f"COP provided {ctx.cop_provided_sqm:.2f} sq.m < required {cop_required_sqm:.2f} sq.m.",
        ))

    return results


def _check_service_rules(ctx: ComplianceContext, *, debug: bool) -> List[RuleCheckResult]:
    results = []
    gdcr = get_gdcr_config()
    lift_trigger = float(gdcr["lift_requirement"]["if_height_above"])

    # gdcr.lift.required
    if ctx.building_height_m <= lift_trigger:
        results.append(_r(
            "gdcr.lift.required", "lift",
            f"Lift is mandatory for buildings exceeding {lift_trigger} m.",
            NA,
            note=f"Height {ctx.building_height_m} m <= {lift_trigger} m; lift not mandatory.",
        ))
    elif ctx.has_lift is None:
        results.append(_r(
            "gdcr.lift.required", "lift",
            f"Lift is mandatory for buildings exceeding {lift_trigger} m.",
            INFO, required=1.0,
            note=f"Height {ctx.building_height_m} m > {lift_trigger} m: lift is mandatory. Declare in proposal.",
        ))
    else:
        s = PASS if ctx.has_lift else FAIL
        results.append(_r(
            "gdcr.lift.required", "lift",
            f"Lift is mandatory for buildings exceeding {lift_trigger} m.",
            s, required=1.0, actual=1.0 if ctx.has_lift else 0.0,
            note="" if ctx.has_lift else "Lift required but not declared in proposal.",
        ))

    # gdcr.basement.height
    if not ctx.has_basement:
        results.append(_r(
            "gdcr.basement.height", "basement",
            "Minimum basement clear height is 2.4 m.",
            NA, note="No basement in proposal.",
        ))
    else:
        min_bh = float(gdcr["basement"]["height_min"])
        if ctx.basement_height_m is None:
            results.append(_r(
                "gdcr.basement.height", "basement",
                "Minimum basement clear height is 2.4 m.",
                INFO, required=min_bh, unit="m",
                note=f"Basement declared; height not provided. Required >= {min_bh} m.",
            ))
        else:
            s = PASS if ctx.basement_height_m >= min_bh else FAIL
            results.append(_r(
                "gdcr.basement.height", "basement",
                "Minimum basement clear height is 2.4 m.",
                s, required=min_bh, actual=ctx.basement_height_m, unit="m",
            ))

    return results


def _check_fire_rules(ctx: ComplianceContext, *, debug: bool) -> List[RuleCheckResult]:
    results = []
    gdcr = get_gdcr_config()

    # gdcr.fire.noc — NOC required above 15 m
    fire_noc_trigger = float(gdcr["fire_safety"]["fire_noc_required_if_height_above"])
    if ctx.building_height_m <= fire_noc_trigger:
        results.append(_r(
            "gdcr.fire.noc", "fire",
            "Fire NOC required for buildings exceeding 15 m.",
            NA, note=f"Height {ctx.building_height_m} m <= {fire_noc_trigger} m; fire NOC not required.",
        ))
    else:
        results.append(_r(
            "gdcr.fire.noc", "fire",
            "Fire NOC required for buildings exceeding 15 m.",
            INFO,
            note=f"Height {ctx.building_height_m} m > {fire_noc_trigger} m: Fire NOC required before construction.",
        ))

    # gdcr.fire.refuge_area — refuge area above 25 m
    refuge_trigger = float(gdcr["fire_safety"]["refuge_area_if_height_above"])
    if ctx.building_height_m <= refuge_trigger:
        results.append(_r(
            "gdcr.fire.refuge_area", "fire",
            "Refuge area mandatory for buildings exceeding 25 m.",
            NA, note=f"Height {ctx.building_height_m} m <= {refuge_trigger} m; refuge area not triggered.",
        ))
    else:
        results.append(_r(
            "gdcr.fire.refuge_area", "fire",
            "Refuge area mandatory for buildings exceeding 25 m.",
            INFO,
            note=f"Height {ctx.building_height_m} m > {refuge_trigger} m: Refuge area is mandatory.",
        ))

    return results
