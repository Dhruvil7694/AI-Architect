# Phase 0 Execution Checklist

Date started: 2026-03-08
Owner: Architecture AI backend team
Scope: Phase 0 only (baseline lock + measurement)

Reference plan:
- .cursor/plans/backend-algorithm-gap-closure-plan_2026-03-08.plan.md

## Current Status
- [x] P0-DISC-1 Inventory existing simulation/diagnostic commands.
- [x] P0-DISC-2 Verify source data availability under `tp_data/pal/tp14`.
- [x] P0-T1 Define benchmark plot set.
- [x] P0-T2 Baseline runner definition and command wrapper strategy.
- [x] P0-T3 KPI schema freeze.
- [x] P0-T4 Baseline artifact generation.

## Discovery Notes (Completed)
1. Existing batch runner for many plots:
- `backend/architecture/management/commands/simulate_tp_batch.py`
2. Existing single-plot end-to-end command:
- `backend/architecture/management/commands/simulate_project_proposal.py`
3. Existing development optimizer command:
- `backend/architecture/management/commands/simulate_optimal_development.py`
4. Data observed:
- `tp_data/pal/tp14/TP14  PLAN NO.3.dxf`
- `tp_data/pal/tp14/TP14_Scheme_English.csv`

## Decision for P0-T2
Use existing `simulate_tp_batch` as the baseline runner for Phase 0.
Do not create a new benchmark command in Phase 0 unless missing KPI fields are blocking.

## P0-T1 - Benchmark Plot Set Definition (Completed)
Selection targets:
- 4 regular-ish plots (rectangular / compact)
- 4 irregular plots (concave / non-orthogonal)
- 4 small area plots (stress density limits)
- 4 medium plots
- 4 large plots
- 4 road-sensitive cases (different road_width_m / frontage)
- 4 likely challenging geometry cases (thin/deep / narrow frontage)

Minimum benchmark size target: 24 plots.
Stretch target: 36 plots.

Selection constraints:
- All selected plots must have usable `geom` and `road_width_m`.
- Include at least 8 from TP14 core range known to run through pipeline.
- Keep list deterministic and versioned.

Output file:
- `backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`
  columns:
  - tp_scheme
  - fp_number
  - cohort_label
  - rationale

## P0-T3 - KPI Schema Freeze (Completed)
Mandatory KPIs per plot:
- envelope_status
- placement_status
- compliance_status
- fsi_achieved
- fsi_max
- gc_achieved_pct
- gc_permissible_pct
- cop_provided_sqft
- cop_required_sqft
- storey_height_used_m
- num_floors_estimated
- footprint_width_m
- footprint_depth_m
- efficiency_pct
- fallback_road_used
- error

Derived baseline metrics to aggregate:
- compliance pass rate
- median fsi_achieved
- median gc_achieved_pct
- error/failure reason counts

## P0-T4 - Baseline Artifact Plan
Primary raw run output:
- `backend/output/benchmark_baseline/tp14_baseline_raw_all.csv`
- `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`

Summary report output:
- `backend/output/benchmark_baseline/tp14_baseline_summary.md`

Repro command template:
- `python manage.py simulate_tp_batch --tp 14 --height 16.5 --road-width 12.0 --output output/benchmark_baseline/tp14_baseline_raw_all.csv`

## Phase 0 Completion Notes
1. Baseline run executed across all TP14 plots and persisted.
2. Benchmark subset (24 plots) extracted to versioned CSV.
3. KPI summary generated at:
- `backend/output/benchmark_baseline/tp14_baseline_summary.md`

## Phase 0.5 (Pre-Phase-1 Fidelity Gate)
Reference:
- `.cursor/plans/phase0_5_algorithm_gap_validation_2026-03-08.md`
- `.cursor/plans/phase0_5_fidelity_gate_execution_plan_2026-03-08.md`

Status:
- [x] P0.5-A Baseline gap validation and taxonomy v1 complete.
- [x] P0.5-T1 Fidelity profile specification (approved, Gate G0.5-A passed).
- [x] P0.5-T2 Fidelity rerun on benchmark v1 (Gate G0.5-B passed).
- [x] P0.5-T3 Taxonomy delta + actionability split (Gate G0.5-C passed).
- [x] P0.5-T4 Freeze actionable_plot_set_v1 and Phase 1 input contract (Gate G0.5-D passed).

P0.5-T1 draft:
- `.cursor/plans/phase0_5_fidelity_profile_spec_2026-03-08.md`

P0.5-T2 runbook:
- `.cursor/plans/phase0_5_t2_fidelity_rerun_runbook_2026-03-08.md`
- `.cursor/plans/phase0_5_t2_validation_report_template_2026-03-08.md`
- `.cursor/plans/phase0_5_g0_5_b_execution_sequence_2026-03-08.md`

P0.5-T3/T4 runbook:
- `.cursor/plans/phase0_5_t3_t4_delta_actionability_runbook_2026-03-08.md`
- `.cursor/plans/phase0_5_taxonomy_delta_template_2026-03-08.csv`
- `.cursor/plans/phase0_5_actionability_split_template_2026-03-08.csv`
- `.cursor/plans/phase1_input_contract_template_from_p0_5_2026-03-08.md`

Completed P0.5 output artifacts:
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_summary_v1.md`
- `.cursor/plans/phase0_5_t2_validation_report_2026-03-08.md`
- `.cursor/plans/phase0_5_taxonomy_delta_2026-03-08.csv`
- `.cursor/plans/phase0_5_actionability_split_2026-03-08.csv`
- `.cursor/plans/phase0_5_delta_analysis_2026-03-08.md`
- `backend/output/benchmark_baseline/actionable_plot_set_v1.csv`
- `.cursor/plans/phase1_input_contract_from_p0_5_2026-03-08.md`
