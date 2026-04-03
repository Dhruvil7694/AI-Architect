# Phase 0.5 Fidelity Gate - Detailed Execution Plan

Date: 2026-03-08
Owner: Architecture AI backend team
Status: Ready for execution (planning only)
Scope: Lock benchmark fidelity and isolate truly actionable algorithm gaps before Phase 1.

Reference artifacts:
- `.cursor/plans/phase0_5_algorithm_gap_validation_2026-03-08.md`
- `.cursor/plans/phase0_5_per_plot_taxonomy_2026-03-08.csv`
- `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`

---

## 1. Why This Gate Exists

Current benchmark evidence confirms two gap layers:
1. Harness fidelity risk:
- Uniform `--road-width` applied to all plots.
- Road-edge detection fallback used in all benchmark rows.
2. Core algorithm limitations:
- Envelope survivability for thin/irregular plots.
- Placement feasibility on constrained envelopes.

Phase 1 algorithm upgrades must be measured on a high-fidelity baseline, otherwise improvements cannot be trusted.

---

## 2. Execution Rules

1. No random exploration: every run maps to a predefined artifact.
2. Do not start Phase 1 until all P0.5 acceptance checks pass.
3. Keep benchmark plot set fixed (`benchmark_plot_set_v1.csv`) during P0.5.
4. Use deterministic ordering and stable taxonomy labels.

---

## 3. Task Breakdown (Detailed)

### P0.5-T1 - Define Fidelity Profile

Goal:
- Specify benchmark run profile that removes known harness bias.

Inputs:
- `tp_data/pal/tp14/*`
- `Plot.road_width_m` values in DB
- Existing benchmark set (`benchmark_plot_set_v1.csv`)

Required profile decisions:
1. Road width source:
- Primary: per-plot `Plot.road_width_m`.
- Fallback: explicit policy when missing (`SKIP` or `DEFAULT_WITH_FLAG`).
2. Road edge source:
- Primary: explicit road geometry layer/queryset.
- Fallback: longest-edge heuristic allowed only when policy permits and must be flagged.
3. Compliance status normalization:
- Pass token = `COMPLIANT` only for this pipeline output.

Outputs:
- `.cursor/plans/phase0_5_fidelity_profile_spec_2026-03-08.md`

Acceptance:
- Spec defines exact field mappings, fallback policy, and pass/fail token semantics.
- Spec includes reproducibility section (seed/order/input files).

---

### P0.5-T2 - Re-run Benchmark Under Fidelity Profile

Goal:
- Produce a second baseline on same 24 plots with corrected fidelity assumptions.

Run contract:
1. Generate fidelity run CSV with same schema as baseline plus fidelity metadata fields.
2. Maintain identical plot ordering by `fp_number`.
3. Capture run metadata:
- timestamp
- command/config
- data source ids

Outputs:
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
- `backend/output/benchmark_baseline/tp14_baseline_fidelity_summary_v1.md`

Acceptance:
- 24/24 rows present.
- No schema drift in core KPI columns.
- Fidelity metadata columns populated for every row.

---

### P0.5-T3 - Taxonomy Delta and Actionability Split

Goal:
- Separate truly non-actionable (hard regulatory infeasible) cases from algorithm-actionable cases.

Method:
1. Compare baseline v1 vs fidelity v1 taxonomy per `fp_number`.
2. Identify status flips caused by fidelity changes:
- `COLLAPSED/TOO_SMALL -> VALID`
- `NO_FIT -> VALID`
3. Mark actionability:
- `NON_ACTIONABLE_REGULATORY`
- `ACTIONABLE_ENVELOPE`
- `ACTIONABLE_PLACEMENT`
- `ACTIONABLE_COMPLIANCE_CHAIN`
- `REVIEW_REQUIRED`

Outputs:
- `.cursor/plans/phase0_5_taxonomy_delta_2026-03-08.csv`
- `.cursor/plans/phase0_5_actionability_split_2026-03-08.csv`
- `.cursor/plans/phase0_5_delta_analysis_2026-03-08.md`

Acceptance:
- 1 row per benchmark plot in delta file.
- Each row assigned exactly one actionability class.
- All classification rules documented in markdown report.

---

### P0.5-T4 - Freeze Actionable Plot Set for Phase 1

Goal:
- Lock the exact plots to use for Phase 1 algorithm improvement work.

Selection policy:
1. Include all `ACTIONABLE_ENVELOPE` and `ACTIONABLE_PLACEMENT`.
2. Include at least 3 control plots from `PIPELINE_PASS`.
3. Keep cohort diversity:
- small/medium/large
- regular/irregular
- road-sensitive/thin geometries

Outputs:
- `backend/output/benchmark_baseline/actionable_plot_set_v1.csv`
- `.cursor/plans/phase1_input_contract_from_p0_5_2026-03-08.md`

Acceptance:
- Actionable set is deterministic and versioned.
- Includes rationale per plot.
- Signed gate statement: "Phase 1 may begin".

---

## 4. Artifact Schema Contracts

### 4.1 `phase0_5_taxonomy_delta_2026-03-08.csv`
Columns:
- `fp_number`
- `baseline_taxonomy_code`
- `fidelity_taxonomy_code`
- `status_changed` (`Y/N`)
- `change_driver` (`ROAD_WIDTH_SOURCE` | `ROAD_EDGE_SOURCE` | `OTHER`)
- `notes`

### 4.2 `phase0_5_actionability_split_2026-03-08.csv`
Columns:
- `fp_number`
- `final_taxonomy_code`
- `actionability_class`
- `primary_failed_stage`
- `candidate_phase1_workstream`
- `rationale`

---

## 5. Decision Gates

Gate G0.5-A (after T1):
- Fidelity profile spec complete and reviewed.

Gate G0.5-B (after T2):
- Fidelity rerun artifacts complete with 24 valid rows.

Gate G0.5-C (after T3):
- Delta/actionability classification complete and auditable.

Gate G0.5-D (after T4):
- Actionable plot set frozen; Phase 1 input contract published.

No Phase 1 work starts before G0.5-D.

---

## 6. Precision Task List (Execution Checklist)

- [ ] T1.1 Draft fidelity profile spec document.
- [ ] T1.2 Define road-width source precedence and missing-value policy.
- [ ] T1.3 Define road-edge source policy and fallback semantics.
- [ ] T1.4 Define compliance pass-token normalization (`COMPLIANT`).
- [ ] T1.5 Approve profile spec at Gate G0.5-A.

- [ ] T2.1 Prepare rerun command/config using fidelity profile.
- [ ] T2.2 Generate fidelity raw benchmark CSV (24 rows).
- [ ] T2.3 Generate fidelity summary markdown.
- [ ] T2.4 Validate schema and row-count checks.
- [ ] T2.5 Approve rerun artifacts at Gate G0.5-B.

- [ ] T3.1 Compute taxonomy delta baseline vs fidelity.
- [ ] T3.2 Assign actionability class for each plot.
- [ ] T3.3 Generate delta analysis markdown with evidence.
- [ ] T3.4 Approve classification at Gate G0.5-C.

- [ ] T4.1 Select actionable plots with cohort balancing.
- [ ] T4.2 Create `actionable_plot_set_v1.csv`.
- [ ] T4.3 Publish Phase 1 input contract document.
- [ ] T4.4 Approve Phase 1 start at Gate G0.5-D.

---

## 7. Exit Criteria

Phase 0.5 is complete only when all are true:
1. Fidelity profile is documented and enforced in rerun.
2. Baseline-vs-fidelity deltas are quantified per plot.
3. Actionability split is complete and traceable.
4. `actionable_plot_set_v1.csv` is frozen and ready for Phase 1.
