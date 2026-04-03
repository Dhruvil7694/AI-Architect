---
name: ""
overview: ""
todos: []
isProject: false
---

# Backend Algorithm Gap Closure Plan (Site Planning + Floor Planning)

Date: 2026-03-08
Owner: Architecture AI backend team
Status: Draft for execution
Scope: Algorithmic improvements only (no UI/security scope in this plan)

## 1. Purpose

This plan translates verified algorithmic gaps into an implementation sequence with strict acceptance criteria.
Goal is to implement changes incrementally, validate each step, and avoid broad refactors that reduce confidence.

## 2. Verified Gaps (From Code Audit)

G

1. Site optimization is FSI-first (single-objective dominant).

G

1. COP strategy search is narrow (edge/center only).

G

1. Floor/tower search is heuristic-capped and can miss better feasible solutions.

G

1. Zone ranking uses area only (no access/daylight/frontage quality).

G

1. Internal road generation is simplistic (single-entry, single-spine bias).

G

1. Road-access constraint is skipped when corridor geometry is absent.

G

1. Floor plan topology is fixed (single core/corridor grammar) for diverse footprints.

G

1. Several floor-plan quality metrics are heuristic constants, not computed from geometry semantics.

## 3. Execution Principles

1. One gap at a time, one merge at a time.
2. No silent behavior changes: every algorithm change must include metrics + regression tests.
3. Prefer feature flags for behavior deltas where rollout risk exists.
4. Preserve deterministic outputs for same seed/inputs unless explicitly changed.
5. Record all objective/weight changes in a versioned config (not hidden constants).

## 4. Phased Work Breakdown

## Phase 0 - Baseline Lock and Measurement

Objective: Freeze current behavior and create benchmark harness before improvements.

Tasks:

- P0-T1 Define benchmark plot set (small/medium/large, regular/irregular, road-edge variants).
- P0-T2 Add benchmark runner command for full planning pipeline output snapshots.
- P0-T3 Define baseline KPIs per plot:
  - achieved_fsi
  - achieved_gc_pct
  - cop_required/provided
  - n_towers_placed
  - road_access_ok
  - floor efficiency ratio
  - units per floor
- P0-T4 Generate baseline report artifact under `backend/output/benchmark_baseline/`.

Acceptance criteria:

- Baseline suite runs successfully on all benchmark plots.
- KPI report generated with no missing fields.
- Baseline outputs frozen and checked into reproducible artifact folder.

Dependencies: none

---

## Phase 1 - FSI-Max Primary Optimization (G1 Revised)

Objective: Enforce FSI maximization as the primary objective for every compliant candidate. Secondary quality metrics are allowed only as deterministic tie-breakers when FSI is equal within tolerance.

Tasks:

- P1-T1 Define objective schema with strict priority:
  - Priority 1: maximize achieved FSI (compliant candidates only)
  - Priority 2+: tie-breakers (access/buildability/quality) only when Priority 1 is tied
- P1-T2 Implement scoring DTO carrying all component scores.
- P1-T3 Introduce weighted score config (versioned, externalized).
- P1-T4 Update solution selection to lexicographic ranking:
  - first by achieved FSI (descending),
  - then by tie-break scores.
- P1-T5 Add tie-break protocol (deterministic and documented).

Tie-break objective components (initial):

- Yield score
- Access/circulation score
- Buildability score
- Quality/livability proxy score

Acceptance criteria:

- For same input, selected plan includes full score breakdown in debug payload/logs.
- Hard non-compliance still always rejects candidate.
- Score changes reproducible across runs (deterministic).
- Benchmark comparison report: FSI-max picks vs baseline picks.
- Validation rule: if a higher-FSI compliant candidate exists, lower-FSI candidate must never be selected.

Dependencies: Phase 0

---

## Phase 2 - COP Strategy Expansion (G2)

Objective: Expand COP placement strategy exploration beyond two hardcoded options.

Tasks:

- P2-T1 Define COP strategy contract (strategy id, parameters, feasibility status).
- P2-T2 Add additional strategy candidates (e.g., edge variants, corner-biased, split-open-space strategy where legal).
- P2-T3 Add strategy pruning rules to avoid combinatorial explosion.
- P2-T4 Integrate strategy candidate scoring into Phase 1 scorer.
- P2-T5 Add COP diagnostics block: why each strategy passed/failed.

Acceptance criteria:

- Candidate strategy count configurable.
- Each strategy returns explicit failure reason if rejected.
- No regression in COP compliance pass rate on benchmark set.

Dependencies: Phase 1

---

## Phase 3 - Search Strategy Refinement (G3)

Objective: Reduce missed-optimum risk from coarse floor/tower heuristics.

Tasks:

- P3-T1 Replace static sampled floor list with adaptive sampling + local refinement near best bands.
- P3-T2 Replace hard `max_expansions`/fixed limits with budget-aware search controls.
- P3-T3 Replace static envelope footprint assumption in floor cap heuristic with observed envelope capacity estimate.
- P3-T4 Add search telemetry (visited states, pruned states, reason counts).
- P3-T5 Add fast/standard/deep search modes for runtime control.

Acceptance criteria:

- Deep mode never underperforms standard mode on achieved score for benchmark set.
- Search telemetry exported in structured format.
- Runtime growth bounded and measurable by configured budget.

Dependencies: Phase 1

---

## Phase 4 - Zone and Road Intelligence (G4, G5, G6)

Objective: Improve placement robustness using richer zone ranking and road-access semantics.

Tasks:

- P4-T1 Add zone quality features:
  - road proximity quality
  - frontage quality
  - compactness/shape penalty
  - corridor reachability
- P4-T2 Replace area-only zone sorting with weighted zone score.
- P4-T3 Improve internal road generation:
  - multi-entry support when multiple road edges exist
  - optional branched spine generation
  - configurable connection goals (COP first, tower zones first)
- P4-T4 Tighten road-access behavior when road geometry is absent:
  - explicit `unknown` state instead of automatic pass
  - configurable policy (`allow_unknown` flag)
- P4-T5 Add validation for disconnected access graph.

Acceptance criteria:

- Zone ranking includes score vector per zone in debug output.
- Road graph generation succeeds or returns explicit structured failure.
- `road_access_ok` becomes tri-state (`true/false/unknown`) with policy-controlled gating.

Dependencies: Phase 1 (and ideally Phase 3)

---

## Phase 5 - Floor Plan Topology Generalization (G7, G8)

Objective: Move from single fixed topology to controlled topology variants with measured quality.

Tasks:

- P5-T1 Define floor topology grammar set:
  - central core variant
  - side core variant
  - dual-core (where footprint supports)
  - single-loaded corridor variant
- P5-T2 Create topology feasibility pre-check per footprint geometry.
- P5-T3 Generate multiple floor layout candidates per topology.
- P5-T4 Add floor-plan scoring model:
  - circulation efficiency
  - daylight proxy by facade exposure
  - ventilation proxy per habitable room
  - unit usability metrics
- P5-T5 Replace fixed carpet/rera multipliers with explicit computed/annotated method where possible, and flag assumptions where not computable.
- P5-T6 Emit per-room/per-unit quality diagnostics for review.

Acceptance criteria:

- At least 2 topology candidates evaluated for eligible footprints.
- Selected floor includes score comparison against rejected candidates.
- No hard GDCR violation introduced by topology expansion.

Dependencies: Phase 1, Phase 4

---

## Phase 6 - Regression Hardening and Rollout

Objective: Safely integrate all enhancements without destabilizing production outputs.

Tasks:

- P6-T1 Extend stress tests with new scorer/search/topology invariants.
- P6-T2 Add golden-case regression snapshots for 10 representative plots.
- P6-T3 Add performance envelope checks (runtime and memory budgets).
- P6-T4 Add feature flags for staged rollout of each major enhancement:
  - scoring_v2
  - cop_strategy_v2
  - search_v2
  - road_graph_v2
  - floor_topology_v2
- P6-T5 Run A/B comparison report baseline vs v2 and document deltas.

Acceptance criteria:

- All regression tests green.
- Runtime budget respected in standard mode.
- A/B report signed off with expected improvements and known trade-offs.

Dependencies: Phases 1-5

## 5. Task Dependency Graph

- Phase 0 -> Phase 1
- Phase 1 -> Phase 2, Phase 3
- Phase 1 + Phase 3 -> Phase 4
- Phase 1 + Phase 4 -> Phase 5
- Phases 1-5 -> Phase 6

## 6. Suggested Implementation Order (Strict)

1. P0 baseline harness
2. P1 scoring architecture
3. P3 search refinement (so scoring has better candidate quality)
4. P4 zone/road intelligence
5. P2 COP expansion
6. P5 floor topology + quality metrics
7. P6 hardening and rollout

## 7. Definition of Done (Per Gap)

A gap is considered closed only when all are true:

- Algorithm change implemented.
- Unit + integration tests added/updated.
- Benchmark delta measured against baseline.
- Output diagnostics expose decision rationale.
- No regression in legal compliance pass rate.

## 8. Risks and Controls

Risk: Objective weights overfit benchmark set.
Control: keep weighted config versioned + add holdout plot set.

Risk: Search improvements increase runtime too much.
Control: mode budgets (`fast`, `standard`, `deep`) + CI runtime assertions.

Risk: Topology expansion creates unstable geometry edge cases.
Control: pre-check feasibility filter + hard failover to stable topology.

Risk: Access policy change rejects too many legacy cases.
Control: staged feature flag with comparative telemetry.

## 9. Tracking Template (To Use During Execution)

For each task completion, append:

- Task ID:
- Date:
- Commit(s):
- Benchmark delta:
- Regressions observed:
- Decision notes:

## 10. Immediate Next Action

Start with Phase 0, Task P0-T1 and P0-T2 only.
Do not implement scoring/search/topology changes before baseline is frozen.
