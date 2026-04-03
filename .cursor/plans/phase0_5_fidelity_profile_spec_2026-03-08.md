# Phase 0.5 Fidelity Profile Spec (TP14 Benchmark v1)

Date: 2026-03-08
Version: v1
Status: Draft ready for approval (Gate G0.5-A)

## 1. Purpose

Define a deterministic benchmark fidelity profile so Phase 1 decisions are based on trustworthy baseline data, not harness artefacts.

## 2. Profile ID

- `profile_id`: `tp14_fidelity_v1`
- `benchmark_set`: `backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`
- `tp_scheme`: `TP14`

## 3. Input Source Precedence

### 3.1 Road Width (`road_width_m`)

1. Primary: `Plot.road_width_m` for each plot.
2. If missing/invalid (`<=0` or null):
- Mark `road_width_source = MISSING`
- Mark row `fidelity_flag = ROAD_WIDTH_MISSING`
- Default action: `SKIP_PLOT`

No global command-level single road width is allowed in fidelity profile.

### 3.2 Road Edge Detection

1. Primary: explicit road geometry source (not `None` queryset).
2. Fallback allowed only when no intersection detected:
- Use longest-edge heuristic.
- Mark `road_edge_source = FALLBACK_LONGEST_EDGE`.

If explicit road geometry source is unavailable:
- mark run-level warning: `ROAD_LAYER_UNAVAILABLE`
- still allow run, but every affected row must carry explicit fallback marker.

## 4. Status Semantics Normalization

### 4.1 Compliance Pass Token

- `compliance_pass = TRUE` iff `compliance_status == COMPLIANT`.
- `NON-COMPLIANT` is always fail.
- Empty compliance status is fail.

### 4.2 Envelope / Placement Interpretation

- Keep raw statuses unchanged (`VALID`, `COLLAPSED`, `TOO_SMALL`, `NO_FIT`, `TOO_TIGHT`, `NO_FIT_CORE`).
- Derived pass fields:
- `envelope_pass = (envelope_status == VALID)`
- `placement_pass = (placement_status == VALID)`

## 5. Required Output Columns (Fidelity Metadata)

Add these columns to fidelity-run CSV:
- `fidelity_profile_id`
- `road_width_source` (`PLOT_FIELD` | `MISSING`)
- `road_edge_source` (`ROAD_LAYER_INTERSECTION` | `FALLBACK_LONGEST_EDGE`)
- `fidelity_flag` (nullable)
- `compliance_pass` (`Y/N`)

Existing KPI columns must remain unchanged.

## 6. Determinism Contract

1. Plot ordering fixed by `fp_number` from benchmark set.
2. No random sampling.
3. Same inputs must produce identical taxonomy classification.

## 7. Acceptance Criteria (Gate G0.5-A)

Spec is accepted only if:
1. Source precedence rules are explicit and non-conflicting.
2. Missing-road-width handling is explicit (`SKIP_PLOT` in v1).
3. Compliance token normalization is explicit (`COMPLIANT` only).
4. Fidelity metadata columns are defined and mandatory.
5. Determinism contract is stated.

## 8. Out-of-Scope for v1

1. No algorithm changes.
2. No scoring weight changes.
3. No benchmark set expansion beyond 24 plots.
