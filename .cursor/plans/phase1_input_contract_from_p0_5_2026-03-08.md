# Phase 1 Input Contract From Phase 0.5

Date: 2026-03-08
Source gate: G0.5-D

## Baseline Context
- Baseline artifact: `D:/AI for Architecture/code/backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`
- Fidelity artifact: `D:/AI for Architecture/code/backend/output/benchmark_baseline/tp14_baseline_fidelity_raw_benchmark_v1.csv`
- Delta artifact: `D:/AI for Architecture/code/.cursor/plans/phase0_5_taxonomy_delta_2026-03-08.csv`
- Actionability artifact: `D:/AI for Architecture/code/.cursor/plans/phase0_5_actionability_split_2026-03-08.csv`

## Frozen Actionable Set
- Actionable set file: `D:/AI for Architecture/code/backend/output/benchmark_baseline/actionable_plot_set_v1.csv`
- Total plots in actionable set: **4**
- Included controls: **3**
- Actionability distribution: `{'NON_ACTIONABLE_REGULATORY': 14, 'CONTROL_PASS': 9, 'ACTIONABLE_ENVELOPE': 1}`

## Phase 1 Workstream Mapping
- Envelope-focused set: `['181']`
- Placement-focused set: `[]`
- Compliance-chain set: `[]`
- Control/pass set: `['23', '34', '84']`

## Measurement Contract
- Required KPI columns: envelope_status, placement_status, compliance_status, fsi_achieved, gc_achieved_pct, error, compliance_pass
- Pass token: compliance_status == COMPLIANT
- Delta method: per-fp taxonomy + KPI comparison against frozen baseline/fidelity artifacts
- Selection policy: choose highest achievable compliant FSI for each plot; apply secondary metrics only as tie-breakers when FSI is equal within tolerance.

## Sign-off
- Gate G0.5-D status: PASS
- Approved to start Phase 1: YES
