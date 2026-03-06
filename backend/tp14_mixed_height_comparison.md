# TP14 Mixed Strategy — Height Comparison (10m, 16.5m, 25m)

Same batch: 171 plots, `--mixed-strategy`, road 12m. Compare distribution shifts to validate engine robustness before Phase 2.

## Summary Table

| Metric | 10m | 16.5m | 25m |
|--------|-----|-------|-----|
| **Plots with mixed result** | 103 | 91 | 58 |
| **Envelope failed** | 47 | 47 | 61 |
| **% where mixed beats homogeneous** | **28.2%** | 23.1% | **19.0%** |
| **Average diversity score (winners)** | **0.1408** | 0.1154 | **0.0948** |
| **Average FSI utilization (winners)** | **40.8%** | 59.3% | **68.4%** |
| **Cases maxing unit cap (>=6/floor)** | 2 | 4 | 2 |

## Distribution of Chosen Unit Types

| Type | 10m | 16.5m | 25m |
|------|-----|-------|-----|
| STUDIO-only | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| 1BHK-only | 8 (7.8%) | 16 (17.6%) | **16 (27.6%)** |
| 2BHK-only | 10 (9.7%) | 10 (11.0%) | 8 (13.8%) |
| 3BHK-only | **56 (54.4%)** | 44 (48.4%) | 23 (39.7%) |
| Mixed | **29 (28.2%)** | 21 (23.1%) | 11 (19.0%) |

## Validation Questions

| Question | Result |
|----------|--------|
| **Does luxury dominate at 10m?** | **Yes.** 3BHK-only is 54.4% at 10m (highest share across heights). Fewer floors → less FSI pressure → larger units win. |
| **Does density increase at 25m?** | **Yes.** FSI utilization rises with height: 40.8% → 59.3% → 68.4%. At 25m, fewer plots pass envelope (61 fail vs 47 at 10m/16.5m); among those that do, the engine pushes FSI harder. |
| **Does diversity increase with height?** | **No — diversity is highest at 10m.** Mixed % and diversity score fall as height increases (28.2% → 23.1% → 19.0%; 0.14 → 0.12 → 0.09). At lower height, density/FSI triple-count is less dominant, so mixed strategies win more often. |

## Conclusion

- **Luxury dominates at 10m** (3BHK 54.4%).
- **Density (FSI utilization) increases with height** (40.8% → 68.4%).
- **Diversity is highest at 10m** and decreases at 25m; behavior is consistent with FSI/density pressure scaling with height.
- **1BHK share rises at 25m** (27.6%) as envelopes tighten and smaller units fit more often.

Behavior scales logically with height: the engine is robust for Phase 2.

---
*Generated from: simulate_tp_batch --tp 14 --height {10|16.5|25} --road-width 12 --mixed-strategy --output tp14_mixed_H{10|16.5|25}.csv*
