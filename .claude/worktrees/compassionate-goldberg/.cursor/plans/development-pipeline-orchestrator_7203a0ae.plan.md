---
name: development-pipeline-orchestrator
overview: Design a deterministic orchestration service that takes the optimal multi-tower development configuration for a plot and generates one representative floor plan per tower by coordinating existing regulatory, geometry, layout, and presentation engines without modifying them.
todos: []
isProject: false
---

## Development Pipeline Orchestrator Design

### 1. Module structure and responsibilities

- **Module**: `[backend/architecture/services/development_pipeline.py](backend/architecture/services/development_pipeline.py)`
- **Primary responsibility**: Orchestrate existing engines to convert the *already-optimised* development configuration for a plot into concrete, deterministic floor-plan outputs (one representative floor per tower).
- **Non-responsibilities**:
  - No regulatory optimisation (no search, no constraint solving).
  - No modification of envelope/placement/skeleton/layout/rules engines.
  - No re-encoding of GDCR constants or rules.
  - No economic scoring or multi-variant exploration (reserved for future layers).

The module will:

- Call `solve_optimal_development_configuration` to get the chosen `(n_towers, floors, height_m, FSI, etc.)`.
- Treat **floors + storey_height_m as canonical** and derive `height_m = floors * storey_height_m` for all downstream engines.
- Re-run envelope and placement once with the final derived height and tower count.
- For each tower, generate a skeleton and floor layout for a single representative floor.
- Assemble a normalized result object that includes regulatory metrics, minimal geometry summaries, and per-tower floor layouts (DTOs), plus structured failure information.

### 2. Public API and dataclasses

#### 2.1 Public entrypoint

```python
generate_optimal_development_floor_plans(
    plot: Plot,
    storey_height_m: float = 3.0,
    min_width_m: float = 5.0,
    min_depth_m: float = 3.5,
    *,
    include_building_layout: bool = False,
    strict: bool = True,
) -> DevelopmentFloorPlanResult
```

- **Parameters**:
  - `plot: Plot` (required): `tp_ingestion.models.Plot` with geometry and `road_width_m`.
  - `storey_height_m: float` (optional, default 3.0): Must be consistent with upstream solvers and building aggregation.
  - `min_width_m: float` (optional, default 5.0): Passed straight to placement engine.
  - `min_depth_m: float` (optional, default 3.5): Passed straight to placement engine.
  - `include_building_layout: bool` (optional, default `False`): If `True`, orchestrator may call `build_building_layout` to assemble a full building contract from per-floor layouts (optional hook).
  - `strict: bool` (optional, default `True`): Controls failure behaviour:
    - `True` → **atomic**: all towers must succeed, or the entire result is marked as failure.
    - `False` → reserved for a future “partial diagnostics” mode (not required initially).
- **Return**:
  - `DevelopmentFloorPlanResult`: A normalized DTO capturing both the selected development configuration and the per-tower floor layouts, plus failure metadata.
- **Failure behaviour**:
  - Domain failures (invalid envelope, placement, skeleton, layout) are reported via structured status codes and failure details, not by throwing exceptions.
  - Exceptions are reserved for programming/configuration errors (e.g. invalid arguments) and occur before engine calls.

#### 2.2 Result dataclasses

##### 2.2.1 DTO vs raw engine objects

- **Tradeoffs**:
  - Raw engine objects (`FloorLayoutContract`, envelope/placement result classes):
    - Pros: full power to in-process Python consumers.
    - Cons: tight coupling; any internal engine change can break external callers; not easily serialisable.
  - DTO layer:
    - Pros: stable boundary; easy to serialise and log; engine internals can evolve safely.
    - Cons: requires mapping; must choose which fields to expose.
- **Decision**:
  - Expose a **DTO-first public contract** with geometry as WKT and scalar metrics.
  - Optionally keep raw engine contracts as internal (non-serialised) fields for in-process use, but these are not part of the formal API.

##### 2.2.2 Proposed DTOs

```python
@dataclass
class TowerFloorLayoutDTO:
    tower_index: int
    floor_id: str
    total_units: int
    efficiency_ratio_floor: float
    unit_area_sum_sqm: float
    footprint_polygon_wkt: str
    core_polygon_wkt: Optional[str]
    corridor_polygon_wkt: Optional[str]
    # Internal use only (not for external APIs)
    raw_contract: Optional[FloorLayoutContract] = None


@dataclass
class PlacementSummaryDTO:
    n_towers: int
    per_tower_footprint_sqft: List[float]
    spacing_required_m: float
    spacing_provided_m: Optional[float]


@dataclass
class DevelopmentFloorPlanResult:
    status: str  # "OK" or one of the failure codes
    failure_reason: Optional[str]
    failure_details: Optional[dict]

    # Chosen configuration from development_optimizer
    n_towers: int
    floors: int
    height_m: float
    achieved_fsi: float
    fsi_utilization_pct: float
    total_bua_sqft: float
    gc_utilization_pct: float
    controlling_constraint: str

    # Geometry and layout artefacts
    envelope_wkt: Optional[str]
    placement_summary: Optional[PlacementSummaryDTO]
    tower_floor_layouts: List[TowerFloorLayoutDTO]

    # Optional: building-level contract when include_building_layout=True
    building_layout: Optional[BuildingLayoutContract]
```

### 3. Deterministic orchestration flow

#### Step 1 — Call development optimizer

- Call `solve_optimal_development_configuration(plot, storey_height_m, min_width_m, min_depth_m)`.
- If the solver returns:
  - `controlling_constraint == "INFEASIBLE"` **or**
  - `n_towers == 0` **or**
  - `floors == 0`
  - Then return `DevelopmentFloorPlanResult` with:
    - `status = "INFEASIBLE"`
    - `failure_reason = "INFEASIBLE"`
    - `tower_floor_layouts = []`, `envelope_wkt = None`, `placement_summary = None`.
- Otherwise, extract configuration:
  - `n_towers`, `floors`, `solver_height_m`, `achieved_fsi`, `fsi_utilization_pct`, `total_bua_sqft`, `gc_utilization_pct`, `controlling_constraint`.

**Canonical height decision**:

- Derive `height_m = floors * storey_height_m` and **ignore** `solver_height_m` as an input for envelope/placement/layout.
- Optionally assert `abs(solver_height_m - height_m) < eps` for debug; a hard violation indicates a programming error, not a domain failure.

#### Step 2 — Recompute envelope at final height

- Use:
  - `plot_wkt = plot.geom.wkt`
  - `road_width = plot.road_width_m`
  - `road_edges, _ = detect_road_edges_with_meta(plot.geom, None)`
- Call:

```python
env = compute_envelope(
    plot_wkt=plot_wkt,
    building_height=height_m,
    road_width=road_width,
    road_facing_edges=road_edges,
    enforce_gc=True,
)
```

- If `env.status != "VALID"` or `env.envelope_polygon is None`:
  - Return `status = "ENVELOPE_INVALID"`, `failure_reason = "ENVELOPE_INVALID"`, and include `{"height_m": height_m}` in `failure_details`.

**Invariant**:

- Envelope is recomputed once for the **derived** `height_m` with the **same calling convention** as in the optimizers (same edge detection, same `enforce_gc`).

#### Step 3 — Recompute placement for chosen n_towers

- With:

```python
placement = compute_placement(
    envelope_wkt=env.envelope_polygon.wkt,
    building_height_m=height_m,
    n_towers=n_towers,
    min_width_m=min_width_m,
    min_depth_m=min_depth_m,
)
```

- If `placement.status != "VALID"` or `not placement.footprints`:
  - Return `status = "PLACEMENT_INVALID"`, `failure_reason = "PLACEMENT_INVALID"`, with diagnostics.

**Deterministic tower ordering**:

- Do **not** rely on engine internals for footprint ordering.
- Derive a deterministic key per tower (e.g. centroid `(x, y)` from `footprint.polygon`), create `(footprint, core_validation)` pairs, and sort by `(centroid_x, centroid_y)`.
- Use this sorted order to assign `tower_index` and to build `tower_floor_layouts`.

#### Step 4 — Per-tower skeleton and floor layout

For each tower in sorted order:

1. Extract `footprint_i`, `core_validation_i`.
2. Call `generate_floor_skeleton(footprint_i, core_validation_i)`.
  - If this raises or returns a skeleton with:
    - `pattern_used == NO_SKELETON_PATTERN`, or
    - `not is_geometry_valid`, or
    - `not passes_min_unit_guard`, or
    - `not is_architecturally_viable`
    - Then return `status = "SKELETON_INVALID"`, `failure_reason = "SKELETON_INVALID"`, with `{"tower_index": i}`.
3. Call `build_floor_layout(skeleton, floor_id=f"L0_T{i}", module_width_m=None)`.
  - If this raises or yields `total_units == 0` or `efficiency_ratio_floor <= 0`:
    - Return `status = "LAYOUT_INVALID"`, `failure_reason = "LAYOUT_INVALID"`, with `{"tower_index": i}`.
4. Build `TowerFloorLayoutDTO` from the resulting `FloorLayoutContract`.

**Atomic failure policy**:

- Under `strict=True`, **all towers must succeed**. Any tower failure returns a failure result; no partial set of towers is considered acceptable design output.

#### Step 5 — Optional building aggregation

- If `include_building_layout` is `True`, call `build_building_layout` with:
  - The per-tower skeleton or floor-layout contracts.
  - `floors` (number of storeys).
- Attach the resulting `BuildingLayoutContract` to `DevelopmentFloorPlanResult.building_layout`.

#### Step 6 — Assemble final result

- On full success (all towers succeeded):
  - `status = "OK"`, `failure_reason = None`, `failure_details = None`.
  - Copy configuration metrics from development optimizer and the derived `height_m`.
  - Set:
    - `envelope_wkt = env.envelope_polygon.wkt`
    - `placement_summary = PlacementSummaryDTO(...)` from placement
    - `tower_floor_layouts = [...]`

### 4. Explicit invariants

1. **Height–floors coupling**:
  - `height_m` used for all engines is **derived** as `floors * storey_height_m`.
  - Solver-provided `height_m` is treated as a check, not as canonical.
2. **Recomputed envelope and placement**:
  - Envelope and placement are recomputed exactly **once** for the final configuration and not reused from internal solver state.
3. **No footprint modification**:
  - `placement.footprints` are never translated, resized, or reshaped by the orchestrator.
4. **No engine mutation**:
  - `compute_envelope`, `compute_placement`, `generate_floor_skeleton`, `build_floor_layout`, and `build_building_layout` are called as pure services.
5. **No regulatory logic duplication**:
  - All GDCR semantics (FSI, GC, spacing, height vs road) remain in accessors, regulatory metrics, solvers, and rules engine.
6. **Deterministic tower ordering**:
  - Explicitly sort towers by a stable geometric key to define `tower_index` and DTO order.
7. **Single representative floor per tower**:
  - Only one floor layout per tower is generated; upper floors are assumed to replicate this layout consistent with `floors` and `height_m`.

### 5. Error handling design

- **Status / failure codes**:
  - High-level: all non-OK outcomes are **domain failures** rather than programmer errors.
  - Leaf codes:
    - `"OK"`
    - `"INFEASIBLE"`
    - `"ENVELOPE_INVALID"`
    - `"PLACEMENT_INVALID"`
    - `"SKELETON_INVALID"`
    - `"LAYOUT_INVALID"`
- **Atomic behaviour (strict=True)**:
  - Any failure after STEP 1 returns a result with the corresponding failure status and **no usable tower layouts**.
  - Partial successes are only captured in `failure_details` for diagnostics, not as design output.
- **Non-strict behaviour (future)**:
  - `strict=False` could allow returning partial tower layouts for debug/UIs, clearly marked as partial and invalid for regulatory use.

### 6. Extensibility hooks

1. **Economic scoring layer**:
  - A future `score_development(result: DevelopmentFloorPlanResult)` function can compute yield, revenue, or cost metrics without changing the orchestrator.
2. **DXF export integration**:
  - A separate service (or command) will consume `DevelopmentFloorPlanResult` and call the detailed layout + `presentation_engine` / `dxf_adapter` to generate DXFs.
3. **AI advisory integration**:
  - `ai_layer` can consume `DevelopmentFloorPlanResult` as a canonical baseline and propose variations or explainability.
4. **Multi-floor variation support**:
  - Later, support for distinct layouts for podium/mid/top floors can extend the API without changing the core orchestration pattern.
5. **Observability / diagnostics**:
  - `failure_details` and optional structured `diagnostics` objects can be extended to capture timings, intermediate geometry stats, and rules outcomes.

### 7. Performance considerations

- Orchestrator runs once for the chosen configuration:
  - 1 × `compute_envelope`
  - 1 × `compute_placement`
  - `n_towers` × (`generate_floor_skeleton` + `build_floor_layout`)
- No internal search loops; all optimisation remains in the dedicated solver modules.
- All loops and ordering are deterministic; no randomness is used.

