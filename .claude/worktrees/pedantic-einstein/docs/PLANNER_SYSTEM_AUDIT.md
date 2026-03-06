# AI Site Planning System — Full System Audit

**Date:** 2025-03-04  
**Scope:** Backend pipeline, geometry efficiency, planning logic, UI visualization, metrics, performance, workflow UX, floor-planning readiness, and prioritized improvements.

---

## STEP 1 — Site Planning Pipeline Analysis

### Pipeline order (current)

1. Plot ingestion (Plot.geom)
2. Road edge detection → `detect_road_edges_with_meta`
3. **Envelope** (`compute_envelope`): setbacks → GC enforcement → COP carve → effective envelope
4. **Internal road network** (envelope + COP)
5. **Road corridor subtraction** from envelope → `final_envelope`
6. **Placement zones** from `final_envelope` (for visualization only)
7. **Tower placement** on whole `final_envelope` (not per-zone)
8. **Parking preparation** on `final_envelope` (not on envelope minus towers)
9. Geometry serialization + validation

### Issues identified

| # | Issue | Why it is a problem | Recommended solution |
|---|--------|----------------------|------------------------|
| 1.1 | **Tower placement ignores placement zones** | `generate_placement_zones` produces ranked candidate zones, but `compute_placement` is called with the entire `final_envelope`. Placement does not prefer or constrain towers to zones, so zone ranking has no effect on outcome. | Either (a) run placement per zone (e.g. place one tower per zone up to n_towers), or (b) pass zone boundaries into the packer so it places only inside zones and respects zone ranking. Prefer (a) for clarity and road-access per zone. |
| 1.2 | **Parking uses envelope before tower subtraction** | `prepare_parking_zones(final_envelope)` is called before subtracting tower footprints. Parking candidate zones therefore include area that is already occupied by towers, so the UI shows parking over tower footprints. | Compute parking on `final_envelope.difference(union(tower_footprints))` (or equivalent) so candidates are only in remaining open area. Implement in `plan_job_service` after tower placement. |
| 1.3 | **No validation that towers have road access** | Tower placement is purely geometric (packer + spacing). There is no check that each footprint is reachable from the internal road network (e.g. within a short walk/buffer of `tower_access_nodes` or road corridor). | After placement, filter or adjust footprints: require each tower centroid to be within a configurable distance of the road corridor or a tower access node. Optionally expose “road access” in metrics/audit. |
| 1.4 | **COP placement strategy is fixed** | Envelope pipeline uses a single COP strategy (e.g. edge/rear strip). There is no optimization for “COP near road” or “COP touching road” as required by some interpretations of GDCR. | Use `common_plot_generator` (or equivalent) to evaluate COP candidates that touch road and meet area; integrate into envelope pipeline as an option and surface strategy in plan result. |
| 1.5 | **Redundant geometry serialization** | `envelope_geo` is built from `final_envelope`; then `result["geometry"]["envelope"]` is overwritten by `validate_geojson_geometry(envelope_geo)`, which parses GeoJSON back to Shapely and may return new GeoJSON. Double conversion. | Validate once (e.g. validate `final_envelope` in Shapely space before serialization), then serialize to GeoJSON once. |
| 1.6 | **Corridor subtraction can leave MultiPolygon; only largest part used** | After `final_envelope.difference(corridor_union)`, the code takes `max(final_envelope.geoms, key=area)` if it’s a MultiPolygon. Other islands are dropped, so buildable area on secondary islands is lost. | Either keep MultiPolygon and pass it to placement (packer already supports MultiPolygon via `find_best_in_components`), or explicitly document that only the largest island is buildable and surface “buildable islands” in metrics. |
| 1.7 | **No explicit validation step between pipeline stages** | Each stage assumes valid input. Invalid or empty geometry from one stage can propagate (e.g. empty envelope after corridor subtraction) and cause confusing failures later. | Add lightweight validation after critical steps (e.g. envelope not empty, polygon valid). Optionally add a small “pipeline validation” layer that checks invariants (e.g. COP ⊆ plot, envelope ⊆ plot). |

---

## STEP 2 — Geometry Efficiency

### Current usage

- Shapely used throughout: `difference`, `intersection`, `buffer`, `unary_union`, WKT load/dump, GeoJSON shape/__geo_interface__.
- No use of STRtree or spatial indexing in the planning codebase (only in tests/libraries).
- Plot WKT is parsed once per job; envelope and road results are not cached across jobs.

### Issues and optimizations

| # | Issue | Why it is a problem | Recommended solution |
|---|--------|----------------------|------------------------|
| 2.1 | **No spatial indexing** | Pairwise checks (e.g. “tower vs road”, “tower vs tower”) use full geometry ops. With many towers or complex polygons this scales poorly. | Use Shapely STRtree for “which towers intersect buffer(road)?” and for spacing audits. Reduces redundant intersection tests. |
| 2.2 | **Repeated WKT/GeoJSON conversion** | `geom.wkt`, `shapely_loads(geom.wkt)`, `geometry_to_geojson`, `wkt_to_geojson` are used in sequence in places. Same geometry is converted multiple times. | Keep a single “canonical” representation per layer (e.g. Shapely in worker, convert to GeoJSON once at the end for API response). |
| 2.3 | **No memoization of expensive ops** | e.g. `unary_union(corridors)` and `final_envelope.difference(corridor_union)` are not cached. Re-running the same job would recompute everything. | For same plot + same inputs, consider caching envelope and road results (e.g. keyed by plot_id + input hash). Less critical if jobs are one-off. |
| 2.4 | **Invalid geometry repair ad hoc** | `validate_geojson_geometry` uses `make_valid`/buffer(0); placement_zone_engine uses `buffer(0)` for envelope. Repair strategy is scattered. | Centralize in `utils.geometry_validation`: one function “ensure_valid_polygon(geom)” used by all callers. Document when to use repair vs fail-fast. |
| 2.5 | **Polygon area in mixed units** | Envelope and placement work in DXF feet; metrics mix sqft and sqm. Area comparisons (e.g. min_zone_area_sqft) are correct but easy to misuse. | Document units in one place (e.g. “plan_job_service: plot from DB in m², internal geometry in DXF feet, API metrics in sqft/sqm as specified”). Add unit constants or converters at boundaries. |

---

## STEP 3 — Planning Logic (Architectural Rules)

| # | Missing / weak rule | Why it matters | Concrete improvement |
|---|----------------------|----------------|------------------------|
| 3.1 | **Road access for towers** | Real schemes require every building to be accessible from the internal road. | After placement, for each footprint check `footprint.centroid` distance to road corridor (or tower_access_nodes). Reject or flag placements beyond e.g. 15–20 m; optionally move packer to prefer zones closer to road. |
| 3.2 | **Tower orientation vs road** | No explicit “front” of tower toward road. | Use existing `orientation_finder`; add constraint that primary orientation is toward nearest road segment (or allow configurable “front toward road” in placement). |
| 3.3 | **Sunlight / spacing** | Spacing is H/3; no explicit sunlight or open-space view rules. | Keep H/3 as baseline; document as “fire/open-space spacing”. Add optional sunlight vector and “no shadow on COP” or “min open angle” later if required by GDCR. |
| 3.4 | **Parking requirement** | Parking engine only produces candidate zones; no check that total parking area meets byelaw (e.g. per unit or per BUA). | Define required parking area (e.g. from BUA or unit count); compare with `sum(parking_candidate_zones.area)`; surface “Parking required vs provided” in metrics. |
| 3.5 | **Fire access** | No explicit fire-tender access path to each tower. | Ensure road corridor (or a dedicated path) reaches within a defined distance of each tower; can reuse “road access” check with a fire-access distance. |
| 3.6 | **COP must touch road** | Some interpretations require COP to be reachable from road. | In COP placement, prefer candidates that intersect or touch `buffer(road_edges)`; validate in pipeline and set `copStatus` accordingly. |

---

## STEP 4 — UI Visualization

| # | Issue | Why it is a problem | Solution |
|---|--------|----------------------|----------|
| 4.1 | **Redundant controls** | Both “Legend” (quick toggles) and “Layers” panel (checkboxes) control the same visibility. Two sources of truth can get out of sync and confuse users. | Keep one primary control (e.g. LayerControl panel); make Legend a compact reflection of the same state, or remove Legend and rely on LayerControl only. |
| 4.2 | **Layer hierarchy not obvious** | All layers appear flat (Plot, Setbacks, Envelope, COP, Roads, Corridors, Tower Zones, Towers, Parking, Spacing, Labels). Users may not understand that e.g. envelope is inside plot, COP inside envelope. | Add optional “stack order” or grouping in the LayerControl (e.g. “Boundaries”, “Circulation”, “Buildings”, “Debug”) and/or a short help tooltip per layer. |
| 4.3 | **Poor visual contrast** | Some layers use similar shades (e.g. grey roads and grey parking). In the screenshot, readability could be improved. | Differentiate by fill + stroke (e.g. roads: stroke-only, parking: light hatch or distinct color). Ensure WCAG contrast for any text on layers. |
| 4.4 | **Missing scale bar** | No scale bar on the SVG canvas, so users cannot judge distances. | Add a scale bar component that uses `viewTransform` and plot bounds to show e.g. “0 — 50 m” and place it in a corner of the canvas. |
| 4.5 | **No zoom-to-selection** | “Fit” and “Reset” zoom to full extent. Users cannot zoom to a selected tower or to a specific layer’s extent. | Add “Zoom to selection” (e.g. when a tower is selected, fit view to that tower’s bbox with padding). Optionally “Zoom to layer” for current visible layers. |
| 4.6 | **Tower selection feedback** | Selected tower is highlighted and “Design Floor Plan” appears, but there is no persistent indication of which tower index is selected (e.g. “Tower 2 of 3”). | Show “Tower 1 of N” (or “Tower A”) in the bottom bar or in the step navigation area when a tower is selected. |
| 4.7 | **Tooltip position** | Tooltips use centroid; for long/thin polygons the centroid can be outside the shape or in a busy area. | Keep centroid as default; optionally clamp tooltip to viewport and add a small offset so it doesn’t sit under the cursor. |
| 4.8 | **Floors label misleading** | “Floors” in Planning Metrics shows `buildingHeightM` (height in metres), not floor count. So “70” means 70 m, not 70 storeys. | Rename to “Building height (m)” or compute and show “Floors” separately (e.g. height_m / storey_height_m) and keep “Height (m)” as secondary. |

---

## STEP 5 — Planning Metrics

| # | Issue | Why it is a problem | Correct formula / backend change |
|---|--------|----------------------|----------------------------------|
| 5.1 | **FSI not in plan result** | Plan result `metrics` does not include `maxFSI` or achieved FSI, so the frontend shows FSI as “—” or 0.00 after generation. | **Formula:** FSI = BUA / plot_area_sqm. Backend should compute BUA from placed towers (e.g. sum of footprint_area × floors or from regulatory solver) and add `achievedFSI` and `maxFSI` (permissible) to plan result metrics. |
| 5.2 | **BUA not computed from plan** | `maxBUA` in plan result is not set; frontend shows “—”. | **Formula:** BUA = Σ (tower_footprint_area_sqm × number_of_floors) per tower, or use height solver output. Backend: add `achievedBUA` (and optionally `maxBUA` from GDCR) to plan result. |
| 5.3 | **COP Required** | Frontend uses `copRequiredSqm` from metrics; backend does not currently send it. | Backend: add `copRequiredSqm` = max(plot_area_sqm × COP_REQUIRED_FRACTION, minimum_total_area_sqm) to plan result (same as site_metrics logic). |
| 5.4 | **Floors vs height** | “Floors” displayed as building height in metres. | Backend: add `floorCount` (e.g. from height_solver or height_m / storey_height_m). Frontend: show “Floors” from `floorCount` and optionally “Height (m)” from `buildingHeightM`. |
| 5.5 | **Efficiency ratios missing** | No corridor efficiency, FSI utilization %, or parking ratio. | Optional: add `fsiUtilizationPct` = achievedFSI / maxFSI × 100; `parkingRequiredSqm`, `parkingProvidedSqm` when parking rules are implemented. |

---

## STEP 6 — Performance

| # | Risk | When it hurts | Improvement |
|---|------|----------------|--------------|
| 6.1 | **Large plots / complex polygons** | Many vertices in plot or envelope cause slow `difference`/`intersection` and buffer ops. | Simplify geometry: use `simplify(tolerance)` for visualization; keep full resolution for compliance. Consider splitting very large plots into chunks for placement. |
| 6.2 | **Many towers** | Packer runs ROW_WISE and COL_WISE each with up to MAX_TOWERS iterations; spacing audit is O(n²) pairs. | Already capped (e.g. n_towers ≤ 4). For future scaling: use STRtree for spacing checks; consider early exit when envelope is too small. |
| 6.3 | **Frontend: many SVG path elements** | Every feature is a `<path>`; complex polygons with many rings can create large DOM and slow pan/zoom. | Paths are already memoized per feature in LayerPath. Add layer-level virtualization: only render paths for visible layers and, if needed, for features in viewport (e.g. clip by bbox). |
| 6.4 | **No worker for geometry** | Heavy parsing/grouping of GeoJSON happens on the main thread. | For very large responses, move `mapPlanGeometryToModel` and `groupFeaturesByLayer` to a Web Worker and pass serialized model to the main thread. |
| 6.5 | **Lazy loading layers** | All layers are rendered (subject to visibility); no lazy load. | For many layers, consider loading geometry by layer on demand (e.g. when user turns on a layer) if the API supports per-layer geometry. |

---

## STEP 7 — Workflow UX

| # | Gap | Impact | Suggestion |
|---|-----|--------|------------|
| 7.1 | **No scenario comparison** | Users cannot compare two scenarios side by side (e.g. 2 towers vs 3 towers). | Add “Compare” mode: select two scenarios and show two canvases or a diff of metrics and key geometry. |
| 7.2 | **Tower selection feedback** | Already noted in 4.6; worth repeating for workflow. | Clear “Tower 1 of N” and “Design Floor Plan” only when selection is valid. |
| 7.3 | **No geometry editing** | Users cannot nudge tower or adjust boundary in the UI. | Phase 2: allow “edit mode” to move a tower within envelope and re-run spacing/road access checks (or send to backend for re-validation). |
| 7.4 | **No undo/redo** | Changing inputs and regenerating replaces the scenario; no undo of the last generation. | Keep a short history of scenario results (e.g. last 3) and “Revert to previous” button. |
| 7.5 | **No scenario duplication** | Cannot duplicate a scenario to try a variant (e.g. same plot, different tower count). | “Duplicate scenario” that copies inputs and optionally re-runs job or keeps previous result for comparison. |

---

## STEP 8 — Floor Planning Integration

### Current state

- **Backend:** `architecture.services.development_pipeline` has `generate_optimal_development_floor_plans`; floor skeleton and layout exist in `floor_skeleton` and residential_layout.
- **Frontend:** Step 2 “Floor Plan” and route `/planner/floor`; `FloorPlanningView` shows selected tower footprint only. No core, corridor, units, or walls from backend yet.

### Gaps for floor layout phase

| # | Need | Location / change |
|---|------|--------------------|
| 8.1 | **API for floor layout** | Expose an endpoint that accepts `plan_id` (or job_id) + `tower_index` and returns floor layout geometry (core, corridor, units, walls) and unit metadata (type, carpet, built-up, RERA, efficiency). |
| 8.2 | **Frontend floor layers** | Once API exists, add layers: Tower footprint, Core, Corridor, Units, Walls. Reuse same layer/visibility pattern as site plan. |
| 8.3 | **Unit inspection** | UnitInspectionPanel and selectedUnit are ready; wire to floor layout API so clicking a unit polygon sets `selectedUnit` with backend data. |
| 8.4 | **Store and routing** | `selectedTowerIndex` and `planningStep` already support “Design Floor Plan”. Ensure floor page receives `job_id` + `tower_index` (from store or URL) and fetches floor layout for that tower. |

---

## STEP 9 — Prioritized Roadmap

### Critical (must fix soon)

1. **Parking on envelope minus towers** (1.2) — correctness of parking zones.
2. **Plan result metrics: FSI, BUA, COP Required, Floors** (5.1–5.4) — metrics panel is central to trust; currently wrong or empty.
3. **“Floors” label** (4.8) — avoid misreading height as floor count.

### Important (planning quality)

4. **Tower placement using zones** (1.1) — zones should drive placement.
5. **Road access validation for towers** (1.3, 3.1).
6. **COP required in plan result** (5.3).
7. **Pipeline validation** (1.7).
8. **Single envelope GeoJSON serialization** (1.5).

### Nice-to-have (UX and polish)

9. **Scale bar** (4.5).
10. **Zoom to selection** (4.5).
11. **Unify Legend vs LayerControl** (4.1).
12. **Layer grouping / tooltips** (4.2).
13. **Scenario comparison or duplicate** (7.1, 7.5).

---

## STEP 10 — Output Summary Table

| Id | Issue | Why it matters | Technical solution | Where | Priority |
|----|--------|----------------|--------------------|--------|----------|
| 1.1 | Placement ignores zones | Zones are computed but not used | Place towers per zone or constrain packer to zones | plan_job_service + placement_engine | Important |
| 1.2 | Parking includes tower area | Parking zones overlap towers | Parking = envelope − road − towers | plan_job_service | Critical |
| 1.3 | No road access check | Towers may be unreachable | Validate distance footprint–road; filter or adjust | plan_job_service or placement_engine | Important |
| 1.4 | COP strategy fixed | May not meet “COP near road” | Use COP generator; optional strategy | envelope_engine / plan_job_service | Nice-to-have |
| 1.5 | Double GeoJSON validation | Redundant work | Validate in Shapely; serialize once | plan_job_service | Important |
| 1.6 | MultiPolygon trimmed to one part | Lost buildable islands | Keep MultiPolygon or document | plan_job_service | Important |
| 1.7 | No pipeline validation | Silent propagation of bad geometry | Validate after envelope, after corridors | plan_job_service | Important |
| 2.1 | No spatial index | Slower with many features | STRtree for road/tower checks | architecture/engines, placement_engine | Nice-to-have |
| 2.2 | Repeated WKT/GeoJSON | Redundant conversion | Single canonical form per layer | plan_job_service, utils | Nice-to-have |
| 3.1–3.6 | Planning rules | Compliance and realism | Road access, orientation, parking req, fire, COP touch | Backend engines + plan_job_service | Important / Nice-to-have |
| 4.1 | Redundant Legend/Layers | Confusion | One source of truth; Legend mirrors or remove | LayerControl, Legend | Nice-to-have |
| 4.2 | Layer hierarchy unclear | Usability | Grouping and tooltips | LayerControl | Nice-to-have |
| 4.5 | No scale bar / zoom-to-selection | Readability and navigation | Scale bar component; zoom to bbox | SvgCanvas, PlannerCanvas | Nice-to-have |
| 4.6–4.8 | Tower label; tooltip; Floors | Clarity and correctness | “Tower 1 of N”; “Building height (m)” or floor count | PlanningMetricsPanel, PlannerCanvas | Critical (4.8) |
| 5.1–5.5 | FSI, BUA, COP req, floors, efficiency | Metrics correctness | Backend formulas and new fields | plan_job_service, site_metrics; frontend panel | Critical |
| 6.1–6.5 | Perf: large plots, many towers, SVG, worker | Scalability | Simplify, STRtree, virtualize, worker | Backend + frontend | Nice-to-have |
| 7.x | Scenario compare, undo, duplicate | Workflow | Compare view, history, duplicate action | Frontend store + UI | Nice-to-have |
| 8.x | Floor layout API and UI | Stage 2 readiness | API + floor layers + unit click | Backend API, FloorPlanningView, layers | Important |

---

*End of audit.*
