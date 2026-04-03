# TP14 Baseline Benchmark Summary (v1)

- Source raw: `backend/output/benchmark_baseline/tp14_baseline_raw_all.csv`
- Benchmark set: `backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`
- Filtered output: `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`
- Benchmark plots: **24**

## KPI Snapshot
- Envelope valid rate: **8/24** (33.3%)
- Placement valid rate: **6/24** (25.0%)
- Placement too-tight rate: **0/24** (0.0%)
- Compliance pass rate: **0/24** (0.0%)
- Median fsi_achieved: **1.684**
- Median gc_achieved_pct: **33.680%**

## Top Failure Reasons
- 9x: Envelope collapsed due to mandatory setback depth
- 7x: Envelope area below minimum usable threshold
- 2x: Placement failed inside feasible envelope

## Notes
- Failure reasons are normalized to decision-level categories for architecture triage.
- Status interpretation uses strict label matching (`VALID/PASS/OK/TRUE/Y`); empty status is non-pass.