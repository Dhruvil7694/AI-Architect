---
name: level2-residential-layout-engine
overview: Roadmap to evolve the existing Architecture AI pipeline into a deterministic, parametric Level 2 residential floor plan engine without AI search, preserving the current envelope→placement→core→skeleton→DXF architecture.
todos:
  - id: phase1-templates
    content: Design and implement RoomTemplate and UnitTemplate dataclasses and config loader in a new residential_layout module.
    status: pending
  - id: phase1b-frames
    content: Implement UnitLocalFrame abstraction and derive_unit_local_frame(skeleton, zone_index) so all layout logic is orientation-agnostic.
    status: pending
  - id: phase2-composer
    content: Specify and implement deterministic 1BHK UnitComposer using UnitLocalFrame only; explicit exceptions and fallback order Standard→Compact→Studio→UNRESOLVED.
    status: pending
  - id: phase3-wet-shaft
    content: Design wet stack and WetWallStrategy per pattern (END_CORE, SINGLE_LOADED, DOUBLE_LOADED); shaft alignment tied to core geometry.
    status: pending
  - id: phase4-repetition
    content: Module-width-first unit repetition; residual band rules; deterministic mirroring for double-loaded; post-repetition validation.
    status: pending
  - id: phase5-presentation
    content: Extend presentation via UnitLayoutContract only; consume semantic room/unit data, place doors, add minimal dimensions.
    status: pending
  - id: phase6-scoring
    content: Add a deterministic scoring module that evaluates layout efficiency, circulation, wet alignment, and daylight proxies.
    status: pending
isProject: false
---

**Implementation-ready revision:** See [level2-residential-layout-engine_REVALIDATION.md](level2-residential-layout-engine_REVALIDATION.md) for the full architectural revalidation (design gaps, corrections, refactored phases, risk matrix, readiness score). Key additions: UnitLocalFrame (Phase 1.5), WetWallStrategy, module-width-first repetition, UnitLayoutContract, explicit failure/fallback hierarchy, and edge-case rules.

# Level 2 Residential Layout Engine Roadmap

## Overall architecture

- **Pipeline (unchanged at top level)**: `Plot → Envelope → Placement → CoreFit → FloorSkeleton → UnitComposer (new) → Presentation DXF`.
- **New domain layer**: a `residential_layout` module that sits between `floor_skeleton` and `presentation_engine` and owns unit templates, room templates, and deterministic composition logic.
- **Configuration first**: all room/unit dimensions and adjacency constraints live in config (YAML/JSON), loaded into dataclasses; no new hard-coded numeric constants.

A simple flow diagram:

```mermaid
flowchart LR
  plot[Plot] --> envelope[EnvelopeEngine]
  envelope --> placement[PlacementEngine]
  placement --> coreFit[CoreFitValidator]
  coreFit --> skeleton[FloorSkeleton]
  skeleton --> unitComposer[UnitComposer (new)]
  unitComposer --> presentation[PresentationEngine]
  presentation --> dxf[DXF Export]
```



---

## Canonical Geometry Contract (UnitLocalFrame)

All layout logic (Unit Composer, repetition, presentation) uses a single geometric abstraction. No orientation branching; no direct use of `placement_label` or skeleton internals.

### Contract fields (read-only)

| Field | Type | Definition |
|-------|------|------------|
| **origin** | `tuple[float, float]` | Pure geometric: min corner of zone bounds (deterministic). From Phase 1.5 `UnitLocalFrame.origin`. |
| **band_axis** | `Literal["X","Y"]` | Axis along band (repetition direction). Derived: `(1,0)` → `"X"`, `(0,1)` → `"Y"` from `repeat_axis`. |
| **depth_axis** | `tuple[float, float]` | Normalized direction perpendicular to band. From Phase 1.5 `UnitLocalFrame.depth_axis`. |
| **repeat_axis** | `tuple[float, float]` | Normalized band direction. From Phase 1.5 `UnitLocalFrame.repeat_axis`. |
| **frontage_edge** | Segment or None | Zone boundary edge that is the external façade (opposite core for END_CORE/SINGLE_LOADED; opposite corridor for DOUBLE_LOADED). Derived from zone polygon and core/corridor adjacency. |
| **core_edge** | `tuple[(x,y),(x,y)] \| None` | Longest shared segment between zone and core. From Phase 1.5 `UnitLocalFrame.core_facing_edge`. |
| **corridor_edge** | `tuple[(x,y),(x,y)] \| None` | Longest shared segment between zone and corridor. From Phase 1.5 `UnitLocalFrame.corridor_facing_edge`. |
| **wet_wall_line** | Axis-aligned line | Line (x = k or y = k) through `core_edge`; toilet back must lie on this line. Derived from `core_edge`. |
| **band_length_m** | float | Length of zone along band_axis. From Phase 1.5. |
| **band_depth_m** | float | Depth of zone along depth_axis. From Phase 1.5. |
| **band_id** | int | Stable band index. From Phase 1.5. |

### Single entry point

```
derive_unit_local_frame(skeleton: FloorSkeleton, zone_index: int) -> UnitLocalFrame
```

- **Implementation:** Call `floor_skeleton.frame_deriver.derive_local_frame(skeleton, skeleton.unit_zones[zone_index])`; then compute `band_axis`, `frontage_edge`, `wet_wall_line` from that result. Expose a single type (Phase 1.5 `UnitLocalFrame` plus derived fields, or an extended view in `residential_layout`) so that callers receive one object with all fields.
- **Composer must not:** read `placement_label`; inspect `skeleton` beyond calling `derive_unit_local_frame(skeleton, zone_index)` and using the returned frame; use `UnitZone` orientation or polygon except as provided via the frame.
- **Composer must:** use only `UnitLocalFrame` (and the derived band_axis, frontage_edge, wet_wall_line) for all coordinate and edge decisions.

---

## Phase 1 — Parametric Unit Template System

**Goal:** Define an explicit, configurable model of 1BHK units and their constituent rooms, independent of geometry algorithms.

### 1.1 New modules

- `**backend/residential_layout/` (new package)**
  - `templates.py`: dataclasses for `RoomTemplate`, `UnitTemplate`, `AdjacencyRule`.
  - `config_loader.py`: load/validate YAML/JSON config into template objects.
  - `enums.py`: enums/constants for room types (`LIVING`, `BEDROOM`, `KITCHEN`, `TOILET`, `PASSAGE`), orientations (`FRONTAGE`, `CORE`, `NEUTRAL`).
  - `errors.py`: domain-specific exceptions (e.g. `TemplateConfigError`).

### 1.2 Data model

- **RoomTemplate (dataclass)**
  - `name: str` (e.g. "LIVING", "BEDROOM")
  - `min_width_m: float`
  - `min_depth_m: float`
  - `preferred_orientation: Literal["FRONTAGE","CORE","NEUTRAL"]`
  - `must_touch_core: bool`
  - `must_touch_corridor: bool`
  - Reserved for future strictness: `max_aspect_ratio`, `min_area_sqm`.
- **UnitTemplate (dataclass)**
  - `name: str` (e.g. `"1BHK_STANDARD"`, `"1BHK_COMPACT"`)
  - `min_width_m: float`
  - `min_depth_m: float`
  - `room_templates: list[RoomTemplateRef]` (ordered program: living, bedroom, kitchen, toilet(s)).
  - `adjacency_rules: list[AdjacencyRule]` (e.g. LIVING–CORRIDOR, BEDROOM–LIVING, KITCHEN–TOILET shared wall).
  - `wet_zone_alignment_flag: bool` (controls whether toilets/kitchen must align to core/shaft side).
- **AdjacencyRule (dataclass)**
  - `from_room: str`
  - `to_room: str`
  - `relation: Literal["MUST_TOUCH","PREFER_TOUCH","MUST_NOT_TOUCH"]`
  - `share_wet_wall: bool` (for kitchen–toilet).

### 1.3 Config structure

- `**config/residential_units.yaml` (or similar)**, e.g.:
  - Global section for room defaults (min sizes per room type).
  - Templates section for unit types (1BHK variants) referencing room types.
- **Config loader responsibilities**:
  - Validate schema and required fields.
  - Cross-validate that referenced room templates exist.
  - Provide a simple query API: `get_unit_template(name)`, `get_default_1bhk()`.

### 1.4 Integration points

- **With FloorSkeleton**:
  - No change to generator; it still returns `FloorSkeleton` with `unit_zones`.
  - New code will later consume `UnitZone` + `UnitTemplate` to create room-level layouts.

### 1.5 Complexity & risk

- **Complexity:** Low–Medium (mostly modeling and configuration). 
- **Risks:**
  - Over-fitting the data model to 1BHK only; keep templates general enough for future 2BHK.
  - Config validation needs to be strict to avoid runtime surprises.

---

## Phase 2 — Deterministic Unit Composer

**Goal:** Given a skeleton, zone index, and template, produce one `UnitLayout` that satisfies program and dimensions. Single-unit only; no repetition. All decisions use only `UnitLocalFrame`.

### 2.1 Exception classes (mandatory)

Define in `backend/residential_layout/errors.py`:

| Exception | When raised |
|-----------|-------------|
| **UnitZoneTooSmallError** | `zone_width_m < template.min_width_m` or `zone_depth_m < template.min_depth_m` for the chosen template. |
| **LayoutCompositionError** | Deterministic cut sequence produces a room below min dimensions or min area; or connectivity check fails. |
| **UnresolvedLayoutError** | All fallbacks (STANDARD → COMPACT → STUDIO) exhausted; no valid layout. |

Composer **must** raise these explicit errors. Composer **must** log a structured reason (e.g. `zone_too_small`, `room_min_dim_fail`, `connectivity_fail`) on each fallback. Composer **must not** silently degrade.

### 2.2 Fallback state machine

| State | Condition | Next state |
|-------|-----------|------------|
| STANDARD | zone &lt; template min (width or depth) | COMPACT |
| STANDARD | layout_fail (dimension or connectivity) | COMPACT |
| COMPACT | zone &lt; compact template min | STUDIO |
| COMPACT | layout_fail | STUDIO |
| STUDIO | zone &lt; studio template min | UNRESOLVED |
| STUDIO | layout_fail | UNRESOLVED |
| UNRESOLVED | — | Return fallback to current room_splitter output; do not produce UnitLayout. |

Template order is fixed: try STANDARD (e.g. `1BHK_STANDARD`), then COMPACT (`1BHK_COMPACT`), then STUDIO. No other order. No search.

### 2.3 Algorithm (strict, deterministic)

1. **Frame**
   - Call `derive_unit_local_frame(skeleton, zone_index)`. All coordinates and cuts use this frame only. Do not read `placement_label`. Do not inspect `skeleton` except via this call.

2. **Template compatibility**
   - If `band_length_m` or `band_depth_m` &lt; `template.min_width_m` or `template.min_depth_m` (mapped by band_axis): raise `UnitZoneTooSmallError`. Caller catches and transitions to next state (COMPACT / STUDIO / UNRESOLVED).

3. **Primary slice**
   - Reserve a strip along **frontage_edge** for **LIVING** with depth = template LIVING min_depth_m + margin. Use band_axis and depth_axis from frame.

4. **Back-to-front sequence**
   - Behind LIVING along band: place **BEDROOM** (template dimensions). At **core_edge**, carve **TOILET** so that toilet back lies on **wet_wall_line**. Place **KITCHEN** adjacent to TOILET on shared wall; dimensions from template.

5. **Corridor entry**
   - Set `entry_door_segment` on **corridor_edge** of LIVING. Deterministic offset: centre of corridor_edge segment (no placement_label bias).

6. **Dimension guards**
   - After each cut, verify every room has `min_width_m`, `min_depth_m`, `min_area_sqm` from template. If any fails: raise `LayoutCompositionError` (caught → next fallback state).

7. **Connectivity (mandatory)**
   - Post-slice check: every room **must** share an edge with LIVING or with the corridor_edge (segment of zone boundary that is corridor_edge). If any room does not: raise `LayoutCompositionError`. No optional validation; this check is required.

8. **Output**
   - Return `UnitLayout` implementing `UnitLayoutContract`: `rooms`, `entry_door_segment`, `unit_id` (None for single-unit call).

### 2.4 New modules

- `backend/residential_layout/unit_composer.py`: `compose_unit(skeleton, zone_index, template) -> UnitLayout`. Input is skeleton + zone_index + template; no raw UnitZone or placement_label.
- `backend/residential_layout/models.py`: `UnitLayout` (holds rooms, entry_door_segment, metadata); `RoomInstance` (room_type, polygon, dims).
- `backend/residential_layout/errors.py`: `UnitZoneTooSmallError`, `LayoutCompositionError`, `UnresolvedLayoutError`.

### 2.5 Integration

- **Input:** `FloorSkeleton`, `zone_index: int`, `UnitTemplate` (from config). Frame is derived inside composer via `derive_unit_local_frame(skeleton, zone_index)`.
- **Output:** `UnitLayout` fulfilling `UnitLayoutContract`; or raise; or UNRESOLVED (caller returns room_splitter fallback).

---

## Phase 3 — Wet Wall Strategy and Shaft Alignment

**Goal:** Define one wet wall line per band so that toilet back lies on that line. Pattern and band_id determine the line deterministically.

### 3.1 WetWallStrategy enum

Define in `backend/residential_layout/wet_wall.py` (or `enums.py`):

```python
class WetWallStrategy(Enum):
    END_CORE      # Single band; wet wall = core_edge of that band.
    SINGLE_LOADED # Single band; wet wall = core_edge (corridor between core and units).
    DOUBLE_LOADED_LEFT  # Band 0 (e.g. left of corridor); wet wall = core edge on left.
    DOUBLE_LOADED_RIGHT # Band 1 (e.g. right of corridor); wet wall = core edge on right.
```

Mapping from `skeleton.pattern_used` and `band_id`:

| pattern_used   | band_id | WetWallStrategy       |
|----------------|---------|------------------------|
| END_CORE       | 0       | END_CORE               |
| SINGLE_LOADED  | 0       | SINGLE_LOADED         |
| DOUBLE_LOADED  | 0       | DOUBLE_LOADED_LEFT     |
| DOUBLE_LOADED  | 1       | DOUBLE_LOADED_RIGHT    |

### 3.2 Wet wall line (exact)

- **wet_wall_line** is an axis-aligned line in the local frame: either `x = k` or `y = k`.
- Derived from `UnitLocalFrame.core_edge`: the core_edge segment is axis-aligned; the line is that same constant (e.g. if core_edge has constant x, wet_wall_line is `x = that_value`).
- **Constraint:** Toilet room back (the wall shared with core) must lie on this line. Phase 2 composer enforces this when carving TOILET.

### 3.3 DOUBLE_LOADED mirroring rule

- For **DOUBLE_LOADED**, band 1 (right) is composed by **reflecting** band 0 layout about the **corridor centreline** (axis through corridor polygon centroid, perpendicular to band_axis).
- **Invariants after mirror:**
  - Wet wall alignment preserved: reflected toilet back still lies on the band’s wet wall line (core edge for that band).
  - Entry door segment lies on corridor-facing edge (reflected segment remains on corridor side).
- No rotation; reflection only. Same template; mirror geometry.

### 3.4 ShaftZone (not persisted)

- Notional strip adjacent to core (e.g. 0.6–0.9 m) in local frame for reference. TOILET/KITCHEN align to **wet_wall_line** (from core_edge); ShaftZone is not used for layout decisions in v1. Core footprint is already provided by skeleton; wet wall line is derived from core_edge per band.

---

## Phase 4 — Module-Width-First Unit Repetition

**Goal:** Tile units along each band with a fixed module width. Repetition count is computed before composition. No back-propagation from repetition into slicing.

### 4.1 Canonical module width (no circular dependency)

- **module_width_m** is defined **only** from:
  - `UnitTemplate.min_width_m + inter_unit_gap_m` (config),
  - **not** from composed layout output.
- **Forbidden:** Adjusting template width based on residual; dynamic stretching of rooms; computing module width from a composed unit’s actual width.

### 4.2 Repetition sequence (strict)

1. **Input:** skeleton, zone_index, template (and frame via `derive_unit_local_frame`).
2. **Compute:**
   - `band_length_m` = frame.band_length_m (along band_axis).
   - `margin` = configurable band-end margin (e.g. 0.2 m each end or one value).
   - `n_units = floor((band_length_m - margin) / module_width_m)`.
   - `residual = band_length_m - margin - n_units * module_width_m`.
3. **Residual rule (deterministic):**
   - If `residual < residual_threshold_m` (e.g. 0.3 m): treat as margin; do not add a unit.
   - If `residual >= compact_template_width_m`: allow one compact/studio unit in the residual strip by explicit rule (one extra unit, fixed template).
   - Otherwise: do not add a unit; leave as margin.
4. **Composition:** For each of the `n_units` (and, when the residual rule allows, one additional unit in the residual strip), call composer with the **same** template and a **translated** slice of the zone (same depth, width = module_width_m). Composition uses canonical module_width; composer does not adjust width based on n_units.
5. **Placement:** Units are placed along band_axis from origin with step = module_width_m (left-align). No centering that depends on n_units.

### 4.3 Repetition invariants (validate after tiling)

After placing all units in a band, validate in order:

| Invariant | On failure |
|-----------|------------|
| No overlap between unit polygons | Reduce n_units by 1 and retry placement; if n_units becomes 0, raise UnresolvedLayoutError. |
| All unit polygons inside unit_zone polygon | Reduce n_units by 1 and retry; else UnresolvedLayoutError. |
| Corridor clear width preserved (no unit encroachment into corridor polygon) | Reduce n_units or UnresolvedLayoutError. |
| Wet wall alignment preserved (each unit’s toilet back on wet_wall_line) | UnresolvedLayoutError (do not reduce n_units for wet alignment; fix composition). |
| Entry doors lie on corridor_edge | UnresolvedLayoutError if violated. |

Validation is deterministic: run once per placement; on first failure apply the stated action.

### 4.4 DOUBLE_LOADED

- Compose band 0; get one UnitLayout (canonical). Tile with n_units along band 0.
- For band 1: compose by **mirroring** band 0’s layout about corridor centreline (see Phase 3). Tile band 1 with same n_units (or per-band n_units if band lengths differ); step = module_width_m along that band’s axis.

### 4.5 New modules

- `backend/residential_layout/repetition.py`: `repeat_units(skeleton, zone_index, template, config) -> list[UnitLayout]`. Computes n_units from module_width_m and band_length_m; calls composer per slot; validates invariants; on failure reduces n_units or raises.

---

## UnitLayoutContract (formal)

Presentation and scoring depend only on this contract. No dependency on UnitComposer internals or skeleton state.

```python
@dataclass
class RoomInstance:
    room_type: str   # LIVING | BEDROOM | KITCHEN | TOILET | PASSAGE
    polygon: Polygon
    area_sqm: float

@dataclass
class UnitLayoutContract:
    rooms: list[RoomInstance]
    entry_door_segment: LineString   # Two-point segment on corridor-facing wall
    unit_id: str | None
```

- **Presentation must** consume only `UnitLayoutContract`: list of room instances (polygon, room_type, area_sqm), entry_door_segment, unit_id. Presentation must not inspect slicing internals, skeleton, or placement_label.
- **UnitLayout** in residential_layout implements this contract; no extra fields are part of the contract. For v1, entry_door_segment is sufficient; internal door segments are a future contract extension.

---

## Phase 5 — Presentation Enhancement

**Goal:** Produce DXF from `UnitLayoutContract` only. Replace room_splitter with an adapter that maps contract to RoomGeometry.

### 5.1 Contract-only dependency

- **Input to presentation:** List of `UnitLayoutContract` (one per unit after repetition). No FloorSkeleton, no UnitComposer, no placement_label.
- **Adapter:** `UnitLayoutContract` → list of `RoomGeometry` (polygon, room_type, unit_id). Replace `presentation_engine.room_splitter` with this adapter.
- **Door placer:** Uses `entry_door_segment` from contract for main door; internal doors from room adjacency implied by shared edges. No access to layout internals.
- **Dimensions:** Deterministic: same edges from room polygons every time (slab, living, bedroom, corridor). Layer `A-DIM`.
- **Labels:** room_type and area per room; title block with unit count, typical area, efficiency.

### 5.2 Forbidden in presentation

- Reading placement_label, skeleton.unit_zones, or composer internal state.
- Branching on layout algorithm or template names; only contract fields are used.

---

## Phase 6 — Deterministic Scoring

**Goal:** Numeric score for layout quality from contract and skeleton metrics only. No search; informational.

### 6.1 Input and output

- **Input:** Layout bundle (list of `UnitLayoutContract`) + skeleton metrics (efficiency_ratio, corridor area). Scoring reads only contract and these metrics.
- **Output:** `LayoutScore` (efficiency_score, circulation_score, wet_stack_score, daylight_score, composite_score). No pipeline behaviour change.

### 6.2 Metrics (deterministic)

- Efficiency: from contract room areas and footprint.
- Circulation: corridor area / usable area.
- Wet alignment: share of units with toilet on wet_wall_line (from contract room geometry vs known wet line).
- Daylight: share of LIVING/BED rooms touching frontage_edge (from contract polygons).

---

## Edge Case Rules (deterministic)

| Case | Rule |
|------|------|
| **Band width 4.2–5.0 m** | If band_width_m &lt; standard min_width_m: try COMPACT then STUDIO. If &lt; studio min: UNRESOLVED. No special 4.2 m constant; use template minima. |
| **Band barely larger than template** | One unit fits. residual = band_length_m - margin - module_width_m &lt; residual_threshold_m → treat as margin; n_units = 1. Do not try second unit. |
| **Deep narrow band** | One unit along band; n_units = 1. Residual depth is margin/circulation. No repetition. |
| **Multiple towers** | One FloorSkeleton per tower. Layout runs per skeleton independently. No cross-tower constraint. Wet stack and repetition are per-tower. |
| **Irregular footprint** | Layout assumes axis-aligned skeleton (0,0)–(W,D). Envelope/placement absorb irregularity; layout does not handle non-rectangular skeleton. |

---

## Explicitly Forbidden

- **AI heuristics, search, optimization loops:** Layout is deterministic only; no trial-and-error or cost minimization.
- **Geometry mutation in composer:** Composer reads frame and zone; produces new polygons. It does not mutate skeleton or zone polygons.
- **Direct use of placement_label inside composer:** Composer uses only `derive_unit_local_frame(skeleton, zone_index)` and the returned frame.
- **Stretching rooms to fit residual space:** Room dimensions come from template minima; no scaling or stretching to fill residual.
- **Adjusting template width from residual:** module_width_m is fixed from config/template; n_units is derived from it. No feedback from residual into template width.
- **Optional connectivity or validation:** Connectivity check and repetition invariants are mandatory; no "optional" validation.

---

## Implementation Order

1. Implement UnitLocalFrame (Phase 1.5) — **done** (floor_skeleton).
2. Implement UnitLayoutContract (dataclass + RoomInstance) in residential_layout.
3. Implement exception classes: UnitZoneTooSmallError, LayoutCompositionError, UnresolvedLayoutError.
4. Implement derive_unit_local_frame(skeleton, zone_index) adapter (calls frame_deriver.derive_local_frame; adds band_axis, frontage_edge, wet_wall_line).
5. Implement deterministic UnitComposer (single unit only): compose_unit(skeleton, zone_index, template) → UnitLayout; fallback state machine STANDARD → COMPACT → STUDIO → UNRESOLVED.
6. Implement fallback state machine and structured logging on each transition.
7. Implement repetition (single band): module_width_m from config; n_units = floor((band_length_m - margin) / module_width_m); residual rule; left-align placement.
8. Implement DOUBLE_LOADED mirroring (reflect about corridor centreline; preserve wet wall and entry edge).
9. Add repetition validation (no overlap, containment, corridor width, wet alignment, entry on corridor); reduce n_units or UnresolvedLayoutError.
10. Replace room_splitter with adapter: UnitLayoutContract → RoomGeometry list.
11. Run TP14 batch smoke test (envelope → placement → skeleton → compose → repeat → presentation).

---

## Required refactors & integration summary

- **Minimal refactor principle**
  - Keep `envelope_engine`, `placement_engine`, and `core_fit` unchanged.
  - Keep `floor_skeleton` mostly unchanged; add only small hooks if necessary (e.g. expose more metadata about orientation or core side).
- **Key integration points**
  - New `residential_layout` package sitting between `floor_skeleton` and `presentation_engine`.
  - Presentation engine updated to consume `UnitLayout`-derived room geometries instead of ad-hoc splits.
  - Door placement and DXF exporter extended, not rewritten.

---

## Phase-wise complexity & risk summary

- **Phase 1 (Templates):** Complexity **Low–Medium**, Risk **Low**.
- **Phase 2 (Unit Composer):** Complexity **Medium–High**, Risk **Medium–High** (geometry edge cases, template over-constraint).
- **Phase 3 (Wet Stack/Shaft):** Complexity **Medium**, Risk **Medium** (pattern interactions, double-loaded slabs).
- **Phase 4 (Repetition):** Complexity **High**, Risk **High** (tiling, overlaps, maintaining wet alignment and corridor clearances).
- **Phase 5 (Presentation Enhancements):** Complexity **Medium**, Risk **Medium** (DXF correctness, not breaking existing flows).
- **Phase 6 (Scoring):** Complexity **Low–Medium**, Risk **Low**.

---

## Preconditions for starting frontend UI

Before investing in a frontend that claims Level 2 residential layouts, the backend should at minimum have:

1. **Phase 1 complete** — stable, config-driven templates for 1BHK.
2. **Core of Phase 2 complete** — deterministic 1BHK composition for a single unit zone (even without repetition), producing believable room geometries.
3. **Early Phase 5 hooks** — Presentation engine able to render LIVING/BED/KITCHEN/TOILET with labels and basic dimensions.
4. Preliminary scoring (Phase 6) for at least efficiency+daylight, to drive simple badges or warnings in UI.

Phases 3–4 (wet stack + repetition) can be iterated while the UI is already visualising single-bay, single-sided 1BHK layouts, as long as the data contracts for units/rooms are stable.

---

## Hardened architecture (summary)

The revalidation document ([level2-residential-layout-engine_REVALIDATION.md](level2-residential-layout-engine_REVALIDATION.md)) integrates these corrections into the roadmap:

| Area | Correction |
|------|------------|
| **Geometry** | Introduce **UnitLocalFrame** (origin, band_axis, depth_axis, frontage/core/corridor edges). Single `derive_unit_local_frame(skeleton, zone_index)`. No orientation branching inside composer. |
| **Module width** | **Module-width-first:** canonical `module_width_m` from config or one canonical composition; `n_units = floor((band_length - margin) / module_width_m)` before tiling. **Residual band:** threshold for margin vs second unit; document alignment (e.g. left-align). |
| **Wet wall** | **WetWallStrategy** per pattern: END_CORE/SINGLE_LOADED one band; DOUBLE_LOADED one wet wall line per band (left/right core edge). Vertical alignment = same wet wall line per band across floors. |
| **Connectivity** | By-construction back-to-front + mandatory post-slice check: every room must share an edge with LIVING or corridor_edge; else LayoutCompositionError. |
| **Failure** | Explicit exceptions (`UnitZoneTooSmallError`, `LayoutCompositionError`, `UnresolvedLayoutError`). Fallback state machine: Standard → Compact → Studio → UNRESOLVED. Structured logging on each fallback. |
| **Repetition** | Mirroring: reflect about corridor centreline for opposite band; invariants: wet alignment, entry on corridor side, no overlap, corridor clear width. Validate after repetition. |
| **Presentation** | **UnitLayoutContract** (rooms + types, entry_door_segment, unit_id). Presentation depends only on this. |
| **Edge cases** | Narrow band 4.2–5 m: try compact/studio → UNRESOLVED. Deep narrow: one unit. Band barely larger: one unit + margin. Multiple towers: one layout per skeleton; no cross-tower constraint. |