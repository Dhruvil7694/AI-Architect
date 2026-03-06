"""
architecture.feasibility.validation
-------------------------------------

Validation matrix for Part 7: compare FeasibilityAggregate outputs
against expected values (e.g. manual GDCR calculations) with defined
tolerances. Used to ensure engine matches GDCR math exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Tolerances (from feasibility plan)
TOLERANCE_FSI = 0.01
TOLERANCE_GC_PCT = 0.5
TOLERANCE_COP_PCT = 0.5
TOLERANCE_FRONTAGE_M = 0.1
# Height band: exact match (string)


@dataclass
class ValidationCheck:
    """Single metric check result."""
    metric: str
    expected: Optional[float | str]
    actual: Optional[float | str]
    passed: bool
    message: str


def _cop_pct(provided_sqft: float, required_sqft: float) -> float:
    if required_sqft <= 0:
        return 0.0
    return 100.0 * provided_sqft / required_sqft


def validate_aggregate_against_expected(
    agg,
    *,
    expected_fsi: Optional[float] = None,
    expected_gc_pct: Optional[float] = None,
    expected_cop_pct: Optional[float] = None,
    expected_frontage_m: Optional[float] = None,
    expected_height_band: Optional[str] = None,
) -> list[ValidationCheck]:
    """
    Compare FeasibilityAggregate to expected values. Only checks that are
    provided (non-None) are run. Returns a list of ValidationCheck.
    """
    checks: list[ValidationCheck] = []
    rm = agg.regulatory_metrics
    pm = agg.plot_metrics

    if expected_fsi is not None:
        actual = rm.achieved_fsi
        passed = abs(actual - expected_fsi) <= TOLERANCE_FSI
        checks.append(ValidationCheck(
            metric="FSI",
            expected=expected_fsi,
            actual=actual,
            passed=passed,
            message=f"expected {expected_fsi:.4f}, got {actual:.4f} (tol ±{TOLERANCE_FSI})",
        ))

    if expected_gc_pct is not None:
        actual = rm.achieved_gc_pct
        passed = abs(actual - expected_gc_pct) <= TOLERANCE_GC_PCT
        checks.append(ValidationCheck(
            metric="GC_pct",
            expected=expected_gc_pct,
            actual=actual,
            passed=passed,
            message=f"expected {expected_gc_pct:.2f}%, got {actual:.2f}% (tol ±{TOLERANCE_GC_PCT})",
        ))

    if expected_cop_pct is not None:
        actual = _cop_pct(rm.cop_provided_sqft, rm.cop_required_sqft)
        passed = abs(actual - expected_cop_pct) <= TOLERANCE_COP_PCT
        checks.append(ValidationCheck(
            metric="COP_pct",
            expected=expected_cop_pct,
            actual=actual,
            passed=passed,
            message=f"expected {expected_cop_pct:.2f}%, got {actual:.2f}% (tol ±{TOLERANCE_COP_PCT})",
        ))

    if expected_frontage_m is not None:
        actual = pm.frontage_length_m
        passed = abs(actual - expected_frontage_m) <= TOLERANCE_FRONTAGE_M
        checks.append(ValidationCheck(
            metric="frontage_m",
            expected=expected_frontage_m,
            actual=actual,
            passed=passed,
            message=f"expected {expected_frontage_m:.2f}m, got {actual:.2f}m (tol ±{TOLERANCE_FRONTAGE_M})",
        ))

    if expected_height_band is not None:
        actual = pm.height_band_label
        passed = (actual == expected_height_band)
        checks.append(ValidationCheck(
            metric="height_band",
            expected=expected_height_band,
            actual=actual,
            passed=passed,
            message=f"expected {expected_height_band}, got {actual}",
        ))

    return checks


def validate_aggregate_against_expected_json(agg, expected_dict: dict) -> list[ValidationCheck]:
    """
    Validate FeasibilityAggregate against an expected JSON structure.

    Expected dict may contain (all optional):
      - fsi_achieved       : float (tolerance ± TOLERANCE_FSI)
      - gc_achieved_pct    : float (tolerance ± TOLERANCE_GC_PCT)
      - cop_provided_pct   : float = 100 * (provided_sqft / required_sqft) (tolerance ± TOLERANCE_COP_PCT)
      - height_band        : str (exact match)

    Reference-only keys (no check): fsi_max, gc_permissible_pct, cop_required_pct.

    Returns
    -------
    list[ValidationCheck] — one per metric checked; .passed True/False per metric.
    """
    expected_fsi = expected_dict.get("fsi_achieved")
    expected_gc_pct = expected_dict.get("gc_achieved_pct")
    expected_cop_pct = expected_dict.get("cop_provided_pct")
    expected_height_band = expected_dict.get("height_band")
    return validate_aggregate_against_expected(
        agg,
        expected_fsi=expected_fsi,
        expected_gc_pct=expected_gc_pct,
        expected_cop_pct=expected_cop_pct,
        expected_height_band=expected_height_band,
    )


def load_expected_csv(path: str) -> dict[str, dict]:
    """
    Load expected values from a CSV file.

    Expected columns: fp_number, expected_fsi, expected_gc_pct, expected_cop_pct,
    expected_frontage_m, expected_height_band. All except fp_number are optional;
    empty or missing means skip that check for that row.

    Returns
    -------
    dict mapping fp_number (str) -> dict of optional expected values (floats/str).
    """
    import csv
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fp = (row.get("fp_number") or "").strip()
            if not fp:
                continue
            expected = {}
            for key, col in [
                ("expected_fsi", "expected_fsi"),
                ("expected_gc_pct", "expected_gc_pct"),
                ("expected_cop_pct", "expected_cop_pct"),
                ("expected_frontage_m", "expected_frontage_m"),
                ("expected_height_band", "expected_height_band"),
            ]:
                val = (row.get(col) or "").strip()
                if not val:
                    continue
                if key == "expected_height_band":
                    expected["expected_height_band"] = val
                else:
                    try:
                        expected[col] = float(val)
                    except ValueError:
                        continue
            out[fp] = expected
    return out
