# Level 2 Residential Layout Engine — Architectural Revalidation Report

**Reference:** `level2-residential-layout-engine_866bbf85.plan.md`  
**Purpose:** Deep architectural revalidation and hardened, implementation-ready revision.  
**Constraints:** No AI; deterministic, parametric only; layout layer between FloorSkeleton and Presentation.

The main plan has been refined with: Canonical Geometry Contract (UnitLocalFrame), strict module-width-first repetition, explicit fallback state machine, WetWallStrategy per pattern, UnitLayoutContract, mandatory connectivity check, repetition invariants, edge-case rules, Explicitly Forbidden list, and Implementation Order. Use the main plan as the source of truth for implementation.

---

## Section A — Critical Design Gaps

### A.1 Canonical geometry & coordinate system

- **No formal UnitLocalFrame.** Phase 2 says "Normalise coordinate frame" and "rely on UnitZone metadata and placement_label" but does not define a single abstraction. Orientation handling is scattered (orientation_axis, placement_label, core/corridor "sides").
- **Axis rules undefined.** "Width-dominant" vs "depth-dominant" is stated but axis semantics (which local axis is band direction, which is depth, origin corner) are not codified. Slicing logic risks branching on multiple ad-hoc checks.
- **Edge tagging absent.** There is no convention that "edge 0 = frontage, edge 1 = core, edge 2 = corridor" (or equivalent). Core-facing vs corridor-facing edges are implied by polygon adjacency, not by a stable tag.
- **Façade direction convention missing.** "Frontage" is used but not formally defined relative to placement_label and pattern (END_CORE vs SINGLE_LOADED vs DOUBLE_LOADED).

### A.2 Template & module width strategy

- **Module width not canonical.** Phase 4 defines module width as "bounding box width of a single 1BHK template + minimum separation." That makes repetition depend on composition output; if composition is not yet run, module width is undefined. No a priori definition (e.g. from `UnitTemplate.min_width_m`) is given.
- **Circular dependency risk.** If "how many units fit" influences composition (e.g. different template when only one unit fits), and composition influences module width, the order of operations is ambiguous.
- **Residual band handling unspecified.** When band width is not an integer multiple of module width, behaviour is undefined: center units, left-align, or allocate a residual strip (e.g. studio / storage / circulation margin). No threshold or rule.

### A.3 Wet wall & shaft logic

- **Not pattern-aware.** Phase 3 "choose one side of core_polygon as primary wet wall" does not define which side for each of SINGLE_LOADED, DOUBLE_LOADED, END_CORE. DOUBLE_LOADED has two unit bands; each band needs a deterministic wet wall (core-facing edge of that band).
- **No WetWallStrategy enum.** Pattern-specific wet-wall placement is not enumerated. Vertical alignment is stated as "wet wall x/y coordinates invariant" but for double-loaded, left and right bands have different extents; the invariant (e.g. toilet back on a fixed x or y line per band) is not formalized.
- **ShaftZone not tied to pattern.** ShaftZone hugs "one side" of core; which side for which band is not specified.

### A.4 Connectivity graph & room access

- **No connectivity model.** Internal circulation is not modeled before or after slicing. Adjacency is mentioned (BED↔LIVING, KITCHEN–TOILET) but only as template rules, not as a graph of room access.
- **Access hierarchy missing.** There is no definition of "entry → LIVING → BEDROOM / KITCHEN / TOILET" or passage allocation. Risk: slicing could produce a bedroom with no door to living or a kitchen unreachable from corridor.
- **No guarantee of navigability.** The "back-to-front sequence" in Phase 2 implies connectivity by construction but is not validated; no post-slice check or rejection if a room is isolated.

### A.5 Failure modes & fallback strategy

- **No explicit exception hierarchy.** Only `TemplateConfigError` (Phase 1) is mentioned. Layout failures (zone too small, cut sequence fails) have no dedicated exception types (e.g. `LayoutCompositionError`, `UnitZoneIncompatibleError`).
- **Fallback order not a state machine.** Fallbacks are listed (compact → studio → UNRESOLVED) but not as a deterministic state machine with explicit transition conditions. "If all fail" is vague.
- **Rejection criteria not enumerated.** Which exact conditions trigger which fallback (e.g. "zone_width < template.min_width_m" → try compact; "any room below min_area" → try studio) are not tabulated.
- **Logging/audit unspecified.** Whether layout failures are logged with structured reasons (for traceability and debugging) is not defined.

### A.6 Repetition logic across bands

- **Mirroring rules not deterministic.** Phase 4: "Use same UnitTemplate mirrored" — reflect about which axis, origin at corridor centre or band edge? No formula.
- **Transformation invariants not stated.** After mirroring, "entry_door_segment on corridor side" and "wet wall aligned to shaft" must hold; these are not written as invariants to verify.
- **Corridor clear width in repetition.** "Corridors maintain required clear width" is stated but not integrated with repetition (e.g. unit entry doors must not encroach; no explicit check that repeated units do not reduce effective corridor width).

### A.7 Presentation coupling

- **No stable contract interface.** Presentation consumes `UnitLayout` output (rooms, entry_door_segment). The plan does not define a minimal `UnitLayoutContract` (e.g. list of room polygons + types + entry segment) that presentation depends on. Risk: presentation may depend on layout internals and break when layout implementation changes.
- **Semantic metadata.** Room types and unit_id are specified for RoomGeometry; this is adequate if the contract is frozen.

### A.8 Edge cases not fully specified

- **Narrow band (4.2–5.0 m).** Current MIN_SPLIT_ZONE_WIDTH = 4.8 m. For Level 2, behaviour when band width is 4.2–5.0 m is not defined (reject, downgrade to studio, or single unit with no repetition).
- **Deep but narrow plot.** One unit along band; repetition count = 1. Not explicitly stated; residual depth handling unclear.
- **Core-heavy slab.** Largely covered by skeleton's min_unit_width_m; layout should state explicitly: if band width < template.min_width_m → fail or studio.
- **Band barely larger than template.** e.g. width = min_width_m + 0.2 m. One unit fits; residual 0.2 m — leave as circulation margin or fail? No rule.
- **Irregular footprint.** By the time we have FloorSkeleton, footprint is axis-aligned (0,0)–(W,D). Irregularity is absorbed by envelope/placement; layout assumes rectangular skeleton. Acceptable if documented.
- **Multiple towers.** Not mentioned. Expected: one FloorSkeleton per tower; layout runs per skeleton; wet stack per tower; no cross-tower constraint. Must be stated explicitly.

---

## Section B — Architectural Corrections

### B.1 UnitLocalFrame abstraction

- **Introduce** a single dataclass `UnitLocalFrame` (in `residential_layout/frames.py` or equivalent):
  - `origin`: corner of unit zone (e.g. frontage–corridor intersection).
  - `band_axis`: `"X"` or `"Y"` — axis along the band (repetition direction).
  - `depth_axis`: the other axis.
  - `frontage_edge`: which polygon edge index or which axis face (e.g. `+Y`) is frontage.
  - `core_edge`: edge/face adjacent to core (or shaft).
  - `corridor_edge`: edge/face adjacent to corridor (for entry).
- **Populate** UnitLocalFrame from `FloorSkeleton` + `UnitZone` + `pattern_used` + `placement_label` via a single deterministic function `derive_unit_local_frame(skeleton, unit_zone_index) -> UnitLocalFrame`. All slicing and door placement use only this frame; no ad-hoc orientation branching inside algorithms.

### B.2 Axis and edge conventions

- **Document** in the plan:
  - Band axis = long dimension of unit zone (consistent with `orientation_axis`).
  - Depth axis = short dimension.
  - Frontage = external façade (opposite core for END_CORE/SINGLE; opposite corridor for DOUBLE_LOADED).
  - Define a small lookup table: for each `(pattern_used, placement_label, unit_zone_index)` the frontage/core/corridor edges are fixed (e.g. by local +X, -X, +Y, -Y or by edge index 0..3).

### B.3 Module-width-first strategy

- **Define** canonical `module_width_m` as a configurable constant (or from `UnitTemplate.min_width_m` + `inter_unit_gap_m`), not derived from composed layout. Use it to:
  - Compute `n_units = floor((band_length_m - margin) / module_width_m)` before composing.
  - Do not derive module_width from composed layout. Use a priori definition only to avoid circularity.
- **Residual band rules:**
  - If `residual = band_length_m - n_units * module_width_m`:
    - If `residual < min_residual_threshold_m` (e.g. 0.3 m): treat as circulation margin; do not try to place an extra unit.
    - If `residual >= second_unit_min_width_m`: allow a second template (e.g. studio) in the residual strip by explicit rule; otherwise leave as margin.
  - Document centering vs left-align: e.g. "units are left-aligned to band origin (frontage–corridor corner) with fixed step module_width_m."

### B.4 WetWallStrategy and pattern-specific logic

- **Introduce** `WetWallStrategy` (enum or dataclass per pattern):
  - `END_CORE`: single band; wet wall = core-adjacent edge of unit zone (one side of core).
  - `SINGLE_LOADED`: single band; wet wall = core-adjacent edge (same as END_CORE conceptually; corridor is between core and units).
  - `DOUBLE_LOADED`: two bands; for each band, wet wall = edge touching core (left band → one core edge, right band → opposite core edge). Define explicitly which core edge (e.g. x = core_x_min vs x = core_x_max) for each band.
- **Vertical alignment:** For each band, define "wet wall line" (e.g. segment or infinite line in local frame). All toilet/kitchen backs in that band must lie on this line (or fixed offset). Composer and repetition must preserve this.

### B.5 Connectivity graph and access

- By construction: back-to-front sequence and door segments so every room is reachable from entry (LIVING ← entry; BEDROOM, KITCHEN, TOILET adjacent to LIVING or corridor). Mandatory post-slice check: all rooms must have at least one shared edge with LIVING or with corridor edge; if not, raise LayoutCompositionError.
- **Passage allocation:** Define corridor segment per unit (e.g. segment of corridor polygon opposite each unit) for door placement; deterministic (e.g. by unit index along corridor).

### B.6 Failure hierarchy and fallback

- **Exception classes:** Add in `residential_layout/errors.py`: e.g. `UnitZoneTooSmallError`, `LayoutCompositionError` (dimension/adjacency failure), `UnresolvedLayoutError` (all fallbacks exhausted).
- **Fallback state machine:** Define explicitly:
  - Try `1BHK_STANDARD` → on failure (zone too small / cut sequence invalid) try `1BHK_COMPACT` → on failure try `STUDIO` → on failure mark `UNRESOLVED` and use current room_splitter output.
- **Rejection criteria table:** Document: e.g. `zone_width_m < template.min_width_m` → next template; `any room area < min_area_sqm` → next template; `connectivity check failed` → next template or UNRESOLVED.
- **Logging:** Require structured log (or audit entry) on every fallback and final UNRESOLVED with reason (e.g. zone_too_small, room_min_dim_fail, connectivity_fail).

### B.7 Repetition: mirroring and invariants

- **Mirroring rule:** For DOUBLE_LOADED, opposite band: reflect unit geometry about the corridor centreline (axis through corridor polygon centroid, perpendicular to band axis). Origin for reflection = corridor centreline. Entry door segment is mirrored so it remains on the corridor side.
- **Invariants:** After repetition (and mirroring): (1) every unit's wet wall aligns to the band's wet wall line; (2) every unit's entry_door_segment lies on the corridor-facing edge; (3) no polygon overlap; (4) all units inside unit zone; (5) corridor clear width ≥ required (e.g. no unit encroachment into corridor polygon).

### B.8 UnitLayoutContract for presentation

- **Define** a minimal interface (e.g. Protocol or dataclass) `UnitLayoutContract`:
  - `rooms: list[RoomInstance]` with `room_type`, `polygon`, `area_sqm`;
  - `entry_door_segment: LineString` (or two-point segment);
  - `unit_id: str | None`; internal door segments are a future extension.
- **Presentation** depends only on this contract. Implementation of `UnitLayout` in residential_layout fulfils this contract; no exposure of internal composition details.

### B.9 Edge case behaviour (deterministic)

- **Narrow band 4.2–5.0 m:** If band width < template.min_width_m → do not attempt 1BHK; try compact or studio; if still below studio min → UNRESOLVED, use current UNIT/ROOM/TOILET split.
- **Deep narrow:** One unit along band; n_units = 1; no repetition. Residual depth = circulation/margin.
- **Core-heavy:** If band width < template.min_width_m after skeleton → fail or studio as above.
- **Band barely larger than template:** One unit; residual < min_residual_threshold_m → treat as margin; do not try second unit.
- **Irregular footprint:** Document: layout assumes axis-aligned skeleton (0,0)–(W,D); envelope/placement handle irregularity.
- **Multiple towers:** Document: one layout run per FloorSkeleton (per tower); wet stack and repetition are per-tower; no cross-tower layout constraint.

---

## Section C — Refactored Phase Plan

### Phase 1 — Parametric Unit Template System

**Goal:** Unchanged. Config-driven 1BHK (and extensible) templates.

**Additions:**

- In `residential_layout/errors.py`: add `TemplateConfigError` only (other layout errors in Phase 2).
- In config: document that `module_width_m` (or `min_width_m + inter_unit_gap_m`) will be used as the canonical module width for repetition (Phase 4); no circular dependency.

**Deliverables:** Unchanged (templates, config loader, enums, RoomTemplate, UnitTemplate, AdjacencyRule).

---

### Phase 1.5 — UnitLocalFrame and orientation (new)

**Goal:** Single canonical coordinate frame per UnitZone so that all downstream logic is orientation-agnostic.

**New modules:**

- `residential_layout/frames.py`:
  - `UnitLocalFrame` dataclass: `origin`, `band_axis` ("X"|"Y"), `depth_axis`, `frontage_edge`, `core_edge`, `corridor_edge` (edge semantics as per B.1/B.2).
  - `derive_unit_local_frame(skeleton: FloorSkeleton, unit_zone_index: int) -> UnitLocalFrame`.
- Document edge tagging: e.g. edge 0 = min_x, 1 = max_y, 2 = max_x, 3 = min_y (CCW) and map frontage/core/corridor from `pattern_used` + `placement_label` + zone index.

**Integration:** Phase 2 composer and Phase 4 repetition use only `UnitLocalFrame`; no direct use of `orientation_axis` or `placement_label` inside slicing.

**Complexity:** Low. **Risk:** Low.

---

### Phase 2 — Deterministic Unit Composer

**Goal:** Unchanged. Compose one unit from UnitZone + template → UnitLayout.

**Algorithm (hardened):**

1. **Frame:** Obtain `UnitLocalFrame` via `derive_unit_local_frame(skeleton, unit_zone_index)`. All coordinates and cuts in this frame.
2. **Compatibility:** If `zone_width_m` or `zone_depth_m` < template minima → raise `UnitZoneTooSmallError` (caught by fallback).
3. **Primary slice:** Use band_axis/depth_axis; reserve frontal strip (frontage side) for LIVING per template.
4. **Back-to-front:** BEDROOM, then TOILET at core_edge, then KITCHEN adjacent to TOILET; all dimensions from template. Wet wall = core_edge strip (ShaftZone or core face).
5. **Corridor entry:** Place `entry_door_segment` on corridor_edge of LIVING (deterministic offset, e.g. centre of corridor edge).
6. **Guards:** After each cut, verify min dimensions and min area; on failure raise `LayoutCompositionError`.
7. **Connectivity (minimal):** Ensure every room shares an edge with LIVING or with the corridor-facing boundary; else raise `LayoutCompositionError`.

**Failure and fallback:**

- Use explicit fallback order: Standard → Compact → Studio → UNRESOLVED.
- On each failure: log reason (zone_too_small, room_min_fail, connectivity_fail); try next template. On UNRESOLVED, return fallback to current room_splitter output.
- **Output:** `UnitLayout` implementing `UnitLayoutContract` (rooms, entry_door_segment, metadata).

**Complexity:** Medium–High. **Risk:** Medium (mitigated by UnitLocalFrame and explicit exceptions).

---

### Phase 3 — Wet Stack + Shaft Logic

**Goal:** Unchanged. Vertical service alignment; shaft/wet wall deterministic per pattern.

**Additions:**

- **WetWallStrategy:** Define per pattern:
  - END_CORE / SINGLE_LOADED: one band; wet wall = core-adjacent edge of unit zone (one side of core polygon).
  - DOUBLE_LOADED: two bands; for band index 0 (e.g. left), wet wall = core edge at min_x; for band index 1 (right), wet wall = core edge at max_x (or equivalent in local frame). Document in plan.
- **ShaftZone:** Notional strip adjacent to core; not used for layout decisions in v1. Wet wall line is derived from core_edge per band.
- **Unit alignment:** In Phase 2, constrain TOILET/KITCHEN to the wet wall line provided by `UnitLocalFrame` (core_edge). Repetition (Phase 4) keeps translation along band only; no rotation — vertical stack preserved.

**Integration with CoreValidationResult:** Unchanged. Use core footprint to derive wet wall line per band; no new persisted core layout view required for v1.

**Complexity:** Medium. **Risk:** Medium (mitigated by WetWallStrategy table).

---

### Phase 4 — Unit Repetition Strategy

**Goal:** Tile composed units along the slab; preserve wet alignment and corridor clear width.

**Module-width-first:**

- **Canonical module_width_m:** From config only: `UnitTemplate.min_width_m + inter_unit_gap_m`. Not from composed layout. Module width is fixed before tiling; n_units = floor((band_length - margin) / module_width_m).
- **Residual:** If residual < threshold, treat as margin; if residual ≥ second_unit_min, allow one studio in residual by explicit rule; otherwise leave as margin. Units left-aligned (or document centering).

**Single-loaded / END_CORE:**

- For each unit zone, compute n_units; place n_units × UnitLayout with step = module_width_m along band_axis from origin. Each instance is translation-only; wet wall line unchanged.

**Double-loaded:**

- Compose one side (e.g. left band); get UnitLayout. For the other side, mirror about corridor centreline (axis through corridor centroid ⊥ band_axis). Mirror rule: reflect all room polygons and entry_door_segment; verify entry stays on corridor side and wet wall stays on core side.
- **Invariants:** No overlap; all inside unit zone; corridor clear width ≥ required; wet wall alignment per band.

**Validation:** After repetition, validate overlap, containment, and corridor width; on failure log and fallback (e.g. reduce n_units or mark band as UNRESOLVED).

**Complexity:** High. **Risk:** High (mitigated by explicit mirroring rule and invariants).

---

### Phase 5 — Presentation Enhancement

**Goal:** Unchanged. DXF with room semantics, doors, minimal dimensions.

**Contract:**

- Presentation consumes only `UnitLayoutContract`: list of room instances (polygon, room_type, area), entry_door_segment, unit_id (nullable). Replace room_splitter with adapter: `UnitLayout` → list of `RoomGeometry` (with room_type, unit_id).
- Door placer uses semantic targets (entry vs internal) from contract. Dimension logic: deterministic edges from room polygons; same set of dimensions every time.

**Complexity:** Medium. **Risk:** Medium (low if contract is frozen).

---

### Phase 6 — Optional Deterministic Scoring

**Goal:** Unchanged. No behavioural change; informational metrics only.

**Additions:** None structural. Scoring reads only from `UnitLayoutContract` and layout metrics; no layout internals.

**Complexity:** Low–Medium. **Risk:** Low.

---

## Section D — Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Orientation bugs in composer (wrong frontage/core) | Medium | High | UnitLocalFrame + single derivation function; no branching on placement_label inside composer |
| Circular dependency (module width ↔ composition) | Medium | High | Module-width-first: define module_width_m a priori or from one canonical composition; fix before repetition |
| Double-loaded wet alignment wrong on one side | Medium | High | WetWallStrategy table; explicit wet wall line per band; mirroring keeps wet wall on core side |
| Non-navigable layout (room without door) | Low–Medium | High | By-construction connectivity + mandatory post-slice connectivity check; raise LayoutCompositionError if failed |
| Fallback order ambiguous or silent failure | Medium | Medium | Explicit exception types; state machine; structured logging on every fallback/UNRESOLVED |
| Presentation coupled to layout internals | Medium | Medium | UnitLayoutContract; presentation depends only on contract |
| Repetition overlap or corridor encroachment | Medium | Medium | Post-repetition validation; invariants documented; reduce n_units or UNRESOLVED on failure |
| Narrow band 4.2–5 m undefined behaviour | Low | Medium | Explicit rule: try compact/studio; else UNRESOLVED; document |
| Multiple towers inconsistent | Low | Low | Document: one layout per skeleton; no cross-tower constraint |

---

## Section E — Readiness Score

| Criterion | Score (0–10) | Notes |
|-----------|--------------|--------|
| **Determinism** | 6 → 8 | After corrections: UnitLocalFrame, module-width-first, WetWallStrategy, and explicit fallback order remove ambiguity. Mirroring and edge-case rules must be implemented as specified. |
| **Robustness** | 5 → 7 | Explicit exceptions, fallback state machine, and residual/margin rules improve robustness. Connectivity check and repetition validation needed. |
| **Scalability** | 6 → 7 | Per-tower layout is independent; repetition is O(n). No fundamental scalability issue; clarity of frame and module width helps. |
| **Extensibility** | 6 → 7 | UnitLayoutContract and template-driven design allow future 2BHK or other patterns; WetWallStrategy and UnitLocalFrame are extensible. |

**Overall (pre → post revalidation):** ~5.75 → ~7.25. The plan is implementation-ready once Phase 1.5 (UnitLocalFrame) is in place, Phase 2/3/4 are updated with the corrections above, and edge-case + failure behaviour is implemented as specified.

---

## Summary of changes to original roadmap

- **New Phase 1.5:** UnitLocalFrame and orientation abstraction.
- **Phase 2:** Use UnitLocalFrame only; explicit exceptions and fallback state machine; minimal connectivity guarantee.
- **Phase 3:** WetWallStrategy per pattern; wet wall line per band for DOUBLE_LOADED.
- **Phase 4:** Module-width-first; residual band rules; deterministic mirroring rule and invariants; validation after repetition.
- **Phase 5:** UnitLayoutContract; presentation depends only on contract.
- **Global:** Edge-case behaviour and multiple-tower behaviour documented; risk matrix and readiness score added.

No AI. Deterministic, production-grade design preserved.
