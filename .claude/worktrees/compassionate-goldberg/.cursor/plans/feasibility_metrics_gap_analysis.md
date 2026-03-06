# Feasibility Metrics — Gap Analysis

**Objective:** Audit the Architecture AI backend to verify whether key residential feasibility parameters are fully computed, stored, and exposed for a regulatory-grade feasibility report.

**Audience:** CTO + senior architect.  
**Mode:** Analysis / plan only. No code written.

---

## Executive summary

| Question | Answer |
|----------|--------|
| **Do we compute and store most regulatory and buildability metrics?** | **Partially.** Many values are computed inside pipelines (envelope, placement, skeleton, rules) but live in different layers: DB models (Plot, PlotEnvelope, BuildingProposal, ComplianceResult, FootprintRecord), in-memory results (EnvelopeResult, FloorSkeleton.area_summary, CoreValidationResult), or only in rule evaluation (FSI required/actual). |
| **Are they exposed in a single place (e.g. generate_floorplan)?** | **No.** `generate_floorplan` prints a minimal linear summary (plot area, buildable area, footprint size, efficiency). It does not persist to DB, does not run compliance, and does not return or write a structured report. |
| **Is there a single FeasibilityReport-style aggregate?** | **No.** There is no type or API that aggregates plot metrics + regulatory metrics + buildability + compliance into one object. |
| **Are we ready to present a regulatory feasibility summary to a client?** | **No.** Key numbers (FSI permissible/achieved, GC permissible/achieved, COP required/provided, frontage, plot depth, height band, setback breakdown) are either missing, scattered, or only in CLI/DB with no unified export. A frontend or report generator would have to call multiple services and join several models. |

---

## SECTION 1 — Plot metrics

| Metric | Status | Where computed | Stored in DB? | Exposed in generate_floorplan? |
|--------|--------|----------------|---------------|---------------------------------|
| **Plot area (sq.m / sq.ft)** | Partial | `tp_ingestion`: `Plot.area_geometry`, `Plot.area_excel`. Ingestion: `area_validator`, `excel_reader`. | Yes — `Plot.area_geometry`, `Plot.area_excel` | Yes — printed as "Area: X sq.ft (Y sq.m)" (line 121–123). **Caveat:** Model docstring says area_geometry is "sq.m" but the entire pipeline (envelope, rules, evaluator, generate_floorplan) treats it as **sq.ft** (DXF unit). This is a **documentation/contract bug**. |
| **Frontage length (road-facing edge length)** | **Missing** | Not computed as a named metric. Data exists inside envelope: `EdgeSpec.length` (DXF) per edge; `edge_margin_audit` has `length_dxf` per edge. Frontage = sum of lengths for edges with `edge_type == "ROAD"`. | No field on Plot or PlotEnvelope | No |
| **Plot depth** | **Missing** | Not defined or stored at plot level. "Depth" appears only as placement/footprint concept: `FootprintRecord.footprint_depth_m`, `core_fit` `depth_m`, unit zone `zone_depth_m`. | No | No |
| **Number of road edges** | Implemented | Input: `road_facing_edges` (list of indices). Stored on envelope. | Yes — `PlotEnvelope.road_facing_edges` (JSONField). Not on Plot. | No (only as input to pipeline) |
| **Road width (input vs stored)** | Implemented | Passed as input to envelope and compliance. | Yes — `PlotEnvelope.road_width_used`; `BuildingProposal.road_width` | No |
| **Corner plot detection** | Partial | Logic exists: `envelope_engine/geometry/edge_classifier.py` (corner = 2 road edges; REAR = most parallel non-road). No explicit boolean stored. | No "is_corner_plot" field | No |
| **Shape classification (rectangular / irregular)** | **Missing** | Not computed. Test code uses `geom_type != "Polygon"` or bbox ratio for "irregular" grouping only. No service or model field. | No | No |

**Section 1 summary:** Plot area is available but unit semantics are inconsistent. Frontage, plot depth, and shape classification are not computed or exposed. Road edges and road width are stored at envelope/proposal level, not as first-class plot attributes.

---

## SECTION 2 — Regulatory metrics

| Metric | Status | Where computed | Stored in DB? | Printed / accessible? |
|--------|--------|----------------|---------------|-------------------------|
| **Permissible FSI** | Partial | From GDCR config: `rules_engine/rules/gdcr_rules.py` — `base_fsi`, `maximum_fsi`, incentive `max_fsi`; used in `evaluate_gdcr_fsi_base`, `evaluate_gdcr_fsi_max`. | No. Only in rule `required_value` at evaluation time (and in `ComplianceResult.required_value` per rule). No proposal-level "permissible_fsi" field. | In compliance report as per-rule "Required" column. |
| **Achieved FSI** | Partial | Same file: `actual_fsi = bua / plot_area`. | No proposal-level "achieved_fsi". Stored only as `ComplianceResult.actual_value` for the FSI rule rows. | In compliance report "Actual" column for FSI rules. |
| **Ground coverage permissible** | Partial | `envelope_engine/geometry/coverage_enforcer.py`: `_gdcr_max_gc_pct()` from GDCR config (e.g. 40%). Used for enforcement only. | No "max_gc_pct" or "permissible_gc" on PlotEnvelope. | Not printed in a report. |
| **Ground coverage achieved** | Implemented | Envelope pipeline: `envelope_area / plot_area * 100`. | Yes — `PlotEnvelope.ground_coverage_pct` | Yes — in `compute_envelope` command and in envelope audit. |
| **COP required** | Partial | Implicit: 10% in `common_plot_carver.py`. Not a named constant or field. | No "common_plot_required_sqft" | No |
| **COP provided** | Implemented | Common plot carver returns area; envelope service sets it. | Yes — `PlotEnvelope.common_plot_area_sqft`, `common_plot_status` | Yes — in compute_envelope report. |
| **Height band classification** | **Missing** | Max height by road width from GDCR (Table 6.23) is used in `evaluate_gdcr_height_road_width`. No explicit "height band" label (e.g. "16.5–25 m"). | No | No |
| **Inter-building spacing requirement** | Implemented | `placement_engine/geometry/spacing_enforcer.py`: GDCR Table 6.25, `max(H/3, minimum_spacing_m)`. | Yes — `BuildingPlacement.spacing_required_m`, `spacing_required_dxf`; per-pair in placement audit. | In compute_placement report. |
| **Setback breakdown per edge** | Implemented | `envelope_engine`: `margin_resolver` + `margin_audit_log()`. Each edge: `edge_index`, `edge_type`, `margin_m`, `margin_dxf`, `gdcr_clause`. | Yes — `PlotEnvelope.edge_margin_audit` (JSONField list of dicts). | Yes — in compute_envelope `_print_report()`. |
| **Margin rule (H/5 or table)** | Implemented | `envelope_engine/geometry/margin_resolver.py`: ROAD = max(table, H/5, min_road_margin); SIDE/REAR from GDCR `side_rear_margin.height_margin_map`. GDCR.yaml: `road_side_margin.height_formula: "H / 5"`, `road_width_margin_map`. | Encoded in `edge_margin_audit` (gdcr_clause, margin_m). | In envelope report per edge. |

**Section 2 summary:** Achieved GC, COP provided, spacing, and full setback breakdown are stored and/or printed. Permissible FSI/GC and COP required are not first-class fields. Height band is not classified or stored. FSI permissible/achieved are only in compliance rule rows, not as top-level proposal metrics.

---

## SECTION 3 — Buildability metrics

| Metric | Status | Where computed | Stored in structured object? | Printed in CLI? |
|--------|--------|----------------|------------------------------|-----------------|
| **Buildable envelope area** | Implemented | `envelope_engine`: `EnvelopeResult.envelope_area_sqft`, `PlotEnvelope.envelope_area_sqft`. | Yes — PlotEnvelope, EnvelopeResult | Yes — generate_floorplan "[2] Buildable: X sq.ft"; compute_envelope. |
| **Efficiency ratio** | Implemented | `floor_skeleton/skeleton_evaluator.py`: `compute_area_summary()`; `efficiency_ratio = unit_area / footprint_area`. Stored on `FloorSkeleton.efficiency_ratio` and `area_summary["efficiency_ratio"]`. | In-memory only — `FloorSkeleton.area_summary`, `.efficiency_ratio`. Not persisted to DB. | Yes — generate_floorplan "[5] Efficiency: X%". |
| **Core-to-slab ratio** | Implemented | Same: `area_summary["core_ratio"]` = core_area / footprint_area. | In-memory only — FloorSkeleton.area_summary | In DXF annotation and presentation title block (area breakdown). Not in generate_floorplan stdout. |
| **Circulation ratio** | Implemented | Same: `area_summary["circulation_ratio"]`. | In-memory only | Same as above. |
| **Net usable unit area** | Implemented | `area_summary["unit_area_sqm"]`; `CoreValidationResult.remaining_usable_sqm` in placement. | In-memory (skeleton) and in FootprintRecord.core_validation JSON (remaining_usable_sqm). | compute_placement prints "Remaining usable: X sq.m". Not in generate_floorplan. |
| **Slab depth/width after setbacks** | Implemented | Placed footprint = slab after envelope. `FootprintRecord.footprint_width_m`, `footprint_depth_m`; in-memory `FootprintRecord` from placement also has width_m, depth_m. | Yes — BuildingPlacement → FootprintRecord (footprint_width_m, footprint_depth_m). | Yes — generate_floorplan "[3] Footprint: W m x D m". |

**Section 3 summary:** All listed buildability metrics are computed. Envelope area and slab dimensions are persisted (envelope + placement models). Efficiency, core ratio, circulation, and net usable are only in-memory (FloorSkeleton, core_validation JSON); there is no dedicated BuildabilityResult table or single persisted "buildability" record for a run.

---

## SECTION 4 — Compliance visibility

| Item | Status | Location |
|------|--------|----------|
| **ComplianceResult model** | Implemented | `rules_engine/models.py`: `ComplianceResult` with `proposal`, `rule_id`, `rule_source`, `category`, `description`, `status`, `required_value`, `actual_value`, `unit`, `note`, `evaluated_at`. |
| **Rule engine stores computed values** | Yes | `RuleResult` (base) and `ComplianceResult` have `required_value`, `actual_value`. GDCR/NBC evaluators pass these to `_result()`. `check_compliance` bulk_creates ComplianceResult rows. |
| **Structured compliance summary** | Partial | `rules_engine/services/report.py`: `as_dict(results)` returns `{"summary": {total, pass, fail, info, na, missing_data, compliant}, "results": [{rule_id, status, required_value, actual_value, ...}]}`. Summary is computed on the fly from a list of RuleResult; not stored as a single row or document. |

**Section 4 summary:** ComplianceResult captures numeric metrics per rule. There is no single "compliance summary" record (e.g. one row per proposal with pass_count, fail_count, compliant); that is derived when calling `as_dict()` or `print_report()`.

---

## SECTION 5 — Frontend readiness

| Question | Answer |
|----------|--------|
| **Single structured FeasibilityReport object?** | **No.** No type or class named `FeasibilityReport` or equivalent. |
| **Aggregation of plot + regulatory + buildability + compliance?** | **No.** Each domain has its own models and commands. To build a full feasibility view, a consumer would need to: (1) load Plot, (2) run or load envelope (PlotEnvelope), (3) run or load placement (BuildingPlacement, FootprintRecord), (4) run skeleton (in-memory FloorSkeleton) for ratios, (5) run compliance (BuildingProposal + ComplianceResult) and optionally report.as_dict(). No single API or document aggregates these. |
| **Recommended architecture for a report model** | Introduce a **FeasibilityReport** (dataclass or Django model) that holds: (a) **plot_metrics**: plot_id, area_sqft, area_sqm, frontage_m, plot_depth_m, n_road_edges, road_width_m, is_corner_plot, shape_class; (b) **regulatory_metrics**: permissible_fsi, achieved_fsi, permissible_gc_pct, achieved_gc_pct, cop_required_sqft, cop_provided_sqft, height_band, spacing_required_m, edge_margin_audit (or list of setback rows); (c) **buildability_metrics**: envelope_area_sqft, footprint_width_m, footprint_depth_m, efficiency_ratio, core_ratio, circulation_ratio, net_usable_sqm; (d) **compliance**: summary (pass/fail counts, compliant bool) + list of rule results (or FK to ComplianceResult). Either populate it from existing services in one "feasibility" service or persist it as a report snapshot (e.g. one row per proposal + version). |

---

## Where each metric lives (code references)

- **Plot area:** `tp_ingestion/models.py` — `Plot.area_geometry`, `area_excel`. Used as sq.ft in `generate_floorplan.py`, `envelope_engine`, `rules_engine/services/evaluator.py`.
- **Envelope / GC / COP / setbacks:** `envelope_engine/models.py` — `PlotEnvelope` (envelope_area_sqft, ground_coverage_pct, common_plot_area_sqft, common_plot_status, edge_margin_audit, road_width_used, road_facing_edges). `envelope_engine/services/envelope_service.py` — `EnvelopeResult`; `margin_resolver.margin_audit_log()`.
- **Placement / slab / spacing:** `placement_engine/models.py` — `BuildingPlacement`, `FootprintRecord` (footprint_width_m, footprint_depth_m, footprint_area_sqft, core_validation JSON). `placement_engine/geometry/spacing_enforcer.py` — spacing requirement.
- **Buildability ratios / net usable:** `floor_skeleton/skeleton_evaluator.py` — `compute_area_summary()` → `FloorSkeleton.area_summary`; `placement_engine/geometry/core_fit.py` — `CoreValidationResult.remaining_usable_sqm`.
- **FSI / GC rules:** `rules_engine/rules/gdcr_rules.py` — `evaluate_gdcr_fsi_base`, `evaluate_gdcr_fsi_max`; GDCR config for permissible values.
- **Compliance storage and report:** `rules_engine/models.py` — `ComplianceResult`; `rules_engine/services/report.py` — `as_dict()`, `print_report()`.

---

## Recommended implementation priority (ordered)

1. **Clarify and fix plot area units** — Decide and document whether `Plot.area_geometry` is sq.m or sq.ft; align model, ingestion, and all consumers; add explicit `plot_area_sqft` / `plot_area_sqm` if both are needed.
2. **Compute and expose frontage** — Derive frontage from edge_margin_audit (sum of `length_dxf` for ROAD edges, convert to m). Store on PlotEnvelope or Plot; expose in any feasibility output.
3. **Define and populate a FeasibilityReport (or equivalent) aggregate** — Single structure (in-memory or persisted) that pulls plot metrics, regulatory metrics (from envelope + rules), buildability metrics (from envelope + placement + skeleton), and compliance summary. One service that runs pipeline (or reads from DB) and fills this structure.
4. **Store permissible vs achieved at proposal/report level** — Add fields (or report sections) for permissible_fsi, achieved_fsi, permissible_gc_pct, achieved_gc_pct, cop_required_sqft, cop_provided_sqft so the report does not depend only on rule rows.
5. **Plot depth and shape classification** — Define "plot depth" (e.g. perpendicular to primary road); compute and store. Add shape classification (e.g. rectangular vs irregular) from geometry and store.
6. **Height band** — Derive from GDCR road-width vs height table; store as a label or enum on proposal/report.
7. **Persist buildability summary** — Optionally persist efficiency_ratio, core_ratio, circulation_ratio (e.g. on a BuildabilityResult or inside FeasibilityReport) so the frontend does not need to re-run skeleton.

---

## Are we ready to present a regulatory feasibility summary to the client?

**No.**

- **Missing for regulatory credibility:** Explicit permissible vs achieved FSI/GC/COP in one place; frontage; plot depth; height band; COP required; single document or API that ties all of these together.
- **Fragmented today:** Metrics are spread across Plot, PlotEnvelope, BuildingPlacement, FootprintRecord, FloorSkeleton (in-memory), ComplianceResult, and CLI output. No one place to "get the feasibility report."
- **generate_floorplan does not produce a report:** It prints a short pipeline summary and writes DXF. It does not run compliance, does not persist results, and does not output a structured feasibility summary.
- **Compliance is rule-row only:** ComplianceResult and report.as_dict() are suitable for a compliance table and summary counts but are not combined with plot, envelope, and buildability into one client-ready deliverable.

To be ready: implement the FeasibilityReport (or equivalent) aggregate, populate it from existing engines, and expose it via an API or export (e.g. JSON/PDF) that includes plot metrics, regulatory metrics (with permissible/achieved), buildability metrics, and compliance summary in one place.
