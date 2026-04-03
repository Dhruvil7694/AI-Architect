# Phase 0.5-T2 Fidelity Rerun Runbook (Planning Only)

Date: 2026-03-08
Status: Ready for execution
Depends on: `phase0_5_fidelity_profile_spec_2026-03-08.md` (Approved)

## 1. Objective

Re-run the same TP14 benchmark plot set under fidelity profile `tp14_fidelity_v1` and produce comparable artifacts for delta analysis.

## 2. Scope and Constraints

1. No algorithm changes.
2. Same benchmark set (24 plots) only.
3. Deterministic plot ordering by `fp_number`.
4. Preserve existing KPI schema; add fidelity metadata columns only.

## 3. Input Artifacts

- `backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`
- `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv` (baseline reference)
- `.cursor/plans/phase0_5_fidelity_profile_spec_2026-03-08.md`

## 4. Planned Output Artifacts

Primary outputs:
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_summary_v1.md`

Validation outputs:
- `.cursor/plans/phase0_5_t2_validation_report_2026-03-08.md`

## 5. Output Schema Contract

Core columns:
- Keep all columns present in `tp14_baseline_raw_benchmark_v1.csv`.

Additional fidelity columns (mandatory):
- `fidelity_profile_id`
- `road_width_source` (`PLOT_FIELD` | `MISSING`)
- `road_edge_source` (`ROAD_LAYER_INTERSECTION` | `FALLBACK_LONGEST_EDGE`)
- `fidelity_flag` (nullable)
- `compliance_pass` (`Y/N`)

## 6. Run Validation Checklist

### 6.1 Completeness
- [ ] Exactly 24 rows present.
- [ ] Every benchmark `fp_number` appears exactly once.

### 6.2 Fidelity Fields
- [ ] `fidelity_profile_id` populated for all rows (`tp14_fidelity_v1`).
- [ ] `road_width_source` populated for all rows.
- [ ] `road_edge_source` populated for all rows.
- [ ] `compliance_pass` populated for all rows.

### 6.3 Schema Integrity
- [ ] No core KPI field dropped.
- [ ] Numeric fields remain numeric-compatible.

### 6.4 Determinism
- [ ] Row order sorted by `fp_number`.
- [ ] Re-run reproducibility note captured.

## 7. Summary Report Contract

`tp14_baseline_fidelity_summary_v1.md` must include:
1. row count and benchmark coverage
2. envelope valid rate
3. placement valid rate
4. compliance pass rate (`COMPLIANT`-normalized)
5. road-edge source distribution
6. road-width source distribution
7. top taxonomy categories

## 8. Gate Decision (G0.5-B)

Pass G0.5-B only if:
1. All 24 plots processed with complete fidelity metadata.
2. Summary report generated and internally consistent with CSV counts.
3. Validation report marked green for sections 6.1-6.4.

If any check fails:
- Mark gate as blocked.
- Record blocker in validation report with exact failing row ids.
