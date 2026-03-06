---
name: Phase 2 Unit Composer
overview: Deterministic one-zone-to-one-layout Unit Composer for Level 2 residential layout. Uses UnitLocalFrame and UnitTemplate only; outputs UnitLayoutContract. No AI, no search, no placement_label. Fallback STANDARD → COMPACT → STUDIO → UNRESOLVED with explicit exceptions and structured logging.
todos:
  - id: phase2-contract
    content: Implement UnitLayoutContract and RoomInstance in residential_layout/models.py; define RoomInstance (room_type, polygon, area_sqm) and UnitLayoutContract (rooms, entry_door_segment, unit_id).
    status: completed
  - id: phase2-errors
    content: Implement UnitZoneTooSmallError, LayoutCompositionError, UnresolvedLayoutError in residential_layout/errors.py with structured reason codes (zone_too_small, room_min_dim_fail, connectivity_fail, wet_wall_alignment_fail, width_budget_fail).
    status: completed
  - id: phase2-frame-adapter
    content: Implement derive_unit_local_frame(skeleton, zone_index) adapter that calls frame_deriver.derive_local_frame and adds band_axis, frontage_edge, wet_wall_line; END_CORE uses frontage_edge when corridor_edge is None.
    status: completed
  - id: phase2-templates
    content: Implement UnitTemplate and RoomTemplate schema and config loader; define STANDARD_1BHK, COMPACT_1BHK, STUDIO templates with min dimensions and room order (no dependence on repetition count).
    status: completed
  - id: phase2-compose-pure
    content: Implement compose_unit(zone, frame, template) pure function with depth budget (required_depth <= band_depth_m), width budget (w_toilet + w_kitchen <= band_length_m), full-width LIVING/BEDROOM strips, back-corner TOILET/KITCHEN (origin-aligned at band 0 and w_toilet), coordinate construction in local frame only, and no input mutation.
    status: completed
  - id: phase2-validation
    content: Implement post-composition validation (no overlaps, all rooms inside zone, min area, wet wall alignment, entry on corridor/frontage edge, connectivity via boundary intersection length).
    status: completed
  - id: phase2-tests
    content: Implement test matrix (single-loaded, double-loaded, end-core, minimal zone, compact fallback, studio fallback, full failure, connectivity fail, wet wall misalignment, dimension fail).
    status: completed
  - id: phase2-orchestrator
    content: Implement fallback orchestrator STANDARD → COMPACT → STUDIO → UNRESOLVED with structured logging on every transition (template_tried, failure_type, reason_code, next_template, band_id).
    status: completed
  - id: phase2-wrapper
    content: Implement resolve_unit_layout_from_skeleton(skeleton, zone_index) that derives frame and zone then calls resolve_unit_layout; do not pass placement_label or skeleton internals.
    status: completed
  - id: phase2-batch
    content: Full TP14 batch resolution at 10 m, 16.5 m, 25 m; record % STANDARD/COMPACT/STUDIO/UNRESOLVED, avg band_depth_m (unresolved), avg band_length_m (width fail). Command: run_phase2_batch_validation.
    status: completed
isProject: false
---

# Phase 2 — Unit Composer: Architectural Design Specification

**LOCKED — Do not modify this spec. Implement as-is; stability first. No optimization, no AI, no alternative slicing.**

**Status:** Implementation-ready design. Build from this plan.  
**Context:** Phase 1.5 (UnitLocalFrame) complete and frozen. FloorSkeleton and UnitZone contracts frozen. Strategy engine unchanged. No AI; no search; deterministic parametric engine only.

---

## 1. Scope Definition

### 1.1 What Phase 2 Does

- **Maps one UnitZone to one deterministic apartment layout.** Given a single zone (or a zone slice), a UnitLocalFrame describing that zone, and a UnitTemplate, Phase 2 produces exactly one layout or raises a defined exception.
- **Enforces minimum dimensions** for every room from the template (min_width_m, min_depth_m, min_area_sqm).
- **Preserves wet wall alignment:** TOILET and KITCHEN backs lie on the wet_wall_line supplied by the frame.
- **Guarantees connectivity:** Every room shares a boundary with LIVING or with the corridor edge; validation is mandatory.
- **Runs the fallback state machine:** STANDARD → COMPACT → STUDIO → UNRESOLVED with explicit failure types and structured logging; no silent degradation.
- **Exposes a single output contract:** UnitLayoutContract (rooms + entry_door_segment only for v1; unit_id nullable). Presentation and repetition depend only on this contract.

### 1.2 What Phase 2 Does Not Do

- **Does not** perform repetition (number of units along the band). Repetition is a separate phase; composer is called once per unit slot with the same template and a zone (or zone slice) and frame.
- **Does not** read or use placement_label, skeleton internals (pattern_used, placement_label, audit_log, etc.), or any strategy engine data.
- **Does not** mutate FloorSkeleton, UnitZone, or any input geometry.
- **Does not** use AI, search, optimization loops, or combinatorial branching.
- **Does not** stretch or resize rooms to consume residual space; room dimensions come only from the template.
- **Does not** depend on repetition count or module_width for its logic; template selection is independent of how many units will be placed.
- **Does not** support staggered wet rooms in depth. v1 assumes toilet and kitchen sit in the same depth band (d_back_strip = max(d_toilet, d_kitchen)). Staggered or L-shaped wet zones are out of scope for v1.

### 1.3 Input Contract (Allowed)


| Input              | Source                                                                    | Usage                                                                                                                                                                                       |
| ------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **UnitZone**       | `skeleton.unit_zones[zone_index]` or a zone slice from repetition         | Polygon and dimensions (zone_width_m, zone_depth_m). Composer uses polygon for containment and frame for axes/edges.                                                                        |
| **UnitLocalFrame** | `derive_unit_local_frame(skeleton, zone_index)` or equivalent for a slice | origin, repeat_axis, depth_axis, band_axis, band_length_m, band_depth_m, frontage_edge, core_edge, corridor_edge, wet_wall_line, band_id. All coordinate and edge decisions use only these. |
| **UnitTemplate**   | Config (e.g. get_unit_template(name))                                     | min_width_m, min_depth_m, room definitions, adjacency rules, min area constraints. Determines cut sequence and minimum geometry.                                                            |


Dimensions used by composer: `band_length_m` and `band_depth_m` from the frame (consistent with zone dimensions). Axis directions from `repeat_axis` and `depth_axis`; no hardcoding of X or Y.

### 1.4 Input Contract (Forbidden)

- **placement_label** — Must not be read. Frontage/corridor/core are defined by the frame only.
- **Skeleton internals** — pattern_used, placement_label, audit_log, area_summary, footprint_polygon, core_polygon, corridor_polygon must not be read. Only the frame (derived from skeleton + zone) is allowed.
- **Strategy engine data** — No dependency on development_strategy, slab_metrics, or strategy generator.
- **Repetition logic** — n_units, module_width_m, residual; composer does not take or use these.

### 1.5 Output Contract

- **Success:** One value of type **UnitLayoutContract** with:
  - **rooms:** list of RoomInstance. Each has room_type (LIVING | BEDROOM | KITCHEN | TOILET), polygon (Shapely), area_sqm. **v1 does not allocate PASSAGE;** remaining width in the back strip is unused; room_type PASSAGE is reserved for future use.
  - **entry_door_segment:** LineString (two-point segment) on the LIVING–corridor (or frontage) shared edge. **Deterministic rule:** segment is **centred** on that shared edge, with **length = door_width_m** (config constant, e.g. 0.9 m). No offset from corners beyond centring; no alignment to bedroom or toilet wall. For END_CORE the shared edge is frontage_edge.
  - **unit_id:** optional (e.g. None for single-unit call; set by repetition when present).
- **Failure:** Exactly one of the following is raised: UnitZoneTooSmallError, LayoutCompositionError. UnresolvedLayoutError is raised by the fallback orchestrator when all templates are exhausted.
- **No other output.** No internal state, no debug layout, no alternative layouts.

---

## 2. Deterministic Slicing Model

### 2.1 Geometric Definitions (from UnitLocalFrame only)

- **band_length_m:** Length of the zone along the band (repetition) direction. Source: `frame.band_length_m`. Axis direction: `frame.repeat_axis`.
- **band_depth_m:** Depth of the zone along the perpendicular direction. Source: `frame.band_depth_m`. Axis direction: `frame.depth_axis`.
- **frontage side:** The zone boundary edge that is the external façade. Source: `frame.frontage_edge`. For END_CORE and SINGLE_LOADED this is the edge opposite the core; for DOUBLE_LOADED it is the edge opposite the corridor.
- **wet_wall_line:** Axis-aligned line (x = k or y = k) through the core_edge. Source: derived from `frame.core_edge`. TOILET and KITCHEN backs must lie on this line.
- **corridor_edge:** Segment of zone boundary shared with the corridor. Source: `frame.corridor_edge`. **Frame contract:** corridor_edge must be the zone boundary segment where LIVING faces the corridor (the entry side). Composer places LIVING with its corridor-facing edge on this segment, so entry_door_segment lies on it and never on bedroom or back-strip side. For DOUBLE_LOADED, frame must define corridor_edge so it is unambiguously the LIVING front (corridor side), not the façade side. For END_CORE, corridor_edge may be None; then the entry edge is frontage_edge.

All coordinates and cuts use the same local frame (origin, repeat_axis, depth_axis). No hardcoding of X or Y.

### 2.2 Template Dimension Semantics (no ambiguity)

- **template.min_depth_m** is the **required total depth** for the unit: the sum of room depths along the depth_axis. Defined as:
  - `required_depth = d_living + d_bed + d_back_strip`
  - where `d_living = template.room("LIVING").min_depth_m + margin_frontage_m`, `d_bed = template.room("BEDROOM").min_depth_m`, `d_back_strip = max(d_toilet, d_kitchen)` (toilet and kitchen share the back strip depth).
  - So **template.min_depth_m = required_depth** (config must set this equal to the sum above, or the loader computes it from room templates). Zone compatibility: **band_depth_m >= template.min_depth_m**.
- **template.min_width_m** is the **required extent along the band_axis**. For v1 (full-width LIVING/BEDROOM, back-corner TOILET/KITCHEN):
  - LIVING and BEDROOM span full band_length_m, so band_length_m must be >= max(living.min_width_m, bedroom.min_width_m).
  - Back strip must fit TOILET + KITCHEN side-by-side: **w_toilet + w_kitchen <= band_length_m**.
  - So **template.min_width_m = max(living.min_width_m, bedroom.min_width_m, w_toilet + w_kitchen)** (or config/compute from room templates). Zone compatibility: **band_length_m >= template.min_width_m**.

### 2.3 Depth Budget (explicit, validated before allocation)

- **Required depth equation:**
  - `d_living = template.room("LIVING").min_depth_m + margin_frontage_m`
  - `d_bed = template.room("BEDROOM").min_depth_m`
  - `d_back_strip = max(template.room("TOILET").min_depth_m, template.room("KITCHEN").min_depth_m)`
  - **required_depth = d_living + d_bed + d_back_strip**
- **Validation (before any room allocation):** **required_depth <= band_depth_m**. If false → UnitZoneTooSmallError (depth budget insufficient). No implied check; this is the explicit depth budget guard.
- **Negative residual guard:** After allocating all rooms, total depth used must not exceed band_depth_m. By construction (LIVING + BEDROOM + back strip) depth used = required_depth; if required_depth <= band_depth_m already checked, no negative residual. If any rounding or placement error causes overflow, fail with LayoutCompositionError.

### 2.4 Width Allocation Model (v1: full-width strips + back-corner block)

**Choice for v1:** LIVING and BEDROOM are **full-width strips** (span full band_length_m along band_axis). TOILET and KITCHEN are **back-corner partial-width rooms** in a single back strip; they do not span full width.

- **LIVING:** Full-width strip. Extent along band_axis: 0 to band_length_m (entire width). Extent along depth_axis: 0 to d_living (from frontage_edge inward). So one rectangle: full width × d_living.
- **BEDROOM:** Full-width strip. Extent along band_axis: 0 to band_length_m. Extent along depth_axis: d_living to d_living + d_bed. So one rectangle: full width × d_bed. **BEDROOM occupies full band_length**; it touches LIVING along the full interface (connectivity guaranteed).
- **Back strip:** Depth band from (d_living + d_bed) to (d_living + d_bed + d_back_strip) = to band_depth_m. Within this strip:
  - **TOILET:** Rectangle with one long edge on wet_wall_line. **Alignment: origin-based.** TOILET starts at **band-axis position 0** (no floating alignment; no centering). Extent along band_axis: **0 to w_toilet**. Extent along depth_axis: back strip. So TOILET occupies [0, w_toilet] × [d_living + d_bed, band_depth_m] in local band/depth coordinates.
  - **KITCHEN:** Adjacent to TOILET along band_axis. Starts at **band-axis position w_toilet**. Extent along band_axis: **w_toilet to w_toilet + w_kitchen**. Same depth band as TOILET. So KITCHEN occupies [w_toilet, w_toilet + w_kitchen] × [d_living + d_bed, band_depth_m].
- **Width budget validation (before placing TOILET/KITCHEN):** **w_toilet + w_kitchen <= band_length_m**. If false → LayoutCompositionError (e.g. room_min_dim_fail or width_budget_fail). No negative residual along width.
- **Remaining width:** `remaining_width = band_length_m - w_toilet - w_kitchen`. In v1 this is **not** allocated to a PASSAGE room; it is unused (circulation/waste). Must be >= 0 (enforced by width budget check). In narrow bands with large w_toilet + w_kitchen, remaining_width is small; when remaining_width is large, efficiency ratio may drop. That is acceptable for v1.

**Lateral adjacency:** BEDROOM is full width, so TOILET and KITCHEN both touch BEDROOM along their front edge (the edge opposite wet_wall_line). So connectivity: LIVING ↔ BEDROOM (full width); BEDROOM ↔ TOILET and BEDROOM ↔ KITCHEN. Entry at LIVING; all rooms reachable. No side-by-side bedroom/kitchen complexity in v1.

### 2.5 Coordinate Construction (single local frame)

- All room polygons are built in the **same local frame as the zone**: origin = frame.origin, first axis = repeat_axis (band), second axis = depth_axis (depth). Coordinates in metres.
- **Construction rule:** Every rectangle is defined by two intervals (min, max) along band_axis and (min, max) along depth_axis, then converted to polygon vertices using origin + scalar × repeat_axis + scalar × depth_axis. No separate "world" or "footprint" coordinate system; zone.polygon is already in this local frame, and output RoomInstance polygons are in this same frame.
- **Output:** UnitLayoutContract.rooms[].polygon are in the same local frame as zone.polygon. Downstream (presentation, repetition) use this frame; no transformation inside composer. This prevents mixing coordinate systems.

### 2.6 Strict Slicing Order (with 2D placement)

1. **Depth budget check:** Compute required_depth; if required_depth > band_depth_m → UnitZoneTooSmallError.
2. **Width budget check:** If w_toilet + w_kitchen > band_length_m → LayoutCompositionError (width_budget_fail).
3. Allocate **LIVING:** full-width strip [0, band_length_m] × [0, d_living] in (band, depth) local coords.
4. Allocate **BEDROOM:** full-width strip [0, band_length_m] × [d_living, d_living + d_bed].
5. Allocate **TOILET:** back-corner block [0, w_toilet] × [d_living + d_bed, band_depth_m]; one edge on wet_wall_line (see Section 6).
6. Allocate **KITCHEN:** [w_toilet, w_toilet + w_kitchen] × [d_living + d_bed, band_depth_m]; shared wall with TOILET at band position w_toilet.
7. Compute **entry_door_segment:** centred on the LIVING–corridor (or frontage) shared edge, length = door_width_m (config). No corner offset; no alignment to bedroom/toilet.
8. Validate dimensions: for each room, **after** rectangle construction, check width >= min_width_m, depth >= min_depth_m, and **area_sqm >= template.room(room_type).min_area_sqm** (if min_area_sqm is defined). Width and depth can pass while area fails (e.g. 1.2×1.2 = 1.44 < min_area 1.6). If any check fails → LayoutCompositionError (room_min_dim_fail).
9. Validate connectivity (Section 5).
10. Validate wet wall alignment (Section 6).

---

## 3. Template System

### 3.1 UnitTemplate Schema

- **name:** str (e.g. "1BHK_STANDARD", "1BHK_COMPACT", "STUDIO").
- **min_width_m:** float. **Defined as** the required zone extent along band_axis: for v1, max(living.min_width_m, bedroom.min_width_m, w_toilet + w_kitchen). Config may set it explicitly or the loader may compute it from room_templates so that zone compatibility band_length_m >= min_width_m and width budget w_toilet + w_kitchen <= band_length_m are consistent.
- **min_depth_m:** float. **Defined as** the required total depth: required_depth = d_living + d_bed + max(d_toilet, d_kitchen). Config may set it explicitly or the loader may compute it from room_templates so that depth budget required_depth <= band_depth_m is the zone compatibility check.
- **room_templates:** Ordered list (LIVING, BEDROOM, KITCHEN, TOILET; or LIVING, TOILET for STUDIO). Each: min_width_m, min_depth_m, min_area_sqm (optional).
- **adjacency_rules:** (from_room, to_room, relation). MUST_TOUCH etc. (e.g. KITCHEN–TOILET).
- **wet_zone_alignment_flag:** bool. TOILET/KITCHEN align to wet_wall_line.

**door_width_m:** float (config constant, e.g. 0.9 m). Length of entry_door_segment; door is centred on LIVING–corridor (or frontage) shared edge. May live in template or in global residential_layout config.

Template does not reference repetition count or module_width.

### 3.2 Named Variants

- **STANDARD_1BHK:** Full 1BHK; largest min dimensions.
- **COMPACT_1BHK:** Same rooms; smaller min dimensions.
- **STUDIO:** LIVING + TOILET only; smallest min dimensions.

Cut sequence: template room_templates order (LIVING first, then BEDROOM, TOILET, KITCHEN for 1BHK; TOILET only after LIVING for STUDIO).

---

## 4. Fallback State Machine


| Current template | Failure type         | Next action                                         |
| ---------------- | -------------------- | --------------------------------------------------- |
| STANDARD_1BHK    | ZoneTooSmall         | Try COMPACT_1BHK                                    |
| STANDARD_1BHK    | RoomMinDimensionFail | Try COMPACT_1BHK                                    |
| STANDARD_1BHK    | ConnectivityFail     | Try COMPACT_1BHK                                    |
| STANDARD_1BHK    | WetWallAlignmentFail | Try COMPACT_1BHK                                    |
| COMPACT_1BHK     | ZoneTooSmall         | Try STUDIO                                          |
| COMPACT_1BHK     | RoomMinDimensionFail | Try STUDIO                                          |
| COMPACT_1BHK     | ConnectivityFail     | Try STUDIO                                          |
| COMPACT_1BHK     | WetWallAlignmentFail | Try STUDIO                                          |
| STUDIO           | ZoneTooSmall         | UNRESOLVED                                          |
| STUDIO           | RoomMinDimensionFail | UNRESOLVED                                          |
| STUDIO           | ConnectivityFail     | UNRESOLVED                                          |
| STUDIO           | WetWallAlignmentFail | UNRESOLVED                                          |
| STANDARD_1BHK    | WidthBudgetFail      | Try COMPACT_1BHK                                    |
| COMPACT_1BHK     | WidthBudgetFail      | Try STUDIO                                          |
| STUDIO           | WidthBudgetFail      | UNRESOLVED                                          |
| UNRESOLVED       | —                    | Do not produce UnitLayoutContract; return fallback. |


**Failure types:** ZoneTooSmall (→ UnitZoneTooSmallError); RoomMinDimensionFail, ConnectivityFail, WetWallAlignmentFail, **WidthBudgetFail** (w_toilet + w_kitchen > band_length_m → LayoutCompositionError); all with reason_code.

**Exceptions:** UnitZoneTooSmallError; LayoutCompositionError (reason: room_min_dim_fail | connectivity_fail | wet_wall_alignment_fail | width_budget_fail); UnresolvedLayoutError (orchestrator).

**Logging (every transition):** timestamp, phase "unit_composer", template_tried, failure_type, reason_code (zone_too_small | room_min_dim_fail | connectivity_fail | wet_wall_alignment_fail | width_budget_fail), next_template (or "UNRESOLVED"). No silent degradation.

---

## 5. Connectivity Guarantee

**Rule:** Every room must share a boundary with LIVING or with the entry edge (corridor_edge when present, else frontage_edge for END_CORE). No isolated room.

**v1 layout guarantees connectivity by construction:** LIVING and BEDROOM are full-width strips; BEDROOM touches LIVING along the full interface. TOILET and KITCHEN are in the back strip and touch BEDROOM (full width) along their front edge. So path: LIVING ↔ BEDROOM ↔ TOILET and LIVING ↔ BEDROOM ↔ KITCHEN. No bedroom “blocking” kitchen from living; both TOILET and KITCHEN connect to LIVING via BEDROOM.

**Validation:** Boundary intersection length. For each room R (except LIVING), shared length of R’s boundary with LIVING or entry edge must be > tolerance (e.g. 1e-6 m). LIVING must share length > tolerance with entry edge. Else → ConnectivityFail → LayoutCompositionError.

---

## 6. Wet Wall Logic (alignment reference and span)

**wet_wall_line:** From frame (axis-aligned line through core_edge). Composer uses only the line provided; does not read pattern_used or band_id.

**Alignment reference:** Origin-based. No floating alignment; no centering. Ensures repetition (translation along band) preserves vertical stacking without drift.

- **TOILET band-axis position:** TOILET starts at **band-axis coordinate 0** (origin). So the TOILET rectangle’s edge on the wet_wall_line spans from origin to (origin + w_toilet along band_axis). The wet_wall_line segment that TOILET occupies is therefore of length w_toilet, starting at the origin-aligned end of the zone.
- **TOILET geometry:** One long edge of the TOILET rectangle must coincide with wet_wall_line over length w_toilet (distance 0 within tolerance). Depth d_toilet perpendicular to that edge. No offset from the line.
- **KITCHEN band-axis position:** KITCHEN starts at **band-axis coordinate w_toilet** (immediately after TOILET). So KITCHEN’s wet-adjacent edge (if any) or shared wall with TOILET lies at band position w_toilet. KITCHEN spans [w_toilet, w_toilet + w_kitchen] along band_axis; same depth strip as TOILET.
- **Kitchen alignment:** KITCHEN must share a boundary segment with TOILET (length > tolerance). Same back strip depth; no floating alignment.

**If band_length_m < w_toilet:** Zone compatibility (template.min_width_m and width budget w_toilet + w_kitchen <= band_length_m) already fails before placement; UnitZoneTooSmallError or LayoutCompositionError. So TOILET width never exceeds band length when placement runs.

---

## 7. Residual Space Handling

Composer fills the zone (or slice) with one layout; no “residual” inside the zone for composer. Repetition slices the band and calls composer per segment. Composer never stretches rooms. Residual threshold and n_units are repetition-phase only.

---

## 8. Composer API

**Pure function (core):**

```
compose_unit(zone: UnitZone, frame: UnitLocalFrame, template: UnitTemplate) -> UnitLayoutContract
```

Pure; no mutation; no global state. Template supplied by caller.

**Wrapper:**

```
compose_unit_from_skeleton(skeleton: FloorSkeleton, zone_index: int, template: UnitTemplate) -> UnitLayoutContract
```

Implementation: zone = skeleton.unit_zones[zone_index], frame = derive_unit_local_frame(skeleton, zone_index), then compose_unit(zone, frame, template). Do not pass placement_label.

**Orchestrator:** Try STANDARD → on error log and try COMPACT → on error log and try STUDIO → on error log and raise UnresolvedLayoutError (or return room_splitter fallback). One call to compose_unit per template; no search.

---

## 9. Validation Invariants (Checklist)

After composition, validate; on any failure raise LayoutCompositionError:

1. **Depth budget:** required_depth <= band_depth_m (checked before allocation; fail fast if not).
2. **Width budget:** w_toilet + w_kitchen <= band_length_m (checked before TOILET/KITCHEN placement).
3. No overlaps (pairwise room intersection area < tolerance).
4. All rooms inside zone polygon.
5. All rooms >= template min area: RoomInstance.area_sqm >= template.room(room_type).min_area_sqm (if defined). Check after rectangle construction; width/depth pass but area fail → room_min_dim_fail.
6. TOILET and KITCHEN have boundary segment on wet_wall_line; TOILET origin-aligned at band 0.
7. entry_door_segment centred on LIVING–corridor (or frontage) shared edge, length = door_width_m, inside LIVING.
8. Connectivity: every room shares boundary with LIVING or entry edge (Section 5).

---

## 10. Edge Case Behaviour


| Case                             | Behaviour                                                             |
| -------------------------------- | --------------------------------------------------------------------- |
| Narrow bands (4–5 m)             | Template minima only; ZoneTooSmall → fallback; all fail → UNRESOLVED. |
| Deep narrow zone                 | One unit; composer fills zone.                                        |
| Band barely larger than template | If meets minima → one layout; else fallback. No stretching.           |
| Multi-tower                      | Composer called per zone; independent; no cross-tower state.          |


---

## 11. Performance

O(1) per zone (fixed room set). No iteration over candidate layouts. No combinatorial branching. At most three template attempts per zone (STANDARD, COMPACT, STUDIO).

---

## 12. Test Matrix (Implement These)

1. Single-loaded slab: one zone, corridor and core edges; expect LIVING, BEDROOM, KITCHEN, TOILET; entry on corridor; wet on wet_wall_line.
2. Double-loaded slab: two zones; two layouts; wet_wall_line per band.
3. End-core slab: corridor_edge None; entry on frontage_edge; valid layout.
4. Minimal viable zone: dimensions = template min; success, rooms at min.
5. Compact fallback: zone too small for STANDARD, fits COMPACT; one fallback, COMPACT succeeds.
6. Studio fallback: STANDARD and COMPACT fail, STUDIO succeeds.
7. Full failure: zone too small for STUDIO; UnresolvedLayoutError; three logged failures.
8. Connectivity fail: room not touching LIVING/entry; LayoutCompositionError connectivity_fail.
9. Wet wall misalignment: TOILET off line; LayoutCompositionError wet_wall_alignment_fail.
10. Dimension fail: room below min; LayoutCompositionError room_min_dim_fail.
11. Width budget fail: w_toilet + w_kitchen > band_length_m; LayoutCompositionError width_budget_fail; orchestrator tries next template.

---

## 13. Explicitly Forbidden

- AI, search, optimization, combinatorial layout try.
- Mutating input geometry or shared state.
- Reading placement_label or skeleton internals (only frame from derive_unit_local_frame).
- Reading strategy engine (development_strategy, slab_metrics).
- Stretching rooms to consume residual.
- Dependence on n_units, module_width, repetition.
- Silent degradation; implicit or alternate fallback order.

---

## Document Control

**Version:** 1.2  
**Source:** Level 2 Phase 2; aligned with Phase 1.5 UnitLocalFrame and Level 2 main plan.  
**Build:** Use the todos in the front matter for implementation order.

**Character:** Phase 2 is a **deterministic spatial compiler**: one (zone, frame, template) → one layout or exception. No flexibility, no optimization, no alternate layouts. Correct for POC.

**Revision 1.2 (future-proofing / clarity):** v1 does not support staggered wet rooms in depth (documented in 1.2). Entry door rule: centred on LIVING–corridor shared edge, length = door_width_m. PASSAGE not allocated in v1; remaining width unused. Min area enforced explicitly after rectangle construction (area_sqm >= min_area_sqm). Frame contract: corridor_edge is LIVING front (entry side). Remaining width / efficiency note for narrow bands. Revision 1.1 (structural): Added explicit depth budget (required_depth equation and validation); width allocation model (full-width LIVING/BEDROOM, back-corner TOILET/KITCHEN with origin-aligned placement); template.min_width_m / template.min_depth_m semantics; coordinate construction (single local frame); wet-wall alignment span and origin-based rule (toilet at band 0, kitchen at w_toilet); width budget guard (w_toilet + w_kitchen <= band_length_m) and WidthBudgetFail; connectivity by construction (BEDROOM full width so TOILET/KITCHEN connect via BEDROOM).