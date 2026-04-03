# Phase 0.5 - Algorithm Gap Validation (TP14 Benchmark v1)

Date: 2026-03-08
Scope: Validate whether enhancement targets are real algorithm gaps vs baseline harness artefacts.

## Corrected Baseline Snapshot (24 plots)
- Envelope VALID: **8/24** (33.3%)
- Placement VALID: **6/24** (25.0%)
- Compliance COMPLIANT: **6/24** (25.0%)
- Fallback road-edge used: **24/24** (100.0%)

## Taxonomy Counts
- ENVELOPE_COLLAPSE_ROAD_SETBACK: **7**
- ENVELOPE_TOO_SMALL_AFTER_SETBACKS: **7**
- PIPELINE_PASS: **6**
- ENVELOPE_COLLAPSE_SIDE_REAR_SETBACK: **2**
- PLACEMENT_NO_FIT_ON_VALID_ENVELOPE: **2**

## Gap Signal Counts
- YES: **2**
- MIXED: **14**
- LIKELY_NO: **2**
- NO: **6**

## Code-Path Evidence (Line-Referenced)
- Envelope margins include `max(table, H/5, min_road_margin)` and fallback road width when edge metadata is missing (`road_width = spec.road_width or 9.0`).
  refs: `backend/envelope_engine/geometry/margin_resolver.py:75,79,81,82`
- Envelope fails hard on half-plane collapse and applies fixed minimum buildable area threshold `215 sq.ft`.
  refs: `backend/envelope_engine/geometry/envelope_builder.py:143,146,170,171`; `backend/envelope_engine/geometry/__init__.py`
- Batch baseline runner always requests single tower placement (`n_towers=1`) and exits early on envelope failure.
  refs: `backend/architecture/management/commands/simulate_tp_batch.py:223,237,248`
- Road edges in batch are detected with `road_layer_queryset=None`, forcing longest-edge fallback when no road geometry iterable is supplied.
  refs: `backend/architecture/management/commands/simulate_tp_batch.py` (road detector call); `backend/architecture/spatial/road_edge_detector.py` (fallback logic)
- Placement status semantics: `NO_FIT`, `TOO_TIGHT`, `NO_FIT_CORE` explicitly gate downstream behavior.
  refs: `backend/placement_engine/services/placement_service.py:142,182,184,204`

## Verdict: Is There an Actual Enhancement Gap?
- All benchmark rows used fallback road-edge detection (`fallback_road_used=Y`), so edge typing is heuristic, not cadastral-road verified.
- `simulate_tp_batch` uses a single command-level `--road-width` for every plot, which can misstate per-plot setbacks during benchmarking.
- Yes, there is an enhancement gap, but it is **two-layered**:
  1) **Benchmark harness fidelity gap** (road-edge fallback + uniform road width) that can create false negatives.
  2) **Core algorithm gap** for thin/irregular survivability after setbacks and placement on fragmented envelopes.
- Therefore, Phase 1 should not start with random algorithm rewrites; first lock benchmark fidelity controls, then improve envelope/placement heuristics against that corrected baseline.

## Prioritized Task List (Pre-Phase 1 Gate)
- [ ] P0.5-T1: Add benchmark fidelity profile that uses per-plot road width from `Plot.road_width_m` and explicit road-edge source.
- [ ] P0.5-T2: Re-run the same 24-plot set under fidelity profile and diff taxonomy shifts.
- [ ] P0.5-T3: Isolate truly hard-regulatory plots (non-actionable) vs algorithm-actionable plots.
- [ ] P0.5-T4: Freeze `actionable_plot_set_v1` for Phase 1 envelope/placement improvements.

## Artifacts
- Per-plot taxonomy CSV: `.cursor/plans/phase0_5_per_plot_taxonomy_2026-03-08.csv`
- Source benchmark CSV: `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`