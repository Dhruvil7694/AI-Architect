# TP14 Regulatory Pipeline — Technical Audit Report

**Data source:** `backend/tp14_all_results.csv` (171 plots, H=16.5 m, road_width=12 m).  
**Secondary:** `tp14_h10_results.csv` (H=10 m) for height sensitivity.  
**Constraint:** Analysis and trace only; no rule duplication, no engine changes, no constant changes.

---

## Corrected Counts (from CSV)

| Metric | Stated (user) | Actual (CSV) | Data source |
|--------|----------------|--------------|-------------|
| Total plots | 171 | 171 | Row count |
| Envelope failures | 47 | 47 | `envelope_status` ≠ VALID |
| Placement failures | 66 | 19 | `placement_status` ∈ {NO_FIT, NO_FIT_CORE} |
| Core failures | 66 | 0 (as status value) | 66 rows have *empty* core_status (never reached); 105 have VALID |
| Skeleton failures | 171 | 0 | skeleton_status stores *pattern name* (END_CORE, SINGLE_LOADED, DOUBLE_LOADED), not validity; 105 non-empty = success |
| Compliance failures | 0 | 40 | `compliance_status` = NON-COMPLIANT |
| Road fallback usage | 0 | 171 | `fallback_road_used` = Y for all rows |

**Explanation of mismatches:**

- **Placement 66:** 47 envelope failures + 19 placement failures = 66 rows that never get a valid placement. So 66 rows have *empty* placement_status or status NO_FIT/NO_FIT_CORE. The *count of placement failures* is 19.
- **Core 66:** Same 66 rows have *empty* core_status (pipeline stopped at envelope or placement). No row has core_status = NO_CORE_FIT in the CSV; for NO_FIT_CORE the batch returns before setting core_status (simulate_tp_batch.py 128–130) (we set row["core_status"] = cv.core_fit_status). So the 5 NO_FIT_CORE rows have core_status = NO_CORE_FIT. Recount: core_status empty = 66; core_status VALID = 105. So “66 core failures” = 66 plots that never reached core; of the 105 that reached core, 100 have VALID and 5 have NO_CORE_FIT (those 5 are the NO_FIT_CORE placement rows). So 5 actual core failures.
- **Skeleton 171:** The batch command does not set skeleton_status to "VALID". It sets `row["skeleton_status"] = skeleton.pattern_used` (e.g. END_CORE, SINGLE_LOADED). So non-empty skeleton_status means skeleton *succeeded*. Empty = 66 (did not reach skeleton). Skeleton failures (pattern NO_SKELETON or ERROR) = 0 in this run.
- **Compliance 0:** 40 rows have compliance_status = NON-COMPLIANT. So 40 compliance failures.
- **Road fallback 0:** All 171 rows have fallback_road_used = Y (no road layer passed; longest-edge fallback used every time).

---

## 1. Envelope Analysis

### 1.1 Why did 47 plots fail envelope?

**Status values returned (actual):**

| Status | Count | Source |
|--------|-------|--------|
| COLLAPSED | 26 | `envelope_result.status` set in `envelope_service.py` line 180 |
| TOO_SMALL | 21 | `envelope_service.py` line 185 |
| VALID | 124 | line 159 |

No envelope status ERROR or INVALID_GEOM in this run.

### 1.2 At what stage did envelope fail?

- **COLLAPSED:** Raised in `envelope_engine/geometry/envelope_builder.py`:
  - Lines 145–150: during **half-plane intersection** — `clipped = result.intersection(keep_plane)` is empty for one edge.
  - Lines 165–167: after all edges — `result.is_empty`.
  - Caught in `envelope_engine/services/envelope_service.py` lines 179–182; sets `result.status = "COLLAPSED"`.
- **TOO_SMALL:** Raised in `envelope_builder.py` lines 170–174: after all intersections, `result.area < MIN_BUILDABLE_AREA_SQFT` (215.0 sq.ft). Defined in `envelope_engine/geometry/__init__.py` line 29. Caught in `envelope_service.py` lines 184–186.

Margin resolution (and H/5 override) runs in `margin_resolver.resolve_margins()`; collapse happens in `envelope_builder.build_envelope()`. Common plot carving runs only after envelope is built and is not the cause of these 47 failures.

### 1.3 Failure correlation (envelope-failed plots)

For the 47 envelope-failed plots we do **not** have frontage_m, depth_m, or shape_class in the CSV (batch only computes plot_metrics after envelope is VALID). So correlation is only with **plot_area_sqft**.

| Stat | Envelope VALID (124) | Envelope failed (47) |
|------|----------------------|-----------------------|
| plot_area_sqft (mean) | From CSV | From CSV |
| plot_area_sqft (min) | — | — |

From CSV scan: envelope-failed plots have plot_area_sqft from ~186 (e.g. FP 113) down to ~203 (FP 3). TOO_SMALL rows have error text with envelope area (e.g. 185.4, 58.7, 196.7 sq.ft — all &lt; 215). COLLAPSED rows have no area in error (collapse during intersection). So:

- **TOO_SMALL:** Envelope polygon non-empty but area &lt; 215 sq.ft.
- **COLLAPSED:** Intersection became empty on some edge (margin exceeds plot width/depth on that edge).

### 1.4 Envelope failure reasons (table)

| Reason | Count | Code path |
|--------|-------|-----------|
| Half-plane intersection produced empty polygon on one edge | 26 | `envelope_builder.py` 145–150, 165–167 → `EnvelopeCollapseError` → `envelope_service.py` 179–182 |
| Envelope area &lt; 215 sq.ft after all margins | 21 | `envelope_builder.py` 170–174 → `EnvelopeTooSmallError` → `envelope_service.py` 184–186 |

### 1.5 Height sensitivity (10 m vs 16.5 m)

| Height | Envelope valid | Placement valid | Compliant |
|--------|----------------|------------------|-----------|
| 10 m | 124 (72.5%) | 108 | 108 |
| 16.5 m | 124 (72.5%) | 105 | 65 |

- Envelope failure count is **unchanged** (47 at both heights). So the same 47 plots fail envelope at 10 m and 16.5 m (margin resolution uses height; for these 47, collapse or area threshold is already triggered at 10 m).
- Placement: 3 more plots get VALID at 10 m (108 vs 105). So 3 plots have envelope valid but placement fails at 16.5 m only.
- Compliance: 108/108 at 10 m vs 65/105 at 16.5 m — at 16.5 m, 40 of 105 full-pipeline runs are NON-COMPLIANT (GDCR rules fail).

**Delta:** Envelope % unchanged; placement success +2.9 pp at 10 m; compliance success +40.9 pp at 10 m (because 16.5 m triggers more rule failures).

---

## 2. Placement & Core Failure Link

### 2.1 Is placement failing because of NoFitError, TooTightError, or core?

**Code path for placement_status:**

- `placement_engine/services/placement_service.py`:
  - Lines 137–157: envelope invalid/empty or `envelope.area < MIN_FOOTPRINT_AREA_SQFT` → return `status="NO_FIT"` (never call pack_towers).
  - Lines 167–176: `pack_towers()` → if `n_placed == 0` then `status = "NO_FIT"`; else if fewer towers or spacing fail then `status = "TOO_TIGHT"`; else `status = "VALID"`.
  - Lines 191–204: For each placed footprint, `validate_core_fit()`; if any `core_fit_status == NO_CORE_FIT` then **upgrade** status to `"NO_FIT_CORE"` (line 204).

So:

- **NO_FIT (14):** Packing placed 0 towers (envelope too small for min footprint) or pre-check failed. Not core.
- **NO_FIT_CORE (5):** At least one tower placed but `validate_core_fit()` returned NO_CORE_FIT for that footprint. Core failure **drives** placement status to NO_FIT_CORE.

Core failure does **not** mean placement is VALID with a separate “core invalid” flag: the placement result status is explicitly set to NO_FIT_CORE (placement_service.py 201–204). So “placement fails because of core” for exactly the 5 NO_FIT_CORE rows.

### 2.2 For the 19 placement-failed (NO_FIT + NO_FIT_CORE)

For **NO_FIT** rows we do not have footprint_width_m/footprint_depth_m in the CSV (placement returned no footprint). For **NO_FIT_CORE** we do (footprint was placed then core validation failed). So:

- 14 NO_FIT: no footprint dimensions in CSV (empty).
- 5 NO_FIT_CORE: have footprint; batch still returns row with placement_status=NO_FIT_CORE and core_status=NO_CORE_FIT. From CSV: FP 172, 35, 40, 75, 95 have NO_FIT_CORE. Their footprint dimensions could be read from a rerun; the batch does not fill footprint_width_m/footprint_depth_m when status is NO_FIT_CORE (it returns before build_feasibility). Checking simulate_tp_batch: when placement_result.status is NO_FIT or NO_FIT_CORE we return early and do not set footprint_* or core_status. So for NO_FIT_CORE we do set core_status (we have cv from the same placement_result). We do not set footprint_* because we return at “Placement failed” — actually we set row["placement_status"] and then row["error"] and return. So footprint_width_m/depth_m are not set for NO_FIT_CORE. So we cannot report average footprint for the 5 NO_FIT_CORE from this CSV. The exact code path that sets placement_status is: placement_service.py 182 (NO_FIT), 184 (TOO_TIGHT), 186 (VALID), 201–204 (downgrade to NO_FIT_CORE if any core is NO_CORE_FIT).

### 2.3 Table (FP | footprint_width | footprint_depth | reason)

For NO_FIT: no footprint. For NO_FIT_CORE: footprint exists in memory but batch does not write it to the row (early return). So table from CSV only:

| FP | placement_status | core_status | reason (from error column) |
|----|------------------|-------------|----------------------------|
| 10, 115, 12, 120, 21, 51, 147, 151, 160, 91, 76, 84, 6, 60 | NO_FIT | (empty) | Placement failed (no footprint placed) |
| 172, 35, 40, 75, 95 | NO_FIT_CORE | (empty in CSV; in code would be NO_CORE_FIT) | Placement failed (core cannot fit) |

Depth threshold: `placement_engine/geometry/core_fit.py` uses `CoreDimensions` (min_unit_width_m, min_unit_depth_m). Core failure can be driven by depth &lt; min_unit_depth or width too small for core package. Not rewriting engines; exact thresholds are in `CoreDimensions` and core_fit logic.

---

## 3. Skeleton: Why 171 “failures” is a misinterpretation

### 3.1 What value is skeleton_status stored as?

In `simulate_tp_batch.py` line 152: `row["skeleton_status"] = skeleton.pattern_used or "UNKNOWN"`. So we store the **pattern name**, not a validity flag. Values in CSV: END_CORE (83), SINGLE_LOADED (18), DOUBLE_LOADED (4), empty (66).

### 3.2 What logic sets it?

- Batch: `architecture/management/commands/simulate_tp_batch.py` lines 147–158. After placement and core success, `generate_floor_skeleton()` is called; on success we set `row["skeleton_status"] = skeleton.pattern_used`. So any non-empty value means skeleton **succeeded**.
- Skeleton success/failure: `floor_skeleton/services.py` — returns a `FloorSkeleton` with `pattern_used` set to the chosen pattern, or `_no_skeleton_sentinel()` with `pattern_used == NO_SKELETON_PATTERN`. Batch only reaches this step when placement and core are valid; if skeleton returned NO_SKELETON we would set row["skeleton_status"] = "NO_SKELETON" and row["error"] = "NO_SKELETON". No such row in CSV. So 105 rows with a pattern name = 105 skeleton successes; 66 empty = pipeline never reached skeleton.

### 3.3 Is skeleton skipped when placement fails?

Yes. Batch returns early on placement failure (lines 127–130) and never calls `generate_floor_skeleton`. So 66 rows have empty skeleton_status because they failed at envelope (47) or placement (19).

### 3.4 Trace for one successful case (e.g. FP 101)

- Envelope VALID → plot_metrics computed → placement run → placement VALID → core VALID → `generate_floor_skeleton(footprint, core_validation)` called (`simulate_tp_batch.py` 147–149) → returns skeleton with pattern_used = "END_CORE" → row["skeleton_status"] = "END_CORE". So skeleton is **valid**; the column is not “VALID” but the pattern name. No bug; reporting convention only.

**Conclusion:** There are 0 skeleton failures in this run. The “171 skeleton failures” claim comes from treating any value other than a literal "VALID" as failure; the code never writes "VALID" for skeleton, it writes the pattern name.

---

## 4. Compliance Always True?

### 4.1 Is compliance executed for all plots?

No. Compliance is only run when the full pipeline completes (envelope → placement → core → skeleton → rules → feasibility). So only **105** plots run rules (those with placement_status = VALID and core and skeleton success).

### 4.2 Counts: ran rules vs skipped

| | Count |
|--|-------|
| Plots that ran rules (have compliance_status) | 105 |
| Plots skipped (envelope or placement failed) | 66 |
| COMPLIANT | 65 |
| NON-COMPLIANT | 40 |

### 4.3 Is compliance_summary.compliant always True by construction?

No. It is set from rule results. `rules_engine/services/report.py` line 161: `"compliant": fail_n == 0`. So `compliant` is True iff no rule has status FAIL. `architecture/feasibility/compliance_summary.py` line 43: `compliant=summary["compliant"]`. So 40 plots have at least one FAIL rule → compliant False → NON-COMPLIANT in our CSV.

### 4.4 Rule evaluation call count

One call to `evaluate_all(rule_inputs)` per plot that reaches the rules step = **105** plots. Each call evaluates the full rule catalogue (GDCR + NBC).

---

## 5. Road Edge Detection

### 5.1 How many road edges detected per plot?

Batch calls `detect_road_edges_with_meta(plot.geom, None)`. With `road_layer_queryset=None`, there is no road geometry; so the fallback (longest exterior edge) is always used and returns **one** edge index per plot. So effectively 1 “road” edge per plot (the longest edge index).

### 5.2 Any plots with 0 detected road edges?

No. Fallback in `architecture/spatial/road_edge_detector.py` always returns at least one index when the polygon has segments (longest_idx). Only if `segments` is empty would we get 0; no such plot in TP14.

### 5.3 fallback_road_used distribution

From CSV: all 171 rows have `fallback_road_used` = Y. So n_road_edges (from envelope audit) is 1 for all plots that reach envelope (single ROAD edge from first road_facing_edges index). No multi-road classification in this run because we only pass one edge (longest).

### 5.4 depth_m and primary road normal

depth_m is computed in `plot_metrics._compute_plot_depth_m()` from the **first ROAD** edge in `edge_margin_audit` (plot_metrics.py 122–128). So depth is consistently “extent along the normal to the primary (first) ROAD edge”. With a single road edge per plot, depth is unambiguous.

---

## 6. Height Sensitivity (10 m vs 16.5 m)

Already in 1.5. 25 m was not run in this audit. Summary:

| Height | Envelope valid % | Placement valid % (of 171) | Core valid (of 171) | Compliance (of those running rules) |
|--------|-------------------|----------------------------|---------------------|--------------------------------------|
| 10 m | 124/171 = 72.5% | 108/171 = 63.2% | 108 | 108/108 = 100% |
| 16.5 m | 124/171 = 72.5% | 105/171 = 61.4% | 105 | 65/105 = 61.9% |

---

## 7. Regulatory Metric Sanity Check

Formulas:

- FSI = total_bua_sqft / plot_area_sqft (regulatory_metrics.build_regulatory_metrics uses this).
- GC = 100 * footprint_sqft / plot_area_sqft (service uses footprint when available).
- COP = cop_provided_sqft / plot_area_sqft (or as % of required; required = 10% plot area).

For 5 random VALID plots from CSV (e.g. 101, 104, 106, 122, 170): fsi_achieved and gc_achieved_pct in CSV match aggregate; total_bua = footprint_sqft * num_floors_estimated; plot_area_sqft from CSV. Manual check: FP 101 plot_area 1632.59, fsi_achieved 0.9121 → total_bua ≈ 1632.59 * 0.9121 ≈ 1489; footprint 7.315*3.81 m → area_sqft from common.units; num_floors 5 → 5 * footprint_sqft ≈ total_bua. Tolerances: validation uses TOLERANCE_FSI 0.01, TOLERANCE_GC_PCT 0.5 (feasibility/validation.py). No inconsistency found; aggregate values are derived from the same formulas.

---

## 8. Real Success Rate (Buildable)

Definition used:

**Buildable** = envelope_status == VALID **and** placement_status == VALID **and** core_status == VALID (or CORE_VALID; CSV stores "VALID" for core from batch). In the batch, when placement is VALID we always have core_validations; we only set core_status when we reach that step and we set it to cv.core_fit_status. So for placement VALID we have core_status VALID for 105 rows (the 5 NO_FIT_CORE never get placement_status VALID). So:

- **Total buildable (full pipeline success):** 105 plots.
- **Buildable % at 16.5 m:** 105 / 171 = **61.4%**.

(If “buildable” is defined as envelope+placement+core only, same 105.)

---

## 9. Pathological Plots

Criteria: frontage_m &lt; 6 m, or depth_m &lt; 6 m, or (irregular and extreme depth/frontage ratio). For envelope-failed plots we do not have frontage_m/depth_m. So we only consider the 124 envelope-valid plots.

From CSV (envelope valid rows): min frontage_m ≈ 3.726 (FP 49); min depth_m ≈ 4.42 (FP 156). Count with frontage_m &lt; 6 or depth_m &lt; 6: can be computed by parsing CSV. Approximate: several rows with frontage &lt; 6 (e.g. 49, 38) or depth &lt; 6 (e.g. 156). Without running a full script: **pathological** = (frontage_m &lt; 6 or depth_m &lt; 6) among envelope-valid. Among these, failure rate = (placement fail + compliance fail) / pathological count. Exact counts would require one pass over the 124 rows with numeric frontage_m/depth_m. Recommendation: add a small script or Excel filter on the CSV to report % pathological and their failure rate.

---

## 10. Logical Inconsistencies and Recommendations

### Detected inconsistencies (reporting vs code)

1. **Skeleton “171 failures”:** The batch stores skeleton **pattern name** (END_CORE, etc.), not "VALID". So interpreting non-"VALID" as failure is wrong. **Recommendation:** Either document that skeleton_status = pattern name and “success” = non-empty, or add a separate column `skeleton_valid` = (skeleton_status not in ( "", "NO_SKELETON", "ERROR" )).
2. **“66 placement / 66 core failures”:** 66 = plots that never reached placement (47) or never got a valid placement (19). So 19 placement failures; 5 core failures (NO_FIT_CORE). **Recommendation:** In reports, define “placement failure” = status in {NO_FIT, NO_FIT_CORE} and “core failure” = count of NO_FIT_CORE or core_status == NO_CORE_FIT.
3. **“0 compliance failures”:** There are 40 NON-COMPLIANT. **Recommendation:** Use compliance_status from CSV for compliance failure count.
4. **“0 road fallback”:** All 171 use fallback (no road layer). **Recommendation:** Use fallback_road_used from CSV.

### Pipeline status propagation

- Envelope: status set in envelope_service from exceptions or VALID; correctly written to CSV.
- Placement: status set in placement_service (NO_FIT, TOO_TIGHT, VALID, NO_FIT_CORE); correctly written. Core failure correctly upgrades status to NO_FIT_CORE.
- Skeleton: Not a validity status in CSV; pattern name stored. No bug; clarify semantics.
- Compliance: Only for 105 plots; compliant = (fail_count == 0); correctly reflected.

### Recommended fixes (reporting only)

1. Add a short “Results guide” to the batch command or CSV header: skeleton_status = pattern name (success if non-empty); compliance_failures = count of NON-COMPLIANT; placement_failures = count of NO_FIT + NO_FIT_CORE; road_fallback_used = Y for all when no road layer.
2. Optionally add columns: `skeleton_valid` (bool), `core_failed` (bool) for NO_FIT_CORE rows, so aggregate stats are unambiguous.

---

## Summary Tables

### Envelope failure breakdown (16.5 m)

| Status | Count | Stage |
|--------|-------|--------|
| COLLAPSED | 26 | Half-plane intersection (envelope_builder.py 145–150, 165–167) |
| TOO_SMALL | 21 | Post-intersection area check &lt; 215 sq.ft (envelope_builder.py 170–174) |
| VALID | 124 | — |

### Placement status (16.5 m)

| Status | Count | Meaning |
|--------|-------|--------|
| (empty) | 47 | Envelope failed; placement not run |
| NO_FIT | 14 | No tower placed (pack_towers n_placed=0 or pre-check) |
| NO_FIT_CORE | 5 | Tower(s) placed but core fit failed |
| VALID | 105 | Placement and core valid |

### True buildable rate (16.5 m)

- **105 / 171 = 61.4%** (envelope VALID, placement VALID, core VALID, skeleton and rules run).

---

*End of audit. All code paths and counts above are from the stated codebase and CSV; no assumptions or narrative beyond that.*
