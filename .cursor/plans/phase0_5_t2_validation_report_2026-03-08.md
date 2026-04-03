# Phase 0.5-T2 Validation Report

Date: 2026-03-08
Profile ID: `tp14_fidelity_v1`
Gate: `G0.5-B`

## 1. Run Metadata
- Input benchmark set: `D:/AI for Architecture/code/backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`
- Run command/config reference: `simulate_tp_batch --fidelity-profile tp14_fidelity_v1 --strict-missing-road-width --benchmark-set ...`
- Raw output CSV: `D:/AI for Architecture/code/backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
- Summary markdown: `D:/AI for Architecture/code/backend/output/benchmark_baseline/tp14_baseline_fidelity_summary_v1.md`

## 2. Completeness Checks
- Expected rows: `24`
- Actual rows: `24`
- Unique `fp_number` count: `24`
- Missing `fp_number`: `[]`
- Duplicate `fp_number`: `[]`
- Result: `PASS`

## 3. Fidelity Metadata Checks
- `fidelity_profile_id` complete: `24/24`
- `road_width_source` complete: `24/24`
- `road_edge_source` complete: `24/24`
- `compliance_pass` complete: `24/24`
- Rows with `fidelity_flag`: `0`
- Result: `PASS`

## 4. Schema Integrity Checks
- Core KPI columns preserved: `PASS`
- Fidelity columns present: `PASS`
- Numeric fields parseability: `PASS` (spot-validated by aggregation script).

## 5. Determinism Checks
- Ordered by numeric `fp_number`: `PASS`
- Reproducibility note captured: `YES`

## 6. KPI Snapshot
- Envelope valid rate: `9/24`
- Placement valid rate: `9/24`
- Compliance pass rate: `9/24`
- Road edge source distribution: `{'ROAD_EDGES_FIELD': 24}`
- Road width source distribution: `{'PLOT_FIELD': 24}`

## 7. Blockers
- None

## 8. Gate Decision
- `G0.5-B = PASS`
- Decision rationale: all critical completeness and fidelity metadata checks passed.