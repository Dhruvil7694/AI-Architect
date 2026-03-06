---
name: area-accounting-foundation
overview: Stabilise current skeleton/layout behaviour, then introduce a deterministic, geometry-derived floor area accounting layer (including RERA-ready metrics) anchored at the floor-layout engine level.
todos:
  - id: truth-table-doc-and-test
    content: Create the 10m×10m geometry truth-table document and its corresponding regression test before any Phase 1 area-accounting code.
    status: completed
  - id: phase0-tests
    content: Add regression tests to freeze current skeleton selection, floor aggregation metrics, and repetition invariants.
    status: completed
  - id: dto-definition
    content: Introduce the `FloorAreaBreakdown` dataclass and core area-accounting helpers in a new area_accounting module.
    status: completed
  - id: base-area-metrics
    content: Implement basic footprint/core/corridor/unit area computations from `FloorLayoutContract` geometry.
    status: completed
  - id: wall-and-rera
    content: Integrate Phase D wall engine and detailing config to compute wall areas, shaft/common areas, and RERA carpet per unit.
    status: completed
  - id: helper-wrapper
    content: Expose a helper that builds `FloorLayoutContract` and an attached `FloorAreaBreakdown` without changing existing contracts.
    status: completed
  - id: area-accounting-tests
    content: Add focused tests for base-area, wall-area, and RERA accounting, including at least one full-layout snapshot test.
    status: completed
isProject: false
---

## Phase 0 – Freeze & Stabilise Current Engine

- **Goal**: Lock in existing skeleton scoring, efficiency outputs, and template behaviour so we can safely evolve geometry and area models.
- **0.1 Snapshot current behaviour via tests**
  - **Skeleton selection + scoring**
    - Add unit tests in a new test module (e.g. `[backend/floor_skeleton/tests/test_skeleton_selection.py](backend/floor_skeleton/tests/test_skeleton_selection.py)`) that:
      - Construct a few deterministic `FootprintCandidate`/`CoreValidationResult` scenarios using `CoreDimensions` so that `generate_floor_skeleton` returns a viable `FloorSkeleton`.
      - Assert that, for fixed inputs, the selected `pattern_used`, `placement_label`, `efficiency_ratio`, and `area_summary["unit_area_sqm"]` match frozen expected values.
      - Assert that `select_best` scores candidates in the current order: primarily by `unit_area_sqm`, then `efficiency_ratio`, then placement label (via `LABEL_ORDER`).
  - **Floor aggregation / efficiency outputs**
    - Add tests under `[backend/residential_layout/tests/test_floor_aggregation.py](backend/residential_layout/tests/test_floor_aggregation.py)` that:
      - Build a simple synthetic `FloorSkeleton` (axis-aligned rectangles for footprint/core/corridor + one/two `UnitZone`s) and pass it into `build_floor_layout`.
      - Assert:
        - `total_units` equals both `sum(b.n_units)` and `len(all_units)` (mirrors `_validate_floor`).
        - `unit_area_sum` equals `sum(b.n_units * module_width_m * zone_depth_m)` within tolerance.
        - `efficiency_ratio_floor` equals `unit_area_sum / footprint_polygon.area` within tolerance.
        - `corridor_area` and `core_polygon.area` match the underlying polygons.
  - **Template behaviour / repetition invariants**
    - Add tests in `[backend/residential_layout/tests/test_repetition_invariants.py](backend/residential_layout/tests/test_repetition_invariants.py)` that:
      - Exercise `_compute_n_and_residual` for band lengths around the `MIN_RESIDUAL_M` threshold and ensure `N`/`residual_width_m` stay frozen.
      - Build a minimal `UnitZone` + `ComposerFrame` and call `repeat_band` with fixed `module_width_m`, asserting:
        - `n_units`, `residual_width_m`, and `band_length_m` are as expected.
        - Slice zones tightly tile the band without overlaps (re-asserting `_validate_band`).
  - **Guard against accidental changes**
    - Where useful, use snapshot-like asserts (exact floats rounded to e.g. 3–4 decimals) so refactors to geometry logic must explicitly update tests.
- **0.2 Full pipeline integration snapshot**
  - Add an integration-level test (e.g. `[backend/architecture/tests/test_full_pipeline_snapshot.py](backend/architecture/tests/test_full_pipeline_snapshot.py)`) that:
    - Runs the full current pipeline for a simple, deterministic plot: `placement → core_fit → generate_floor_skeleton → build_floor_layout`.
    - Serialises, for each resulting tower/floor:
      - `pattern_used`
      - `placement_label`
      - `total_units`
      - `efficiency_ratio_floor`
      - `unit_area_sum`
  - Assert these values (rounded to a fixed precision) so any change in skeleton scoring, repetition invariants, or efficiency math forces an intentional test update.
  - Keep this test seedless and deterministic (no randomness), and treat it as the main tripwire before Phase 1 accounting changes.

---

## Phase 1 – Area Accounting Layer (Floor-Level, Geometry-Derived)

- **Goal**: Introduce a formal, deterministic floor area accounting model, derived only from geometry and explicit wall thickness, anchored alongside `FloorLayoutContract`. RERA carpet computation will leverage the existing Phase D `detailed_layout` wall engine and config.

### 1.0 Geometry conventions and truth table

- **Freeze geometric axioms up-front**
  - Document, in code and in a short design note (e.g. `docs/area_accounting_truth_table.md`), the geometric conventions that all Phase 1 accounting relies on:
    - `footprint_polygon` represents the **gross built-up boundary** at the outer face of external walls.
    - `core_polygon` / `corridor_polygon` are drawn to the **inner faces of surrounding walls** (i.e. usable common area, excluding wall thickness), or, if that is not yet true, clearly state the current convention and adapt the partition formula accordingly.
    - `unit_envelope_area_sqm` (and the underlying unit band geometry) represents the **usable unit slab area excluding wall thickness**, i.e. room polygons do not already “bake in” half wall thickness at boundaries.
    - `RoomInstance.polygon` areas are treated as *internal* room areas:
      - Add a focused geometry test for a minimal configuration (single room against external boundary) to confirm whether room polygons extend only to the wall **interior face** or to the wall **centreline**.
      - If they currently extend to the centreline, RERA wall allocation must avoid double-counting implicit half-thickness already baked into room areas; this compensation rule must be documented alongside the truth table.
    - `DetailedWall.polygon` is generated via a **symmetric buffer** around the wall centreline (`buffer(thickness / 2)`), so that:
      - `area ≈ edge_length * thickness` for a straight segment.
      - Splitting a shared wall 50/50 corresponds to assigning half of `polygon.area` to each adjacent unit.
      - For external walls this implies that approximately half the buffered polygon lies inside the `footprint_polygon` and half outside; the accounting layer must decide whether to:
        - Treat wall area as a separate layer that can extend beyond `footprint_polygon` but is still included in gross built-up via invariants, or
        - Explicitly trim wall polygons to the interior of the footprint before using them in partition checks.
  - Add a small, hand-worked “truth table” example (e.g. 10 m × 10 m footprint with 0.2 m walls, simple core and one unit band) that states expected values for:
    - **Explicit inputs** (not just schematic): exact footprint corner coordinates, wall thickness value, core rectangle coordinates/dimensions, corridor strip width and location, and one unit zone’s band rectangle.
    - **Explicit numeric outputs**: concrete numbers (in sq.m) for `gross_built_up_sqm`, `unit_envelope_area_sqm`, `core_area_sqm`, `corridor_area_sqm`, `internal_wall_area_sqm`, `external_wall_area_sqm`, `shaft_area_sqm`, `rera_carpet_area_total_sqm`, and `common_area_total_sqm` written out in the document.
  - In tests, reproduce this configuration and assert that the engine’s computed breakdown matches those manual truth-table numbers within a tight tolerance; any future change to geometry semantics must therefore update the truth-table doc and its test together.

### 1.1 Define `FloorAreaBreakdown` DTO & module placement

- **New DTO**
  - Create a new dataclass in a dedicated module, e.g. `[backend/area_accounting/floor_area.py](backend/area_accounting/floor_area.py)`:
    - `FloorAreaBreakdown` with the fields you specified:
      - `gross_built_up_sqm: float`
      - `core_area_sqm: float`
      - `corridor_area_sqm: float`
      - `shaft_area_sqm: float`
      - `common_area_total_sqm: float`
      - `unit_envelope_area_sqm: float`
      - `internal_wall_area_sqm: float`
      - `external_wall_area_sqm: float`
      - `rera_carpet_area_total_sqm: float`
      - `carpet_per_unit: list[float]`
      - `common_area_percentage: float`  (derived: `common_area_total_sqm / gross_built_up_sqm`, 0 when gross is 0)
      - `carpet_to_bua_ratio: float`     (derived: `rera_carpet_area_total_sqm / gross_built_up_sqm`)
      - `efficiency_ratio_recomputed: float` (derived: `unit_envelope_area_sqm / gross_built_up_sqm`)
  - Keep this module engine-agnostic but depend on existing contracts:
    - `FloorLayoutContract` (from `[backend/residential_layout/floor_aggregation.py](backend/residential_layout/floor_aggregation.py)`).
    - `UnitLayoutContract`/`RoomInstance` (from `[backend/residential_layout/models.py](backend/residential_layout/models.py)`).
    - Wall/wall-config types from Phase D (`DetailedWall`, `DetailingConfig`, `build_walls_for_floor`).

### 1.2 Base skeleton/floor area metrics (no walls yet)

- **Leverage existing `area_summary` and floor polygons**
  - Implement a first-level helper, e.g. `compute_floor_base_areas(floor: FloorLayoutContract) -> dict` in `floor_area.py` that:
    - Uses `floor.footprint_polygon.area` as a deterministic base for `gross_built_up_sqm`.
    - Uses `floor.core_polygon.area` for `core_area_sqm`.
    - Uses `floor.corridor_polygon.area` (or `0.0` if `None`) for `corridor_area_sqm`.
    - Uses `floor.unit_area_sum` (which comes from band repetition geometry) as `unit_envelope_area_sqm`.
  - For now, set `shaft_area_sqm` to `0.0` at this level; it will be overridden by the Phase D–aware layer (Section 1.3).
  - Define a thin wrapper `compute_floor_area_breakdown_basic(floor: FloorLayoutContract) -> FloorAreaBreakdown` that fills:
    - The above geometric values.
    - Sets wall-related and RERA fields to `0.0`/`[]`, with an internal docstring clarifying that these are completed only when the detailed pass is executed.

### 1.3 Integrate Phase D detailing for wall and shaft modelling

- **Wall construction and classification**
  - In `floor_area.py`, add a function like `compute_wall_areas_for_floor(floor: FloorLayoutContract, units: list[UnitLayoutContract], config: DetailingConfig) -> dict` that:
    - Calls `build_walls_for_floor(floor, units, config)` from `[backend/detailed_layout/wall_engine.py](backend/detailed_layout/wall_engine.py)`.
    - Separates **wall construction** from **area accounting** so heavy geometry work is done once:
      - First, build and cache the wall structures (e.g. `DetailedWall` list and room/unit lookup maps).
      - Then, pass these precomputed structures into:
        - `compute_wall_areas_for_floor_from_walls(...)` for area sums, and
        - `compute_rera_carpet_for_units(...)` for per-unit allocation.
    - When computing areas from the wall list:
      - Sum `polygon.area` for walls with `wall_type == "INTERNAL"` → `internal_wall_area_sqm`.
      - Sum `polygon.area` for walls with `wall_type == "EXTERNAL"` → `external_wall_area_sqm`.
      - Sum `polygon.area` for walls with `wall_type == "SHAFT"` → contributes to `shaft_area_sqm` and `common_area_total_sqm`.
    - This ensures we explicitly model wall thickness based on the shared-edge logic you already captured (room-room, room-footprint, core/corridor), while keeping the computationally expensive edge-normalisation + buffering reusable.
- **Shafts and common area accounting**
  - Use the existing classification semantics to define:
    - `shaft_area_sqm` as the area of `SHAFT`-type walls plus any lift/stair hatch polygons where available (e.g. by optionally accepting `DetailedCore`/`DetailedStair` lists later).
    - `common_area_total_sqm` as `core_area_sqm + corridor_area_sqm + shaft_area_sqm`.
  - Keep this additive definition explicit in the function’s docstring to preserve auditability.
  - Design the API so that, in a later phase, richer common-area tags (e.g. `COMMON_CORE`, `COMMON_VERTICAL`, `COMMON_REFUGE`, `COMMON_ACCESS`) can be plugged in either as:
    - Additional attributes on `EdgeRecord` / `DetailedWall`, or
    - A higher-level usage classifier layered on top of existing wall types.
  - For Phase 1, collapse these into `shaft_area_sqm` and `common_area_total_sqm` while keeping the interface stable enough to fan them out later without breaking callers.
  - Treat wall polygons as a **separate layer** that may geometrically overlap core/corridor/footprint polygons; partition checks must therefore rely on explicit invariants (rather than strict geometric disjointness) to ensure:
    - `common_area_total_sqm` does not exceed `gross_built_up_sqm` beyond tolerance, and
    - any intentional overlaps between wall polygons and zone polygons are consistently accounted for (document which fields are “area including walls” vs “area excluding walls”).

#### 1.3.a Wall metadata extension (unit–unit vs same-unit)

- Before implementing RERA allocation, extend the wall metadata derived from `EdgeRecord` so that for each `DetailedWall` (or a parallel metadata structure) we can distinguish:
  - Same-unit room–room edges vs room–room edges between two different units.
  - For example, introduce:
    - `adjacent_unit_ids: tuple[str, str] | None` (derived from room IDs → unit IDs).
    - `is_shared_between_units: bool` (True only when the two sides belong to different units).
- This metadata is required so that internal partitions within a single unit can be treated differently from shared walls between units during RERA allocation.

### 1.4 RERA carpet computation per unit

- **Per-unit geometric inputs**
  - Add a function `compute_rera_carpet_for_units(floor: FloorLayoutContract, units: list[UnitLayoutContract], config: DetailingConfig) -> tuple[float, list[float]]` that:
    - Reuses `build_walls_for_floor(...)` results (or accepts precomputed maps) to avoid duplicate work.
    - For each unit:
      - Compute `room_internal_area = sum(room.area_sqm for room in unit.rooms)`.
      - For walls touching that unit’s rooms:
        - For internal walls (shared between two rooms of the same unit): allocate **full thickness** to that unit’s carpet (your “internal partition wall thickness” term).
        - For walls shared between two different units (room–room edges where the rooms belong to different units), apply a configurable shared-wall policy:
          - Introduce a small enum/config, e.g. `SharedWallAllocationPolicy` with options:
            - `HALF` — allocate **50% of wall thickness to each unit** (each side gets half the buffered wall polygon area projected onto carpet).
            - `NONE` — allocate **0% of shared wall thickness** to either unit (strict interpretation for some RERA regimes).
          - Default to `HALF`, but ensure the policy is threaded in as an explicit parameter (not hidden global state).
        - For walls between a room of the unit and the corridor/core (classified as `SHAFT` in the current wall model): treat them as common walls; allocate **zero** thickness to unit carpet (entirely common area).
        - For walls between a unit room and the plot exterior (`EXTERNAL`): treat them as external walls; allocate **zero** thickness to unit carpet.
      - This matches your formula conceptually:
        - `Carpet = sum(room internal area) + internal partition wall thickness - external wall thickness - common wall share`, with the latter two effectively modelled as “no allocation” in the positive direction.
    - Return:
      - `rera_carpet_area_total_sqm`: sum of per-unit carpets.
      - `carpet_per_unit`: list of carpets in a deterministic order, sorted by `unit.unit_id` (string) so the mapping from unit to carpet is stable and testable.
- **Tie together into a full breakdown**
  - Implement `compute_floor_area_breakdown_detailed(floor: FloorLayoutContract, units: list[UnitLayoutContract], config: DetailingConfig) -> FloorAreaBreakdown` that:
    - Calls `compute_floor_base_areas`.
    - Calls `compute_wall_areas_for_floor`.
    - Calls `compute_rera_carpet_for_units`.
    - Constructs a fully-populated `FloorAreaBreakdown` instance with:
      - `gross_built_up_sqm` from footprint.
      - `core_area_sqm`, `corridor_area_sqm` from polygons.
      - `shaft_area_sqm`, `internal_wall_area_sqm`, `external_wall_area_sqm`, `common_area_total_sqm` from wall stats.
      - `unit_envelope_area_sqm` from `floor.unit_area_sum`.
      - `rera_carpet_area_total_sqm` and `carpet_per_unit` from the RERA helper.

### 1.5 Wire breakdown alongside `FloorLayoutContract`

- **Engine-level integration point**
  - Keep `FloorLayoutContract` unchanged to respect existing callers.
  - Expose the area accounting via a separate helper that pairs contracts and breakdowns, e.g.:

```python
# new public helper in backend/area_accounting/floor_area.py
@dataclass
class FloorLayoutWithAreaBreakdown:
    contract: FloorLayoutContract
    area: FloorAreaBreakdown


def build_floor_layout_with_area(
    skeleton: FloorSkeleton,
    floor_id: str = "",
    module_width_m: Optional[float] = None,
    *,
    detailing_config: Optional[DetailingConfig] = None,
) -> FloorLayoutWithAreaBreakdown:
    contract = build_floor_layout(skeleton=skeleton, floor_id=floor_id, module_width_m=module_width_m)
    if detailing_config is None:
        area = compute_floor_area_breakdown_basic(contract)
    else:
        # uses contract.all_units as the unit list for detailed accounting
        area = compute_floor_area_breakdown_detailed(contract, contract.all_units, detailing_config)
    return FloorLayoutWithAreaBreakdown(contract=contract, area=area)
```

- **Future wiring into the development pipeline (not part of Phase 1 core)**
  - Document a follow-up step (Phase 1b/2) where `architecture.services.development_pipeline.generate_optimal_development_floor_plans` optionally calls `build_floor_layout_with_area` instead of `build_floor_layout`, and stores `FloorAreaBreakdown` in `TowerFloorLayoutDTO`.
  - Keep this out of the initial change-set to minimise blast radius while we stabilise the new accounting logic with tests.
  - Treat `build_floor_layout_with_area` as an **opt-in** Phase 1 helper so that, when Phase 3+ introduces multi-configuration search, we can:
    - Run detailed wall/RERA accounting only for shortlisted configurations, and
    - Introduce caching at the floor-layout + wall-graph level without changing the public DTOs.
  - When designing the wall-geometry cache, define its identity semantics up-front, e.g.:
    - Keyed by a stable hash of `(footprint_polygon, sorted room polygons + unit IDs, DetailingConfig thickness parameters)`.
    - So that any future optimisation loop can safely reuse wall geometry across repeated evaluations of the same floor layout configuration.

### 1.6 Tests for Area Accounting

- **Unit-level tests for base areas**
  - In `[backend/area_accounting/tests/test_floor_base_areas.py](backend/area_accounting/tests/test_floor_base_areas.py)`, construct simple synthetic `FloorLayoutContract` instances (rectangular footprint, core, corridor, known `unit_area_sum`) and assert that:
    - `gross_built_up_sqm`, `core_area_sqm`, `corridor_area_sqm`, `unit_envelope_area_sqm`, and `common_area_total_sqm` are correct to a small numeric tolerance.
- **Wall and RERA tests with Phase D geometry**
  - In `[backend/area_accounting/tests/test_floor_wall_and_rera.py](backend/area_accounting/tests/test_floor_wall_and_rera.py)`:
    - Build a small synthetic floor: one or two units, a simple corridor, and external footprint rectangle.
    - Use `DetailingConfig` with known wall thicknesses and run `compute_floor_area_breakdown_detailed`.
    - Assert:
      - `internal_wall_area_sqm` and `external_wall_area_sqm` match analytically-computed values from the simple layout.
      - `shaft_area_sqm` is non-zero when core/corridor walls are present.
      - Per-unit `carpet_per_unit` values match a hand-computed RERA formula for that layout, including:
        - 100% allocation for internal partitions within a unit.
        - 50/50 or 0 allocation for walls shared between two units, depending on the configured `SharedWallAllocationPolicy`.
        - 0 allocation for unit–corridor/core and unit–exterior walls.
- **Determinism and stability guarantees**
  - Add explicit area-partition invariants, e.g.:
    - Depending on the final geometric conventions (outer vs inner faces), enforce a consistent partition such as:
      - `core_area_sqm + corridor_area_sqm + unit_envelope_area_sqm + external_wall_area_sqm + internal_wall_area_sqm + shaft_area_sqm` is within a small tolerance of `gross_built_up_sqm`, or
      - A variant that explicitly subtracts overlapping wall zones if footprint/core/corridor are defined to include wall thickness.
    - `common_area_total_sqm <= gross_built_up_sqm + tol` to guard against double counting between common zones and wall areas.
  - Ensure tests assert not just approximate floats but also these internal compositions so area partition integrity is enforced.
  - Add at least one regression test that freezes the full `FloorAreaBreakdown` for a representative layout (e.g. serialise to a dict and compare against a fixture) to catch accidental changes in future phases, including the derived ratios (`common_area_percentage`, `carpet_to_bua_ratio`, `efficiency_ratio_recomputed`) and the ordering of `carpet_per_unit`.
  - Add a micro-test that confirms the geometric meaning of `DetailedWall.polygon` for a canonical wall (e.g. buffer of a length-1 edge with known thickness) so that:
    - `polygon.area ≈ edge_length * thickness` under the current buffering strategy.
    - Using `polygon.area / 2` for 50/50 shared allocation is mathematically sound under the symmetric-buffer assumption.

