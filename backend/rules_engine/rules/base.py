"""
rules/base.py
-------------
Core dataclasses shared by the entire rules engine.

Rule        — static descriptor loaded from YAML (what the regulation says).
RuleResult  — dynamic outcome produced by evaluating a Rule against inputs.

Status values
-------------
PASS         — actual value satisfies the regulation threshold.
FAIL         — actual value violates the regulation threshold.
INFO         — rule is a trigger / declaration requirement, not a numeric check;
               result tells the architect what action is required.
NA           — rule is not applicable given the current proposal parameters
               (e.g. refuge area rule when height <= 25 m).
MISSING_DATA — one or more required inputs were not provided; cannot evaluate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Status constants ──────────────────────────────────────────────────────────
PASS         = "PASS"
FAIL         = "FAIL"
INFO         = "INFO"
NA           = "NA"
MISSING_DATA = "MISSING_DATA"

ALL_STATUSES = (PASS, FAIL, INFO, NA, MISSING_DATA)


@dataclass
class Rule:
    """
    Static descriptor of a single regulation clause.

    Attributes
    ----------
    rule_id         : unique dot-separated identifier, e.g. "gdcr.fsi.base"
    source          : "GDCR" | "NBC"
    category        : broad grouping, e.g. "fsi", "height", "margins", "fire"
    description     : human-readable clause text
    required_inputs : list of input dict keys needed to evaluate this rule;
                      if any are absent the result is MISSING_DATA
    """

    rule_id: str
    source: str
    category: str
    description: str
    required_inputs: List[str] = field(default_factory=list)


@dataclass
class RuleResult:
    """
    Dynamic outcome of evaluating a Rule against a set of building inputs.

    Attributes
    ----------
    rule_id         : matches Rule.rule_id
    source          : "GDCR" | "NBC"
    category        : matches Rule.category
    description     : matches Rule.description
    status          : one of PASS / FAIL / INFO / NA / MISSING_DATA
    required_value  : the regulation limit / threshold (None if not numeric)
    actual_value    : the value computed from the proposal inputs (None if N/A)
    unit            : display unit string, e.g. "m", "sq.ft", "%"
    note            : additional human-readable context
    """

    rule_id: str
    source: str
    category: str
    description: str
    status: str
    required_value: Optional[float] = None
    actual_value: Optional[float] = None
    unit: str = ""
    note: str = ""
