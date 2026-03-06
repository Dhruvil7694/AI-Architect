"""
services/report.py
------------------
Formats the list of RuleResult objects into a human-readable compliance report.

Two output formats are provided:
  print_report()  — prints an ASCII table to stdout (used by the management command)
  as_dict()       — returns a structured dict (useful for future API/JSON output)

Summary line counts:
  PASS, FAIL, INFO (declarations needed), NA (not applicable), MISSING_DATA
"""

from __future__ import annotations

from typing import Dict, List

from rules_engine.rules.base import FAIL, INFO, MISSING_DATA, NA, PASS, RuleResult

# Column widths for the ASCII table
_W_ID    = 38
_W_STAT  = 13
_W_REQ   = 10
_W_ACT   = 10
_W_UNIT  = 7
_W_NOTE  = 52

_HEADER = (
    f"{'Rule ID':<{_W_ID}} "
    f"{'Status':<{_W_STAT}} "
    f"{'Required':>{_W_REQ}} "
    f"{'Actual':>{_W_ACT}} "
    f"{'Unit':<{_W_UNIT}} "
    f"Note"
)
_SEP = "-" * (_W_ID + _W_STAT + _W_REQ + _W_ACT + _W_UNIT + _W_NOTE + 5)

# Status colour/symbol markers (plain text — works on all terminals)
_STATUS_ICON = {
    PASS:         "[PASS]",
    FAIL:         "[FAIL]",
    INFO:         "[INFO]",
    NA:           "[ NA ]",
    MISSING_DATA: "[MISS]",
}


def _fmt_val(val, decimals: int = 3) -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.{decimals}f}"
    return str(val)


def _row(r: RuleResult) -> str:
    icon = _STATUS_ICON.get(r.status, f"[{r.status[:4]}]")
    note = (r.note or "")[:_W_NOTE]
    return (
        f"{r.rule_id:<{_W_ID}} "
        f"{icon:<{_W_STAT}} "
        f"{_fmt_val(r.required_value):>{_W_REQ}} "
        f"{_fmt_val(r.actual_value):>{_W_ACT}} "
        f"{(r.unit or ''):<{_W_UNIT}} "
        f"{note}"
    )


def _section_header(title: str) -> str:
    bar = "-" * len(_SEP)
    return f"\n{bar}\n  {title}\n{bar}"


def print_report(results: List[RuleResult],
                 title: str = "Compliance Report",
                 show_na: bool = False,
                 show_missing: bool = True) -> None:
    """
    Print a formatted compliance table to stdout.

    Parameters
    ----------
    results      : list of RuleResult from evaluator.evaluate_all()
    title        : header string (e.g. "FP 101 — TP14 Surat")
    show_na      : include NA rows in the output (default False — reduces noise)
    show_missing : include MISSING_DATA rows (default True)
    """
    print(f"\n{'=' * len(_SEP)}")
    print(f"  {title}")
    print(f"{'=' * len(_SEP)}\n")

    # Group by source (GDCR first, NBC second) then by category
    gdcr_results = [r for r in results if r.source == "GDCR"]
    nbc_results  = [r for r in results if r.source == "NBC"]

    for source_label, group in [("GDCR Rules", gdcr_results), ("NBC Rules (Part 4)", nbc_results)]:
        print(_section_header(source_label))
        print(_HEADER)
        print(_SEP)

        categories: Dict[str, List[RuleResult]] = {}
        for r in group:
            categories.setdefault(r.category, []).append(r)

        for cat, cat_results in categories.items():
            for r in cat_results:
                if r.status == NA and not show_na:
                    continue
                if r.status == MISSING_DATA and not show_missing:
                    continue
                print(_row(r))

        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    pass_n  = sum(1 for r in results if r.status == PASS)
    fail_n  = sum(1 for r in results if r.status == FAIL)
    info_n  = sum(1 for r in results if r.status == INFO)
    na_n    = sum(1 for r in results if r.status == NA)
    miss_n  = sum(1 for r in results if r.status == MISSING_DATA)

    print(f"{'=' * len(_SEP)}")
    print(f"  SUMMARY  |  PASS: {pass_n}  |  FAIL: {fail_n}  |  INFO: {info_n}  "
          f"|  NA: {na_n}  |  MISSING DATA: {miss_n}")
    print(f"{'=' * len(_SEP)}\n")

    if fail_n:
        print("FAIL items require design changes before submission:\n")
        for r in results:
            if r.status == FAIL:
                print(f"  • {r.rule_id}: {r.note or r.description}")
        print()

    if info_n:
        print("INFO items require declarations / provisions in the drawing set:\n")
        for r in results:
            if r.status == INFO:
                print(f"  • {r.rule_id}: {r.note or r.description}")
        print()


def as_dict(results: List[RuleResult]) -> dict:
    """
    Return a structured dict representation of the compliance results.
    Suitable for JSON serialisation (future API endpoint).
    """
    pass_n  = sum(1 for r in results if r.status == PASS)
    fail_n  = sum(1 for r in results if r.status == FAIL)
    info_n  = sum(1 for r in results if r.status == INFO)
    na_n    = sum(1 for r in results if r.status == NA)
    miss_n  = sum(1 for r in results if r.status == MISSING_DATA)

    return {
        "summary": {
            "total":        len(results),
            "pass":         pass_n,
            "fail":         fail_n,
            "info":         info_n,
            "na":           na_n,
            "missing_data": miss_n,
            "compliant":    fail_n == 0,
        },
        "results": [
            {
                "rule_id":        r.rule_id,
                "source":         r.source,
                "category":       r.category,
                "description":    r.description,
                "status":         r.status,
                "required_value": r.required_value,
                "actual_value":   r.actual_value,
                "unit":           r.unit,
                "note":           r.note,
            }
            for r in results
        ],
    }
