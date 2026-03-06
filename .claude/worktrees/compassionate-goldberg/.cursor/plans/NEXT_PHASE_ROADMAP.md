# Deterministic Layout Engine — Done vs Remaining

## What We Have Done

### Pipeline (pre–residential)

- **Envelope engine:** Plot → buildable envelope (margins, road width).
- **Placement engine:** Envelope → footprint(s), core fit validation (NBC/GDCR).
- **Floor skeleton:** Footprint + core validation → `FloorSkeleton` (unit_zones, core, corridor, footprint, pattern).

### Residential layout (Phases 2–4)

| Phase | What it does | Status |
|-------|----------------|--------|
| **Phase 2 — Unit Composer** | One `UnitZone` + `ComposerFrame` → one `UnitLayoutContract` (rooms, entry_door_segment). Deterministic fallback STANDARD → COMPACT → STUDIO. | **Done, frozen.** |
| **Phase 3 — Band Repetition** | One band → N slices → `repeat_band(zone, frame, module_width_m)` → `BandLayoutContract` (units, residual_width_m). Abort-band on first slice failure. | **Done, frozen.** |
| **Phase 4 — Floor Aggregation** | Full `FloorSkeleton` → run Phase 3 per band → `build_floor_layout(skeleton)` → `FloorLayoutContract` (all_units, band_layouts, core/corridor/footprint, floor metrics). Mandatory skeleton assertions (band-overlap, band-in-footprint). | **Done, frozen.** |

### Integration and demo

- **generate_floorplan:** Plot → Envelope → Placement → Core → **Step 5: Skeleton** → **Step 5b: build_floor_layout** → Step 6: DXF export. Phase 4 runs after skeleton; on failure, pipeline exits with clear error and no DXF.
- **Demo output:** `[5b] Floor Layout -- Units: N, Bands: B, Unit area: X sq.m, Efficiency: Y%` (+ optional band breakdown). Demo plots documented: TP14 FP101 (END_CORE), TP14 FP126 (DOUBLE_LOADED).

### Supporting pieces

- **UnitLocalFrame / ComposerFrame:** `derive_unit_local_frame(skeleton, zone_index)`; orientation-agnostic layout.
- **Templates:** RoomTemplate, UnitTemplate (STANDARD_1BHK, COMPACT_1BHK, STUDIO).
- **Exceptions:** UnresolvedLayoutError, BandRepetitionError, FloorAggregationError, FloorAggregationValidationError.
- **Tests:** Phase 2, 3, and 4 test matrices covered (unit composer, repetition, floor aggregation).

---

## What Is Remaining

### 1. Phase 5 — Floor stacking + building metrics (not yet designed)

- **Intent:** Multiple floors; aggregate per-floor `FloorLayoutContract` into a building-level result (total units, BUA, building efficiency).
- **Current state:** Only single-floor path exists. No stacking, no building-level contract.
- **Depends on:** Phase 4 (done). Design needed: building-level dataclass, how storey count / height drives floor count, how to pass floor_id per floor.

### 2. Use FloorLayoutContract downstream (M3 / “optional later”)

- **Feasibility:** Feed `FloorLayoutContract` into feasibility so reported unit count, BUA, or efficiency come from the actual layout (e.g. `total_units`, `unit_area_sum`) instead of skeleton-only.
- **Presentation:** Today presentation uses **FloorSkeleton** only (room_splitter splits unit zones; no composed rooms). Remaining work: accept `FloorLayoutContract` (or list of `UnitLayoutContract`) and derive room geometry from contract so DXF shows real LIVING/BED/KITCHEN/TOILET from Phase 2.
- **Scope:** Plan explicitly deferred this to “later” to avoid overbuilding before demo.

### 3. Real PAL DXF ingestion

- **Intent:** Connect real PAL (plot/architecture) DXF ingestion into the engine so real geometry feeds envelope/placement/skeleton.
- **Current state:** Pipeline is driven by DB plot (e.g. TP14) and envelope/placement; no PAL DXF ingestion path wired in.
- **Order:** Sensible after pipeline and demo are stable; then define ingestion contract and plug it in.

### 4. Level2 “Phase 5” — Presentation from contract only

- **Intent (from level2 plan):** Presentation consumes **only** `UnitLayoutContract` (or floor-level list); replace `room_splitter` with an adapter UnitLayoutContract → RoomGeometry.
- **Current state:** Presentation uses skeleton; room_splitter splits unit zones. Composed units exist in `FloorLayoutContract.all_units` but are not yet passed to presentation.
- **Overlap with (2):** Same direction — “use FloorLayoutContract in presentation.”

### 5. Level2 “Phase 6” — Deterministic scoring

- **Intent:** LayoutScore from contract + skeleton (efficiency, circulation, wet alignment, daylight proxies). Informational; no pipeline behaviour change.
- **Current state:** Not implemented. Feasibility has buildability/efficiency from skeleton, not from FloorLayoutContract.

### 6. Optional small items

- **--no-floor-layout:** Flag on generate_floorplan to skip Step 5b (e.g. for debugging). Plan said “add later if needed.”
- **Automated test:** Test that generate_floorplan runs without error for a fixture plot (or that Step 5b runs and returns contract). Plan said optional for M1/M2.

---

## Suggested Next Steps (in order)

1. **Decide next milestone:**  
   - **Option A — Phase 5 (stacking + building):** Design and implement building-level aggregation (multi-floor, building metrics).  
   - **Option B — Use contract in presentation:** Add a path where presentation can consume `FloorLayoutContract` (or `all_units`) so DXF reflects composed rooms and unit count.  
   - **Option C — PAL DXF ingestion:** Design and wire real PAL DXF ingestion into the pipeline.

2. **If Option A:** Write a short **Phase 5 architectural plan** (building-level contract, how floors are stacked, how storey height / building height yields floor count, metrics, no code until plan is agreed).

3. **If Option B:** Plan **“Presentation from FloorLayoutContract”**: adapter from `UnitLayoutContract` to `RoomGeometry`, and how `generate_floorplan` (or presentation entry point) receives and passes the contract; keep skeleton fallback so existing behaviour is preserved.

4. **If Option C:** Plan **“PAL DXF ingestion”**: input format, how it produces or updates plot/envelope/footprint, and where it plugs into the existing pipeline.

---

## Summary table

| Item | Status | Notes |
|------|--------|--------|
| Phase 2 Unit Composer | Done | Frozen. |
| Phase 3 Band Repetition | Done | Frozen. |
| Phase 4 Floor Aggregation | Done | Frozen; skeleton assertions in place. |
| Phase 4 in generate_floorplan | Done | Step 5b, summary, demo plots. |
| Phase 5 (stacking + building) | Not started | Needs design. |
| Use contract in feasibility | Not done | M3 / later. |
| Use contract in presentation | Not done | Level2 Phase 5 / M3. |
| PAL DXF ingestion | Not done | Separate workstream. |
| Deterministic scoring (Phase 6) | Not done | Optional. |
| --no-floor-layout flag | Not done | Optional. |
