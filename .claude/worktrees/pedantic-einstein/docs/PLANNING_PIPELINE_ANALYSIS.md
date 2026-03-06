# Planning Pipeline Analysis (Steps 1 & 2)

## STEP 1 — Current Geometry Pipeline

### Entry points

- **API / jobs**: `services.plan_job_service._build_envelope_plan_result()` (used by PlanJob worker).
- **Full floor-plan pipeline**: `architecture.services.development_pipeline.generate_optimal_development_floor_plans()` (optimiser → envelope → placement → floor layout).

Both use the same envelope and placement engines; the job path is a lighter subset (envelope + placement only, no floor aggregation).

---

### 1. Plot boundary processing

- **Source**: `Plot.geom` (GeoDjango `PolygonField`, SRID=0). Coordinates are in **DXF feet** (ingestion assumes 1 DXF unit = 1 ft).
- **Ingestion** (`tp_ingestion`):
  - DXF → polygons + text labels (FP numbers, road widths).
  - Excel/CSV → `{fp_number: area}`.
  - Geometry matcher associates labels to polygons; area validator checks geometry area vs Excel; valid records are saved/updated on `Plot` (including `geom`, `road_width_m`, `plot_area_sqm`).
- **Pipeline use**: Plot boundary is passed as **WKT** (`plot.geom.wkt`) into the envelope engine. It is parsed to a Shapely polygon in DXF feet. No coordinate transform is applied.

---

### 2. Setbacks (margins)

- **Classification** (`envelope_engine.geometry.edge_classifier`):
  - Input: plot polygon + `road_facing_edges` (indices from `detect_road_edges_with_meta`).
  - Each exterior edge is classified as **ROAD**, **REAR**, or **SIDE**. REAR = non-road edge most parallel to the first road edge.
- **Resolution** (`envelope_engine.geometry.margin_resolver`):
  - **ROAD**: Table 6.24 → `margin = max(road_width_based_lookup(road_width), H/5, min_road_side_margin)` (e.g. 1.5 m floor).
  - **SIDE / REAR**: Table 6.26 → height-band lookup (e.g. 3 / 4 / 6 / 8 m by height).
  - Margins are stored in metres and DXF feet on each `EdgeSpec`.
- **Application** (`envelope_engine.geometry.envelope_builder`):
  - Per-edge **half-plane intersection**: for each edge, offset inward by `required_margin_dxf`, build a “keep” half-plane, intersect with running polygon. Result = **margin polygon** (setback polygon). No uniform buffer; each edge gets its own margin.

---

### 3. Buildable envelope

- **Steps** (`envelope_engine.services.envelope_service.compute_envelope`):
  1. Parse plot WKT → Shapely polygon.
  2. Classify edges → `edge_specs`.
  3. Resolve margins → `edge_specs` updated.
  4. **Build envelope** = `build_envelope(plot_polygon, edge_specs)` → **margin polygon** (same as “setback polygon” above; this is the polygon inside all setbacks).
  5. **Ground coverage**: `enforce_ground_coverage(margin_polygon, plot_polygon)` → clip to GDCR max GC % (e.g. 40%) if exceeded → **gc_polygon**.
  6. **COP carve**: `carve_common_plot(plot_polygon, gc_polygon, edge_specs, cop_strategy)` → common plot polygon.
  7. **Final envelope**: gc_polygon minus (COP + COP margin band) → **envelope_polygon** (buildable area).
- So: **buildable envelope** = inside all setbacks, under GC cap, and with COP + COP margin removed. It does **not** yet subtract any internal roads (none exist today).

---

### 4. COP (Common Open Plot) — current behaviour

- **Config** (GDCR.yaml): `required_fraction: 0.10`, `minimum_total_area_sqm: 200`, `applies_if_plot_area_above_sqm: 2000`, `geometry_constraints.minimum_width_m / minimum_depth_m: 10` (not 7.5).
- **Strategies**:
  - **edge**: Rear-strip carve. Required area = `max(10% × plot_area, 200 sqm)` in sq.ft. Find REAR edge; bisect depth so strip from rear boundary has area ≥ required; strip = plot ∩ half-plane (rear side). Result can be irregular (strip along rear).
  - **center**: Axis-aligned rectangle centred on plot centroid; width/depth ≥ min from config; area ≥ required; scaled by bisection if needed; clipped to plot.
- **Placement**: COP is carved from the **plot** (and conceptually from the margin zone); the **envelope** is then reduced by (COP + height-based COP margin band) so buildable area does not overlap COP.
- **Minimum dimension**: CENTER uses `minimum_width_m` / `minimum_depth_m` from GDCR (10 m in current YAML). EDGE strategy does **not** enforce a minimum width/depth (e.g. 7.5 m); it only enforces area. So a long, thin rear strip could violate “min dimension ≥ 7.5 m”.

---

### 5. Tower placement

- **Input**: Envelope polygon (WKT, DXF feet), building height, n_towers, min width/depth (metres).
- **Flow** (`placement_engine.services.placement_service.compute_placement`):
  - Parse envelope WKT → Shapely polygon.
  - Orientation from envelope MBR (`orientation_finder`).
  - **Packing** (`placement_engine.geometry.packer.pack_towers`): two strategies — **ROW_WISE** (dual orientation per step) and **COL_WISE** (force perpendicular). For each: repeatedly find best inscribed rectangle in remaining polygon (`find_best_in_components`), add **H/3 exclusion zone** around placed footprint (`spacing_enforcer.compute_exclusion_zone`), subtract from envelope, repeat. Winner = more towers placed, then larger total area, then ROW_WISE.
  - **Spacing**: GDCR Table 6.25 → `required_spacing_m = max(H/3, minimum_spacing_m)` (e.g. 3 m). Post-placement audit measures pairwise gaps.
  - **Core fit**: Per tower, `validate_core_fit(width_m, depth_m, height_m)` for lift/core compliance.
- **Output**: List of `FootprintCandidate` (Shapely polygons), spacing audit, core validations. No internal roads or circulation corridors are reserved; placement is purely “fit rectangles in envelope with H/3 spacing”.

---

### Current pipeline (high-level) — diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Plot (tp_ingestion)                                                        │
│  Plot.geom (WKT), road_width_m, plot_area_sqm                               │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Road edge detection (architecture.spatial.road_edge_detector)              │
│  → road_facing_edges                                                        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Envelope engine (envelope_engine)                                            │
│  1. EdgeClassifier → ROAD/SIDE/REAR                                          │
│  2. MarginResolver → per-edge margins (GDCR Tables 6.24, 6.26)               │
│  3. EnvelopeBuilder → margin_polygon (setbacks)                              │
│  4. CoverageEnforcer → gc_polygon (GC limit)                                 │
│  5. CommonPlotCarver → common_plot_polygon (COP)                            │
│  6. envelope = gc_polygon − (COP + COP margin band)                         │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Placement engine (placement_engine)                                          │
│  pack_towers(envelope, n_towers, height, min_w, min_d)                      │
│  → footprints, spacing audit (no internal roads)                            │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Optional: development_pipeline → floor skeleton → floor layout → building   │
│  (PlanJob path stops at envelope + placement + GeoJSON)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## STEP 2 — COP vs GDCR 2017

### Rule: COP_area ≥ max(10% × plot_area, 200 sqm)

- **Current**: Enforced in `common_plot_carver` (both EDGE and CENTER). `required_area = max(COMMON_PLOT_FRACTION * plot_area_sqft, min_total_area_sqft)` with `min_total_area_sqm: 200`. **Compliant.**

### Rule: Minimum dimension of COP ≥ 7.5 m

- **GDCR.yaml** has `geometry_constraints.minimum_width_m: 10`, `minimum_depth_m: 10` (i.e. 10 m, not 7.5 m). So config already uses a **stricter** minimum dimension where applied.
- **CENTER strategy**: Uses `minimum_width_m` and `minimum_depth_m` from config (10 m). So CENTER satisfies “min dimension ≥ 7.5 m” (and actually 10 m).
- **EDGE strategy**: Does **not** enforce any minimum width or depth. The rear strip can be arbitrarily narrow (e.g. long thin strip). So **EDGE does not guarantee “minimum dimension ≥ 7.5 m”**.

### Validations currently missing (to list clearly)

1. **Minimum dimension (e.g. 7.5 m) for EDGE strategy**  
   After carving the rear strip, check that the resulting polygon has both width and depth ≥ 7.5 m (e.g. minimum rotated rectangle side or equivalent). If not, fall back to CENTER or another strategy, or fail with a clear status.

2. **Explicit “COP inside plot” check**  
   Current logic assumes intersection with plot keeps COP inside; an explicit `cop.within(plot)` or `cop.intersection(plot).area == cop.area` check would make validity auditable.

3. **COP does not overlap building envelope**  
   Currently enforced indirectly: envelope is defined as gc_polygon minus (COP + margin). So buildable envelope does not overlap COP. No explicit boolean “COP ∩ envelope is empty” in the carver.

4. **Post-carve geometry validity**  
   No explicit Shapely `is_valid` or “no self-intersection” check on the returned COP polygon before returning (repair with `buffer(0)` if invalid).

5. **Configurable 7.5 m in YAML**  
   If GDCR 2017 is interpreted as “min dimension 7.5 m”, that value should be in GDCR (e.g. `minimum_dimension_m: 7.5`) and used by both EDGE and CENTER so one source of truth.

---

## Updated pipeline (after implementation)

Correct order:

```
plot ingestion (tp_ingestion)
    → setbacks (edge classifier + margin resolver)
    → margin polygon
    → ground coverage enforce → gc_polygon
    → COP generation (carve_common_plot / generate_common_plot)
    → envelope = gc_polygon − (COP + COP margin)
    → internal road network (generate_internal_road_network)
    → final envelope = envelope − road corridors
    → tower placement (on final envelope)
    → floor generation (optional)
```

---

## Example output GeoJSON structure

```json
{
  "planId": "uuid",
  "plotId": "TP14-152",
  "metrics": { "plotAreaSqm", "envelopeAreaSqft", "groundCoveragePct", "copAreaSqft", "copStatus", "buildingHeightM", "roadWidthM", "nTowersRequested", "nTowersPlaced", "spacingRequiredM" },
  "geometry": {
    "plotBoundary": { "type": "Polygon", "coordinates": [ ... ] },
    "envelope": { "type": "Polygon", "coordinates": [ ... ] },
    "cop": { "type": "Polygon", "coordinates": [ ... ] },
    "copMargin": { "type": "Polygon", "coordinates": [ ... ] },
    "internalRoads": [ { "type": "LineString", "coordinates": [ ... ] }, ... ],
    "towerFootprints": [ { "type": "Polygon", "coordinates": [ ... ] }, ... ],
    "spacingLines": [ { "type": "LineString", "coordinates": [ ... ] }, ... ]
  },
  "debug": {
    "buildableEnvelope": { "type": "Polygon", "coordinates": [ ... ] },
    "roadNetwork": [ { "type": "LineString", "coordinates": [ ... ] }, ... ]
  }
}
```

---

## Summary for implementation

- **Pipeline order**: Today order is plot → setbacks → GC → COP → envelope (gc − COP) → placement. Desired: plot → setbacks → envelope (GC) → **COP** → **internal road network** → **envelope minus COP and roads** → placement. So COP and roads must be generated before final envelope and placement; envelope must subtract both COP (and margin) and road corridors.
- **COP**: Add `generate_common_plot(plot_polygon, envelope_polygon, required_area)` that returns a valid COP polygon with area ≥ required, min dimension ≥ 7.5 m (configurable), no overlap with envelope/setbacks, simple (prefer rectangle); prefer road-facing edge when possible.
- **Internal roads**: New module (e.g. `architecture/engines/road_network_engine.py`) to produce entry + spine + COP connection + circulation corridor; output LineStrings; min width 6 m (configurable).
- **Envelope**: After COP and roads, subtract COP (+ margin) and road corridors from gc_polygon to get final buildable envelope.
- **Placement**: Add parameters (min_tower_spacing, max_tower_depth, max_tower_width); reserve circulation; return tower polygons.
- **Output**: Structured GeoJSON (plotBoundary, envelope, cop, internalRoads, towerFootprints, spacingLines) plus validation and optional debug layers.

---

## Implementation summary (completed)

1. **STEP 1–2** — Documented in this file: current pipeline analysis, COP vs GDCR validation, missing validations listed.
2. **STEP 3** — `envelope_engine.geometry.common_plot_generator.generate_common_plot(plot_polygon, envelope_polygon, required_area_sqft, ...)` added. Enforces area ≥ required, min dimension ≥ 7.5 m (from GDCR `minimum_dimension_m`), no overlap with envelope, rectangular preference. GDCR.yaml extended with `minimum_dimension_m: 7.5`.
3. **STEP 4** — `architecture.engines.road_network_engine` added: `generate_internal_road_network()` (entry point, spine road, connection to COP), `road_network_corridor_polygons()` for corridor buffers. Minimum width 6 m (configurable).
4. **STEP 5** — Plan job pipeline order: envelope → internal road network → subtract road corridors → placement on final envelope.
5. **STEP 6** — Final envelope = envelope minus road corridor union (in `plan_job_service`).
6. **STEP 7** — Placement engine already has min_width_m, min_depth_m and H/3 spacing; optional max_tower_* can be added later to packer.
7. **STEP 8** — API result includes `geometry.internalRoads` (LineStrings), `geometry.plotBoundary|envelope|cop|copMargin|towerFootprints|spacingLines`; `debug.buildableEnvelope`, `debug.roadNetwork`.
8. **STEP 9** — `utils.geometry_validation.validate_polygon`, `validate_geojson_geometry` added for optional pre-return checks.
9. **STEP 10** — Debug layers in result: `debug.buildableEnvelope`, `debug.roadNetwork`.
