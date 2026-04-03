# Phase 0.5-T3/T4 Delta + Actionability Runbook (Planning Only)

Date: 2026-03-08
Status: Ready for execution after G0.5-B

## 1. Objective

1. Compute baseline-vs-fidelity taxonomy delta per plot.
2. Classify each plot into a single actionability class.
3. Freeze `actionable_plot_set_v1.csv` for Phase 1.

## 2. Required Inputs

- `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
- `.cursor/plans/phase0_5_per_plot_taxonomy_2026-03-08.csv`

## 3. Delta Rules

For each `fp_number`, compute:
- `baseline_taxonomy_code`
- `fidelity_taxonomy_code`
- `status_changed` (`Y/N`)
- `change_driver`

Change driver mapping:
- `ROAD_WIDTH_SOURCE`: if status/taxonomy change aligns with road-width source change.
- `ROAD_EDGE_SOURCE`: if status/taxonomy change aligns with edge-source change.
- `OTHER`: remaining changes.

## 4. Actionability Classification Rules

Assign exactly one class:
1. `NON_ACTIONABLE_REGULATORY`
2. `ACTIONABLE_ENVELOPE`
3. `ACTIONABLE_PLACEMENT`
4. `ACTIONABLE_COMPLIANCE_CHAIN`
5. `REVIEW_REQUIRED`

Default guidance:
- Persistent collapse/too-small after fidelity correction -> `NON_ACTIONABLE_REGULATORY` unless evidence indicates geometry algorithm artifact.
- `VALID envelope + NO_FIT/TOO_TIGHT/NO_FIT_CORE` -> `ACTIONABLE_PLACEMENT`.
- `VALID envelope + VALID placement + NON-COMPLIANT` -> `ACTIONABLE_COMPLIANCE_CHAIN`.
- Ambiguous patterns -> `REVIEW_REQUIRED`.

## 5. Planned Outputs

- `.cursor/plans/phase0_5_taxonomy_delta_2026-03-08.csv`
- `.cursor/plans/phase0_5_actionability_split_2026-03-08.csv`
- `.cursor/plans/phase0_5_delta_analysis_2026-03-08.md`
- `backend/output/benchmark_baseline/actionable_plot_set_v1.csv`
- `.cursor/plans/phase1_input_contract_from_p0_5_2026-03-08.md`

## 6. Actionable Set Freeze Rules (T4)

1. Include all `ACTIONABLE_ENVELOPE` and `ACTIONABLE_PLACEMENT`.
2. Include at least 3 `PIPELINE_PASS` controls.
3. Maintain cohort diversity:
- small/medium/large
- regular/irregular
- thin/road-sensitive
4. Include per-plot rationale field.

## 7. Gate Decisions

Gate G0.5-C pass if:
- Delta and actionability files cover all 24 plots with exactly one class each.

Gate G0.5-D pass if:
- `actionable_plot_set_v1.csv` frozen and Phase 1 input contract published.

No Phase 1 implementation before G0.5-D.
