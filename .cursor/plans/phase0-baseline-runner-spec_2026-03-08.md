# Phase 0 Baseline Runner Spec

Date: 2026-03-08
Scope: P0-T2 baseline runner definition using existing commands

## Decision
Reuse existing command:
- `python manage.py simulate_tp_batch`

Reason:
- Already emits all core site-planning and compliance KPIs in one CSV.
- Avoids building new code before baseline freeze.

## Inputs
1. Benchmark set file:
- `backend/output/benchmark_baseline/benchmark_plot_set_v1.csv`
2. Simulation command output:
- `backend/output/benchmark_baseline/tp14_baseline_raw_all.csv`
3. Filtered benchmark output:
- `backend/output/benchmark_baseline/tp14_baseline_raw_benchmark_v1.csv`

## Run Command (raw all TP14)
From `backend/` directory:

`python manage.py simulate_tp_batch --tp 14 --height 16.5 --road-width 12.0 --output output/benchmark_baseline/tp14_baseline_raw_all.csv`

## Filter Logic
Keep only rows where:
- `(tp_scheme='TP14', fp_number)` exists in `benchmark_plot_set_v1.csv`

Required filtered columns (minimum):
- fp_number
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

## KPI Summary Output
Generate markdown summary:
- `backend/output/benchmark_baseline/tp14_baseline_summary.md`

Summary metrics:
1. total benchmark rows
2. envelope valid rate
3. placement valid/too-tight rate
4. compliance pass rate
5. median fsi_achieved
6. median gc_achieved_pct
7. top failure reasons by count

## Determinism Notes
- Keep command arguments fixed for baseline v1.
- Re-run with same args must overwrite output files and produce same row count.
- If results differ, record drift reason before proceeding to Phase 1.
