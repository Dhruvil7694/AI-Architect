# Phase 0.5 Gate G0.5-B - Execution Sequence

Date: 2026-03-08
Mode: Execution planning only (no code changes)
Goal: Produce fidelity rerun artifacts and validate Gate G0.5-B deterministically.

## 1. Preconditions

1. `G0.5-A` approved.
2. Fidelity profile spec approved:
- `.cursor/plans/phase0_5_fidelity_profile_spec_2026-03-08.md`
3. Benchmark set frozen:
- `backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`

## 2. Ordered Execution Steps

### Step 1 - Snapshot Inputs

Actions:
1. Record hash/signature or timestamp for:
- benchmark set CSV
- baseline benchmark CSV
2. Record DB context (plot count for TP14 and benchmark id list).

Expected output:
- Input snapshot section in validation report.

Stop condition:
- If benchmark set differs from frozen v1, abort gate run.

### Step 2 - Produce Fidelity Raw CSV

Actions:
1. Execute rerun using fidelity profile `tp14_fidelity_v1`.
2. Ensure per-row fidelity metadata fields are present.
3. Save output to:
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`

Expected output:
- Raw fidelity CSV with exactly 24 rows.

Stop condition:
- If any benchmark plot missing/duplicated, fail gate immediately.

### Step 3 - Generate Fidelity Summary

Actions:
1. Compute summary from fidelity raw CSV.
2. Include mandatory sections:
- envelope/placement/compliance rates
- road-edge source distribution
- road-width source distribution
- top taxonomy categories
3. Save output to:
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_summary_v1.md`

Stop condition:
- If summary counts do not reconcile with raw CSV, fail gate.

### Step 4 - Run Validation Checklist

Actions:
1. Fill template:
- `.cursor/plans/phase0_5_t2_validation_report_template_2026-03-08.md`
2. Save completed report as:
- `.cursor/plans/phase0_5_t2_validation_report_2026-03-08.md`
3. Evaluate sections:
- completeness
- fidelity metadata
- schema integrity
- determinism

Stop condition:
- Any FAIL in sections 2-5 => `G0.5-B = FAIL`.

### Step 5 - Gate Decision

Actions:
1. Declare gate decision in validation report:
- `G0.5-B = PASS/FAIL`
2. If PASS:
- authorize T3 delta/actionability run.
3. If FAIL:
- list blockers with exact `fp_number` rows and remediation path.

## 3. Required Artifacts at Gate End

Mandatory:
1. `backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
2. `backend/output/benchmark_baseline/tp14_baseline_fidelity_summary_v1.md`
3. `.cursor/plans/phase0_5_t2_validation_report_2026-03-08.md`

Optional diagnostics:
1. run log excerpt
2. schema diff note vs baseline raw benchmark CSV

## 4. Pass/Fail Criteria (Strict)

`G0.5-B = PASS` only if all true:
1. 24/24 benchmark rows present exactly once.
2. Fidelity metadata columns complete for all rows.
3. Core KPI schema preserved.
4. Summary metrics match raw CSV.
5. Validation report marks all critical checks PASS.

Else `G0.5-B = FAIL`.

## 5. Handoff to Next Gate

On PASS, start:
- `.cursor/plans/phase0_5_t3_t4_delta_actionability_runbook_2026-03-08.md`

On FAIL, do not start T3/T4.
