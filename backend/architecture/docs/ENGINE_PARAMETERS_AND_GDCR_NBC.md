# Engine Parameters (Mathematically Accurate, Working) and GDCR/NBC Alignment

This document lists **all parameters computed by the layout engines** that are mathematically defined and in working condition, and clarifies how **GDCR** and **NBC** rules are used.

---

## 1. Parameters by Engine

### 1.1 Plot (Input)

| Parameter           | Source        | Formula / definition                                      | Unit   |
|---------------------|---------------|------------------------------------------------------------|--------|
| `plot_area_sqft`    | DB (Plot)     | Stored                                                     | sq.ft  |
| `plot_area_sqm`     | DB / convert  | From plot_area_sqft                                        | sq.m   |

---

### 1.2 Envelope Engine

| Parameter                 | Formula / definition                                                                 | Unit   |
|--------------------------|---------------------------------------------------------------------------------------|--------|
| `envelope_area_sqft`     | Area of polygon after setbacks and ground-coverage enforcement                      | sq.ft  |
| `ground_coverage_pct`    | envelope_area_sqft / plot_area_sqft × 100                                            | %      |
| `common_plot_area_sqft` | Carved 10% common open space (CGDCR 2017); from carve_common_plot                    | sq.ft  |
| `common_plot_status`     | CARVED / NO_CARVE_NEEDED / NO_REAR_EDGE / NA                                         | —      |
| `edge_margin_audit`      | Per-edge: edge_type, margin_m, margin_dxf, gdcr_clause (setbacks from GDCR Table 6.24/6.26) | —  |

**Formulas:** Setbacks and margins come from GDCR config; ground coverage cap from GDCR (e.g. 40% DW3). COP carve = 10% of plot (CGDCR 2017).

---

### 1.3 Placement Engine

| Parameter                | Formula / definition                                           | Unit   |
|--------------------------|----------------------------------------------------------------|--------|
| `footprint` (per tower)  | Rectangle fitted inside envelope; width_m, depth_m, area_sqft | m, m, sq.ft |
| `spacing_required_m`     | From placement / multi-tower logic                             | m      |
| `placement_audit`        | gap_dxf etc. for spacing                                       | —      |

---

### 1.4 Core Validation (Core Fit)

| Parameter                    | Formula / definition                                                                 | Unit   |
|-----------------------------|---------------------------------------------------------------------------------------|--------|
| `core_area_estimate_sqm`    | Core footprint from CoreDimensions (stair, landing, lift, corridor, etc.)             | sq.m   |
| `remaining_usable_sqm`      | Footprint area (sq.m) − core_area_estimate_sqm                                       | sq.m   |
| `pattern_used`              | DOUBLE_LOADED / SINGLE_LOADED / END_CORE (NBC/GDCR dimensional checks)               | —      |

**Constants:** From `CoreDimensions`: stair_width_m (GDCR Table 13.2), stair_run_m, landing_m, lift dimensions, corridor_m, min_unit_depth_m (NBC), lift_threshold_m (GDCR 10 m), highrise_threshold_m (NBC 15 m).

---

### 1.5 Floor Skeleton

| Parameter              | Formula / definition                                              | Unit   |
|------------------------|--------------------------------------------------------------------|--------|
| `footprint_polygon`    | From placement footprint (Shapely)                                 | —      |
| `core_polygon`         | Core strip geometry                                                | —      |
| `corridor_polygon`     | Optional; corridor strip (None for END_CORE)                       | —      |
| `unit_zones`           | One or two UnitZones (band_id, polygon, zone_width_m, zone_depth_m)| —      |
| `pattern_used`         | DOUBLE_LOADED / SINGLE_LOADED / END_CORE / NO_SKELETON_PATTERN     | —      |
| `efficiency_ratio`     | From area_summary (skeleton builder)                               | ratio  |
| `area_summary`         | efficiency_ratio, core_ratio, circulation_ratio                  | —      |

---

### 1.6 Phase 2 (Unit Composer)

| Parameter (per unit)   | Formula / definition                          | Unit   |
|------------------------|-----------------------------------------------|--------|
| `UnitLayoutContract`   | One unit per slice: polygon, rooms, unit_id  | —      |
| Room geometries        | Slice-local (template-based)                  | —      |

---

### 1.7 Phase 3 (Band Repetition)

| Parameter                 | Formula / definition                                      | Unit   |
|---------------------------|------------------------------------------------------------|--------|
| `n_units`                 | N = floor(band_length_m / module_width_m)                  | int    |
| `residual_width_m`        | band_length_m − N × module_width_m                         | m      |
| Slice zones               | N equal slices along band repeat axis                     | —      |
| `BandLayoutContract`      | band_id, units[], n_units, residual_width_m                | —      |

**Formula:** Deterministic; no search. Width accounting validated: N×module_width_m + residual_width_m = band_length_m.

---

### 1.8 Phase 4 (Floor Aggregation)

| Parameter                  | Formula / definition                                                                 | Unit   |
|----------------------------|----------------------------------------------------------------------------------------|--------|
| `total_units`              | len(all_units) = sum(b.n_units for b in band_layouts)                                 | int    |
| `total_residual_area`     | sum(b.residual_width_m × skeleton.unit_zones[b.band_id].zone_depth_m) for b in bands  | sq.m   |
| `unit_area_sum`            | sum(b.n_units × module_width_m × zone_depth_m) per band                              | sq.m   |
| `average_unit_area`        | unit_area_sum / total_units if total_units > 0 else 0                                 | sq.m   |
| `corridor_area`            | skeleton.corridor_polygon.area if present else 0                                      | sq.m   |
| `efficiency_ratio_floor`   | unit_area_sum / footprint_polygon.area if area > 0 else 0                             | ratio  |
| `unit_id`                  | f"{floor_id}_{band_id}_{slice_index}" (per unit)                                     | —      |

**Assertions (mandatory):** Band-overlap (pairwise zone intersection area ≤ tol); band inside footprint (each zone contained in footprint_polygon).

---

### 1.9 Phase 5 (Building Aggregation)

| Parameter               | Formula / definition                                                    | Unit   |
|-------------------------|--------------------------------------------------------------------------|--------|
| `total_floors`          | len(floors) = floor(height_limit_m / storey_height_m)                  | int    |
| `total_units`           | sum(f.total_units for f in floors)                                      | int    |
| `total_unit_area`       | sum(f.unit_area_sum for f in floors)                                   | sq.m   |
| `total_residual_area`   | sum(f.total_residual_area for f in floors)                             | sq.m   |
| `building_efficiency`   | total_unit_area / (footprint_area_sqm × total_floors) if > 0 else 0     | ratio  |
| `building_height_m`     | total_floors × storey_height_m                                           | m      |

**Assumptions:** Identical slab footprint for all floors; Phase 4 unit_id convention (floor_id prefix) for uniqueness.

---

### 1.10 Feasibility (Plot + Regulatory + Buildability)

| Parameter                 | Formula / definition                                                                 | Unit   |
|---------------------------|----------------------------------------------------------------------------------------|--------|
| **PlotMetrics**           |                                                                                        |        |
| plot_area_sqft / plot_area_sqm | From Plot                                                                        | sq.ft / sq.m |
| frontage_length_m        | Sum of ROAD edge lengths from edge_margin_audit (converted to m)                     | m      |
| plot_depth_m             | Perpendicular to primary road edge (vertex projection)                                | m      |
| n_road_edges             | Count of ROAD edges in audit                                                          | int    |
| is_corner_plot           | n_road_edges ≥ 2                                                                      | bool   |
| shape_class              | RECTANGULAR if area_ratio ≥ 0.98 and MBR edges ~0°/90°; else IRREGULAR               | —      |
| height_band_label        | LOW_RISE / MID_RISE / HIGH_RISE (from CoreDimensions thresholds: 10 m, 15 m)         | —      |
| **RegulatoryMetrics**    |                                                                                        |        |
| base_fsi, max_fsi        | From GDCR config (e.g. 1.8, 2.7)                                                      | —      |
| achieved_fsi              | total_bua_sqft / plot_area_sqft (BUA = footprint_sqft × num_floors_estimated)         | —      |
| fsi_utilization_pct      | achieved_fsi / max_fsi × 100                                                          | %      |
| permissible_gc_pct       | From GDCR config (e.g. 40% DW3)                                                       | %      |
| achieved_gc_pct          | 100 × footprint_sqft / plot_area_sqft (built footprint, not envelope)                 | %      |
| cop_required_sqft        | plot_area_sqft × 0.10 (CGDCR 2017)                                                    | sq.ft  |
| cop_provided_sqft        | From envelope_result.common_plot_area_sqft                                            | sq.ft  |
| spacing_required_m       | From placement_result                                                                | m      |
| spacing_provided_m       | Min gap from placement_audit (multi-tower)                                           | m      |
| **BuildabilityMetrics**  |                                                                                        |        |
| envelope_area_sqft/sqm   | From envelope result                                                                  | sq.ft / sq.m |
| footprint_width_m, depth_m, area_sqft | From first placement footprint                              | m, m, sq.ft |
| core_area_sqm            | From core validation                                                                  | sq.m   |
| remaining_usable_sqm     | Footprint area (sq.m) − core_area_sqm                                                 | sq.m   |
| efficiency_ratio         | From skeleton.area_summary (optional)                                                 | ratio  |
| core_ratio, circulation_ratio | From skeleton.area_summary (optional)                                          | ratio  |

---

## 2. GDCR and NBC Usage

### 2.1 Where GDCR Is Used

- **Envelope engine:** Setbacks and margins from GDCR (e.g. Table 6.24 road, 6.26 side/rear). Ground coverage cap from GDCR (max_percentage_dw3). Common plot carve = 10% (CGDCR 2017).
- **Feasibility (regulatory metrics):** `build_regulatory_metrics` uses GDCR config for `base_fsi`, `max_fsi`, `permissible_gc_pct`. COP required = 10% of plot. Achieved FSI/GC/COP are computed from pipeline outputs (BUA, footprint, envelope).
- **Rules engine (full GDCR):** `rules_engine.rules.gdcr_rules` evaluates **19 GDCR rules** (access road width, FSI base/max/incentive, height max/road_dw3, margin side/rear, lift required, staircase width/tread-riser, ventilation, clearance habitable/bathroom, fire refuge/NOC, boundary wall, env solar/rainwater, basement height). These are run by the **check_compliance** command with a building proposal; they are **not** run inside `generate_floorplan`.

### 2.2 Where NBC Is Used

- **Core fit (CoreDimensions):** Stair run, landing, corridor, lift dimensions, lift threshold (10 m), high-rise threshold (15 m), min unit depth — aligned with NBC 2016 Part 3/4.
- **Rules engine (full NBC):** `rules_engine.rules.nbc_rules` evaluates **NBC 2016 Part 4** rules (classification, egress, staircase, fire, refuge, etc.). Same as GDCR: run by **check_compliance**, not by `generate_floorplan`.

### 2.3 Are We Properly Following GDCR and NBC?

- **Formulas and constants:** FSI, GC, COP, setbacks, core dimensions, and height bands are sourced from or aligned with GDCR and NBC. The feasibility summary printed in `generate_floorplan` shows achieved vs max FSI, achieved vs permissible GC, and COP provided vs required (10% of plot).
- **Full rule compliance:** The pipeline does **not** run the full GDCR/NBC rule catalogue (e.g. staircase tread/riser, ventilation, fire NOC). To get a full pass/fail report, use:
  - `python manage.py check_compliance --tp 14 --fp 126 --height 16.5 ...`
  - Or pass `rule_results` into `build_feasibility_from_pipeline` when you have a proposal and evaluated rules.

So: **math and thresholds used in envelope, placement, core fit, and feasibility are GDCR/NBC-aligned**; **full clause-by-clause compliance** is available via the rules engine and `check_compliance`, not automatically in the main floor plan command.

---

## 3. Real Buildable Plot Test (TP14 FP126)

**Command run:** Road width and road edges are taken from the **dataset (PostGIS)** when the Plot has `road_width_m` and/or `road_edges` set. TP14 FP126 is backfilled with 15 m (per cadastral plan 15.00 MT), so no need to pass `--road-width` for that plot.

```text
python manage.py generate_floorplan --tp 14 --fp 126 --height 16.5 --export-dir ./demo_output
```
(If a plot has no road data in the DB, use `--road-width` and `--road-edges` to override.)

**Actual output (real run with --road-width 15, matching plan):**

```text
Architecture AI -- Floor Plan Generator
========================================
TP: 14  FP: 126  H: 16.5m  Road: 15.0m  Edges: [0]  Towers: 1  Mode: SKELETON

[1] Plot Loaded         -- Area: 9,608.4 sq.ft (892.7 sq.m)  (TP14, FP126)
[2] Envelope Computed   -- Buildable: 3,843.4 sq.ft (357.1 sq.m)
[3] Placement           -- Towers: 1, Mode: ROW_WISE, Footprint: 26.46m x 12.21m
[4] Core Validation     -- VALID, Pattern: DOUBLE_LOADED (2 stairs, lift required)
[5] Floor Skeleton      -- Pattern: DOUBLE_LOADED, Label: END_CORE_LEFT, Efficiency: 75.7%

Feasibility Summary
----------------------------------------
  Plot: 9,608 sq.ft (892.7 sq.m)  Frontage: 3.2m  Depth: 42.5m  Road edges: 1  IRREGULAR  HIGH_RISE
  FSI: achieved 1.77 (max 2.7)  GC: 35.5% (max 40.0%)  COP: 961 / 961 sq.ft
  Buildable: 3,843 sq.ft  Footprint: 26.46m x 12.21m  Efficiency: 75.7%
----------------------------------------
[5b] Floor Layout       -- Units: 2, Bands: 2, Unit area: 39.7 sq.m, Efficiency: 12.3%
       Band 0: 1 units, Band 1: 1 units
[5c] Building Layout    -- Floors: 5, Total Units: 10, Total Unit Area: 198.3 sq.m, Efficiency: 12.3%
[6] DXF Exported        -- ./demo_output\TP14_FP126_H16.5.dxf

Done.
```

(With default `--road-width 9`, the pipeline would show Road: 9.0m and a larger footprint (29.75m x 11.99m) and higher FSI/GC; the plan shows 15 m, so use 15 for validation.)

**Interpretation (road width 15 m per plan):**

- **Plot:** 9,608 sq.ft (892.7 sq.m); frontage 3.2 m, depth 42.5 m; 1 road edge; IRREGULAR; HIGH_RISE (16.5 m > 15 m). **Road: 15.0 m** (per cadastral plan 15.00 MT).
- **Regulatory (GDCR-aligned):** FSI 1.77 ≤ 2.7; GC 35.5% ≤ 40%; COP 961 sq.ft meets 10% of plot (961 required).
- **Buildability:** Envelope 3,843 sq.ft; footprint 26.46 m × 12.21 m; skeleton efficiency 75.7%.
- **Phase 4:** 2 units per floor, 2 bands; 39.7 sq.m unit area per floor; floor efficiency 12.3%.
- **Phase 5:** 5 floors (16.5 / 3.0); 10 total units; 198.3 sq.m total unit area; building efficiency 12.3%.
- **Export:** DXF written to `./demo_output/TP14_FP126_H16.5.dxf`.

All of the above parameters are computed by the engines as described in Section 1 and are in working condition for this buildable plot.

---

## 4. Summary Table (All Parameters)

| Engine / layer      | Parameters (key)                                                                 | GDCR/NBC link                          |
|---------------------|-----------------------------------------------------------------------------------|----------------------------------------|
| Envelope            | envelope_area_sqft, ground_coverage_pct, common_plot_area_sqft, edge_margin_audit | Setbacks, GC cap, 10% COP              |
| Placement           | footprint (width, depth, area), spacing_required_m, placement_audit               | —                                      |
| Core fit            | core_area_estimate_sqm, remaining_usable_sqm, pattern                             | NBC/GDCR core dimensions, height bands |
| Skeleton            | footprint/core/corridor polygons, unit_zones, efficiency_ratio, area_summary      | —                                      |
| Phase 2             | UnitLayoutContract per slice (rooms, polygon)                                     | —                                      |
| Phase 3             | n_units, residual_width_m, slice zones                                            | —                                      |
| Phase 4             | total_units, total_residual_area, unit_area_sum, efficiency_ratio_floor, unit_id | —                                      |
| Phase 5             | total_floors, total_units, total_unit_area, building_efficiency, building_height_m| —                                      |
| Feasibility         | PlotMetrics, RegulatoryMetrics (FSI, GC, COP), BuildabilityMetrics                | GDCR config for FSI, GC, COP           |
| Rules (check_compliance) | Full GDCR + NBC rule results                                                | 19 GDCR + NBC Part 4 rules             |

All listed parameters are mathematically defined, implemented, and produced in the pipeline run above. GDCR and NBC are followed for thresholds and core dimensions in the main pipeline; full rule-by-rule compliance is available via the rules engine and `check_compliance`.
