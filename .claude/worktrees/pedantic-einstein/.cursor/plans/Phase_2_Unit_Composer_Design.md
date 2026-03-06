# Phase 2 — Unit Composer: Architectural Design Specification

**Use for direct build:** [phase2_unit_composer.plan.md](phase2_unit_composer.plan.md) — same specification with YAML front matter and implementation todos.

**Status:** Implementation-ready design. No code; specification only.  
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

### 1.3 Input Contract (Allowed)

| Input | Source | Usage |
|-------|--------|--------|
| **UnitZone** | `skeleton.unit_zones[zone_index]` or a zone slice from repetition | Polygon and dimensions (zone_width_m, zone_depth_m). Composer uses polygon for containment and frame for axes/edges. |
| **UnitLocalFrame** | `derive_unit_local_frame(skeleton, zone_index)` or equivalent for a slice | origin, repeat_axis, depth_axis, band_axis, band_length_m, band_depth_m, frontage_edge, core_edge, corridor_edge, wet_wall_line, band_id. All coordinate and edge decisions use only these. |
| **UnitTemplate** | Config (e.g. get_unit_template(name)) | min_width_m, min_depth_m, room definitions, adjacency rules, min area constraints. Determines cut sequence and minimum geometry. |

Dimensions used by composer: `band_length_m` and `band_depth_m` from the frame (consistent with zone dimensions). Axis directions from `repeat_axis` and `depth_axis`; no hardcoding of X or Y.

### 1.4 Input Contract (Forbidden)

- **placement_label** — Must not be read. Frontage/corridor/core are defined by the frame only.
- **Skeleton internals** — pattern_used, placement_label, audit_log, area_summary, footprint_polygon, core_polygon, corridor_polygon must not be read. Only the frame (derived from skeleton + zone) is allowed.
- **Strategy engine data** — No dependency on development_strategy, slab_metrics, or strategy generator.
- **Repetition logic** — n_units, module_width_m, residual; composer does not take or use these.

### 1.5 Output Contract

- **Success:** One value of type **UnitLayoutContract** with:
  - **rooms:** list of RoomInstance. Each has room_type (LIVING | BEDROOM | KITCHEN | TOILET | PASSAGE), polygon (Shapely), area_sqm.
  - **entry_door_segment:** LineString (two-point segment) on the corridor-facing edge of LIVING; deterministic placement (e.g. centre of that edge).
  - **unit_id:** optional (e.g. None for single-unit call; set by repetition when present).
- **Failure:** Exactly one of the following is raised: UnitZoneTooSmallError, LayoutCompositionError. UnresolvedLayoutError is raised by the fallback orchestrator when all templates are exhausted, not by the single-unit composer itself.
- **No other output.** No internal state, no debug layout, no alternative layouts.

---

## 2. Deterministic Slicing Model

### 2.1 Geometric Definitions (from UnitLocalFrame only)

- **band_length_m:** Length of the zone along the band (repetition) direction. Source: `frame.band_length_m`. Axis direction: `frame.repeat_axis`.
- **band_depth_m:** Depth of the zone along the perpendicular direction. Source: `frame.band_depth_m`. Axis direction: `frame.depth_axis`.
- **frontage side:** The zone boundary edge that is the external façade. Source: `frame.frontage_edge`. For END_CORE and SINGLE_LOADED this is the edge opposite the core; for DOUBLE_LOADED it is the edge opposite the corridor. All coordinates use the same local frame as the zone.
- **wet_wall_line:** Axis-aligned line (x = k or y = k) through the core_edge. Source: derived from `frame.core_edge`. TOILET and KITCHEN backs must lie on this line (see Section 6).
- **corridor_edge:** Segment of zone boundary shared with the corridor. Source: `frame.corridor_edge`. Entry door is placed on the LIVING side of this edge (segment inside LIVING polygon). For END_CORE, corridor_edge may be None; then the entry edge is defined as frontage_edge (the single external façade edge).

All coordinates and cuts are expressed using the same local frame (origin, repeat_axis, depth_axis). No hardcoding of "X" or "Y" in the slicing logic; axis-aligned cuts are made along directions given by the frame (e.g. a cut perpendicular to band_axis at a distance d from origin along band_axis).

### 2.2 Dimension Equations (formal)

- **Zone compatibility (pre-condition):**  
  `band_length_m >= template.min_width_m` and `band_depth_m >= template.min_depth_m`  
  (with template.min_width_m / min_depth_m mapped to band vs depth by template convention: e.g. template "width" = dimension along band, "depth" = dimension along depth_axis).  
  If either fails → UnitZoneTooSmallError.

- **LIVING strip (depth along depth_axis):**  
  `d_living = template.room("LIVING").min_depth_m + margin_frontage_m`  
  where `margin_frontage_m` is a configurable constant (e.g. 0.0 or small buffer). The LIVING polygon is the strip adjacent to frontage_edge of depth `d_living` and spanning the full band_length_m (or the slice length when used in repetition).

- **Remaining depth for back rooms:**  
  `d_remaining = band_depth_m - d_living`  
  Must satisfy: `d_remaining >= 0` (guaranteed by prior compatibility check and non-negative margin). If `d_remaining < 0` the compatibility check must have failed; treat as logic error and fail fast.

- **BEDROOM depth:**  
  `d_bed = template.room("BEDROOM").min_depth_m`  
  BEDROOM is placed immediately behind LIVING (along depth_axis). Its extent along band_axis is full band_length_m (or slice length).

- **TOILET:** Placed against wet_wall_line. Width (along band_axis): `w_toilet = template.room("TOILET").min_width_m`. Depth: `d_toilet = template.room("TOILET").min_depth_m`. One edge of the TOILET rectangle must coincide with the wet_wall_line over a segment of length at least `min(w_toilet, d_toilet)` (alignment equation in Section 6).

- **KITCHEN:** Adjacent to TOILET (shared wall). Min dimensions from template. Must share a wall segment with TOILET; must not overlap TOILET or BEDROOM.

- **Residual area:** Any remaining area after placing LIVING, BEDROOM, TOILET, KITCHEN is not allocated to rooms. No dynamic resizing of rooms to consume residual. If the remaining area is negative (room sum exceeds zone), LayoutCompositionError is raised before output.

### 2.3 Strict Slicing Order

1. **Allocate LIVING** on the frontage side: strip of depth `d_living` along depth_axis, starting from the frontage_edge boundary.
2. **Allocate BEDROOM** immediately behind LIVING: strip of depth `d_bed` along depth_axis.
3. **Allocate TOILET** against wet_wall_line: rectangle with one long edge on wet_wall_line; dimensions from template. Placement is deterministic (e.g. one end aligned with origin along band_axis, or centred; one fixed rule).
4. **Allocate KITCHEN** adjacent to TOILET: rectangle sharing a wall with TOILET; dimensions from template; deterministic side (e.g. same depth_axis side as BEDROOM or opposite; one fixed rule).
5. **Compute entry_door_segment:** On the corridor_edge, restricted to the LIVING polygon. Midpoint of the intersection of corridor_edge with LIVING boundary, or centre of LIVING’s corridor-facing edge; one deterministic formula.
6. **Validate dimensions:** For each room, `width >= room_template.min_width_m`, `depth >= room_template.min_depth_m`, `area >= room_template.min_area_sqm` (if defined). If any fails → LayoutCompositionError.
7. **Validate connectivity:** See Section 5. If fails → LayoutCompositionError.
8. **Validate wet wall alignment:** See Section 6. If fails → LayoutCompositionError.

No branching on placement_label or pattern; all choices are from frame and template only.

---

## 3. Template System

### 3.1 UnitTemplate Schema

- **name:** str (e.g. "1BHK_STANDARD", "1BHK_COMPACT", "STUDIO").
- **min_width_m:** float. Minimum zone extent along band_axis.
- **min_depth_m:** float. Minimum zone extent along depth_axis.
- **room_templates:** Ordered list of room definitions (LIVING, BEDROOM, KITCHEN, TOILET; for STUDIO: LIVING, TOILET only). Each room definition includes min_width_m, min_depth_m, min_area_sqm (optional).
- **adjacency_rules:** List of (from_room, to_room, relation). Relation: MUST_TOUCH, PREFER_TOUCH, MUST_NOT_TOUCH. Used to constrain which rooms share walls (e.g. KITCHEN–TOILET MUST_TOUCH for wet wall).
- **wet_zone_alignment_flag:** bool. If true, TOILET and KITCHEN must align to wet_wall_line.

Template does not reference repetition count, n_units, or module_width. Template is independent of how many units will be placed.

### 3.2 Named Template Variants

- **STANDARD_1BHK:** Full 1BHK (LIVING, BEDROOM, KITCHEN, TOILET). Largest min_width_m and min_depth_m.
- **COMPACT_1BHK:** Same room set, smaller min dimensions. Used when STANDARD fails (zone too small or layout_fail).
- **STUDIO:** Reduced program: LIVING (combined living/sleeping), TOILET. Smallest min dimensions. Used when COMPACT fails.

Cut sequence is determined by the template’s room_templates order: first LIVING (frontage), then remaining rooms in a fixed back-to-front and wet-adjacency order (BEDROOM, TOILET, KITCHEN for 1BHK; TOILET only for STUDIO). The same deterministic order is used for all templates; only dimensions and room set differ.

### 3.3 How Template Defines Minimum Geometry

- Composer checks zone compatibility using `template.min_width_m` and `template.min_depth_m` (mapped to band_length_m and band_depth_m).
- After each room placement, composer checks that room’s polygon satisfies that room’s `min_width_m`, `min_depth_m`, and if present `min_area_sqm` from the template. Failure triggers LayoutCompositionError and fallback to next template.

---

## 4. Fallback State Machine

### 4.1 Formal Table

| Current template | Failure type | Next action |
|------------------|--------------|-------------|
| STANDARD_1BHK | ZoneTooSmall | Try COMPACT_1BHK |
| STANDARD_1BHK | RoomMinDimensionFail | Try COMPACT_1BHK |
| STANDARD_1BHK | ConnectivityFail | Try COMPACT_1BHK |
| STANDARD_1BHK | WetWallAlignmentFail | Try COMPACT_1BHK |
| COMPACT_1BHK | ZoneTooSmall | Try STUDIO |
| COMPACT_1BHK | RoomMinDimensionFail | Try STUDIO |
| COMPACT_1BHK | ConnectivityFail | Try STUDIO |
| COMPACT_1BHK | WetWallAlignmentFail | Try STUDIO |
| STUDIO | ZoneTooSmall | UNRESOLVED |
| STUDIO | RoomMinDimensionFail | UNRESOLVED |
| STUDIO | ConnectivityFail | UNRESOLVED |
| STUDIO | WetWallAlignmentFail | UNRESOLVED |
| UNRESOLVED | — | Do not produce UnitLayoutContract; return fallback (e.g. room_splitter output). |

Template order is fixed: STANDARD → COMPACT → STUDIO. No other order. No search over templates.

### 4.2 Failure Types

- **ZoneTooSmall:** `band_length_m < template.min_width_m` or `band_depth_m < template.min_depth_m` (with consistent axis mapping). Raises UnitZoneTooSmallError.
- **RoomMinDimensionFail:** After slicing, some room has width < its min_width_m, or depth < its min_depth_m, or area < its min_area_sqm. Raises LayoutCompositionError with reason room_min_dim_fail.
- **ConnectivityFail:** Connectivity validation (Section 5) fails. Raises LayoutCompositionError with reason connectivity_fail.
- **WetWallAlignmentFail:** TOILET or KITCHEN does not have a boundary segment on the wet_wall_line (Section 6). Raises LayoutCompositionError with reason wet_wall_alignment_fail.

### 4.3 Exception Hierarchy

- **UnitZoneTooSmallError:** Subclass of a base layout error (e.g. ResidentialLayoutError). Carries template name and which dimension failed.
- **LayoutCompositionError:** Carries structured reason: one of room_min_dim_fail, connectivity_fail, wet_wall_alignment_fail. Carries template name and optional room/geometry hint.
- **UnresolvedLayoutError:** Raised when all three templates have been tried and all failed. Carries list of failure reasons (one per template attempt).

### 4.4 Structured Error Logging

On every fallback transition, log a structured record (e.g. JSON or typed dict) with:

- **timestamp**
- **phase:** "unit_composer"
- **template_tried:** name of template that failed
- **failure_type:** ZoneTooSmall | RoomMinDimensionFail | ConnectivityFail | WetWallAlignmentFail
- **reason_code:** zone_too_small | room_min_dim_fail | connectivity_fail | wet_wall_alignment_fail
- **next_template:** name of next template to try, or "UNRESOLVED"

No silent degradation; every transition is logged.

---

## 5. Connectivity Guarantee

### 5.1 Deterministic Rule

Every room polygon must share a boundary (edge) with either:

- the LIVING room polygon, or  
- the entry edge: corridor_edge when present, otherwise frontage_edge (for END_CORE with no corridor).

No isolated room is allowed. Equivalently: from the corridor entry (LIVING), every room is reachable by crossing shared edges (doors are placed on those edges by presentation).

### 5.2 Validation Method

**Chosen method: Boundary intersection length.**

- For each room R (other than LIVING):
  - Compute total length of R’s boundary that is shared with LIVING or with the corridor_edge segment (using geometric intersection of boundaries with a tolerance, e.g. 1e-6 m).
  - If this shared length is less than a tolerance (e.g. 1e-6 m), R is not connected → ConnectivityFail.
- LIVING must share a segment with corridor_edge (length > tolerance); otherwise entry is invalid → ConnectivityFail.

Single deterministic pass over rooms; no graph construction required. Alternative (single connected component): build graph with nodes = rooms + “corridor”, edges = shared boundary length > 0; then require one connected component. Either method is deterministic; this spec chooses boundary-intersection-length for simplicity.

---

## 6. Wet Wall Logic

### 6.1 WetWallStrategy (pattern- and band-aware)

Wet wall line is determined by pattern and band_id (see Level 2 plan WetWallStrategy). For each (pattern_used, band_id) the frame provides the same core_edge; wet_wall_line is the axis-aligned line containing that edge (x = k or y = k).

- **END_CORE, band_id 0:** wet_wall_line = line through core_edge.
- **SINGLE_LOADED, band_id 0:** wet_wall_line = line through core_edge.
- **DOUBLE_LOADED, band_id 0:** wet_wall_line = line through core_edge (left band).
- **DOUBLE_LOADED, band_id 1:** wet_wall_line = line through core_edge (right band; mirrored in repetition, not in composer).

Composer receives wet_wall_line from the frame; it does not read pattern_used or band_id for logic, only uses the line provided.

### 6.2 Alignment Equation

- **TOILET:** At least one edge of the TOILET rectangle must lie on the wet_wall_line. That is: the rectangle’s boundary has a segment that coincides with the wet_wall_line over a length >= min(toilet_min_width_m, toilet_min_depth_m) (or a fixed tolerance). No offset: the edge lies on the line (distance from line to segment = 0 within tolerance).
- **KITCHEN:** If wet_zone_alignment_flag is true, KITCHEN must share a wall with TOILET (and thus is adjacent to the wet zone); the shared wall may lie on the same wet_wall_line or immediately adjacent. Exact rule: KITCHEN boundary must share a segment with TOILET boundary (length > tolerance).

Vertical stacking is preserved by repetition: repetition uses translation only along the band; the same wet_wall_line is used for every unit in that band, so toilet backs align vertically across floors.

---

## 7. Residual Space Handling

- When the zone (or slice) has band_length_m > template.min_width_m (e.g. one unit in a long band), the composer still produces one unit layout using the **full** zone extent along the band for that single unit (or the slice given by repetition). Composer does not “leave” residual inside the zone; it fills the zone (or slice) with one layout.
- **Repetition** is responsible for slicing the band into segments of length module_width_m and calling the composer once per segment. Within one call, the zone (or slice) is the segment; there is no “residual” inside that segment for the composer to handle.
- **Threshold (repetition phase):** When repetition has residual band length < residual_threshold_m (e.g. 0.3 m) after placing n_units, that residual is treated as margin; no extra unit is placed. Composer is not involved in that decision.
- **No dynamic resizing:** Composer never stretches rooms to consume leftover space. Room dimensions are fixed by the template and the deterministic cut sequence.

---

## 8. Composer API

### 8.1 Pure Function (core contract)

```
compose_unit(
    zone: UnitZone,           # polygon + zone_width_m, zone_depth_m
    frame: UnitLocalFrame,    # with band_axis, frontage_edge, wet_wall_line, etc.
    template: UnitTemplate
) -> UnitLayoutContract
```

- **Pure:** Same (zone, frame, template) always produces the same UnitLayoutContract. No global state, no hidden config beyond what is in template.
- **No mutation:** Does not modify zone, frame, or any input. Returns a new UnitLayoutContract.
- **Config:** Template is loaded externally; composer receives it as input. No direct file or env access inside compose_unit.

### 8.2 Wrapper (convenience)

A wrapper may be provided for callers that have a skeleton and zone index:

```
compose_unit_from_skeleton(
    skeleton: FloorSkeleton,
    zone_index: int,
    template: UnitTemplate
) -> UnitLayoutContract
```

Implementation: obtain zone = skeleton.unit_zones[zone_index], frame = derive_unit_local_frame(skeleton, zone_index), then call compose_unit(zone, frame, template). The wrapper must not pass placement_label or any other skeleton internals to the core logic.

### 8.3 Fallback Orchestrator

The **fallback state machine** is implemented by an orchestrator that:

1. Tries STANDARD_1BHK; on UnitZoneTooSmallError or LayoutCompositionError, logs and tries COMPACT_1BHK.
2. Tries COMPACT_1BHK; on same errors, logs and tries STUDIO.
3. Tries STUDIO; on same errors, logs and raises UnresolvedLayoutError (or returns a sentinel for “use room_splitter fallback”).

Orchestrator calls compose_unit(zone, frame, template) once per template; no iteration over many layouts, no combinatorial search.

---

## 9. Validation Invariants (Post-Composition Checklist)

After producing the set of room polygons and entry_door_segment, the composer must validate the following. If any fails, raise LayoutCompositionError (and orchestrator triggers next template or UNRESOLVED).

1. **No overlaps:** For every pair of distinct rooms, room_i.polygon.intersection(room_j.polygon).area < tolerance (e.g. 1e-9). No overlap allowed.
2. **All rooms inside zone:** For every room, room.polygon.within(zone.polygon) or equivalent (buffer by small tolerance if needed). No room may extend outside the zone.
3. **All rooms above min area:** For every room, room.area_sqm >= template.room(room_type).min_area_sqm (if min_area_sqm is defined).
4. **Wet wall alignment correct:** TOILET and KITCHEN each have a boundary segment on wet_wall_line (see Section 6). Check by boundary intersection with line (length > tolerance).
5. **Entry on corridor edge:** entry_door_segment is a line segment that lies on the zone’s corridor_edge and inside the LIVING polygon (segment midpoint or both endpoints in LIVING, and on corridor_edge).
6. **Connectivity satisfied:** Every room (other than LIVING) shares boundary with LIVING or corridor_edge (see Section 5).

All checks are deterministic and run once per composition.

---

## 10. Edge Case Behaviour

| Case | Deterministic behaviour |
|------|--------------------------|
| **Narrow bands (4–5 m)** | Zone compatibility uses template.min_width_m and min_depth_m. If band_depth_m or band_length_m < template minima → UnitZoneTooSmallError; orchestrator tries next template (COMPACT, then STUDIO). If all fail → UNRESOLVED. No special 4 m or 5 m constant; only template minima. |
| **Deep narrow zone** | One unit only. Composer fills the zone with one layout. Repetition (separate phase) will set n_units = 1 for such bands. |
| **Band barely larger than template** | Same as any zone: if dimensions meet template minima, composer produces one layout. If not, ZoneTooSmall and fallback. No stretching to use “barely” extra space. |
| **Multi-tower** | Composer is called per zone (or per zone slice). Each call is independent. No cross-tower state or constraint. |

No vague “may try” or “optionally”; each case has a single specified behaviour.

---

## 11. Performance Characteristics

- **Per-zone complexity:** O(1) in the number of rooms (fixed set: at most LIVING, BEDROOM, KITCHEN, TOILET, or LIVING, TOILET for STUDIO). No iteration over multiple candidate layouts.
- **No combinatorial branching:** One deterministic cut sequence per template. No search over room orders or dimensions.
- **No iteration over many layouts:** One layout per (zone, frame, template). Fallback tries at most three templates (STANDARD, COMPACT, STUDIO), each producing at most one layout attempt.

Stated explicitly: Phase 2 does not perform optimization, search, or backtracking over layouts.

---

## 12. Test Matrix (Before Coding)

Implement the following test cases (as specifications; implementation in tests later):

1. **Single-loaded slab:** One zone, corridor_edge and core_edge present; frame has wet_wall_line. Expect one UnitLayoutContract with LIVING, BEDROOM, KITCHEN, TOILET; entry on corridor edge; wet rooms on wet_wall_line.
2. **Double-loaded slab:** Two zones (band_id 0 and 1). Run composer for each zone with same template. Expect two layouts; wet_wall_line from frame differs per band.
3. **End-core slab:** One zone, no corridor; corridor_edge None. Entry edge is frontage_edge. Composer places entry_door_segment on LIVING’s frontage_edge (e.g. centre). Expect valid layout with entry on that edge.
4. **Minimal viable zone:** Zone dimensions equal to template.min_width_m and min_depth_m. Expect success and all rooms at minimum dimensions.
5. **Compact fallback:** Zone too small for STANDARD; dimensions suit COMPACT. Expect orchestrator to try STANDARD (fail), then COMPACT (succeed). Log shows one fallback.
6. **Studio fallback:** Zone too small for COMPACT; dimensions suit STUDIO. Expect STANDARD fail, COMPACT fail, STUDIO succeed.
7. **Failure case:** Zone too small for STUDIO. Expect UnresolvedLayoutError after three attempts. Log shows three failure records.
8. **Connectivity fail:** (If achievable with a deliberately broken cut sequence in a test harness) A room not touching LIVING or corridor. Expect LayoutCompositionError with reason connectivity_fail.
9. **Wet wall misalignment:** (If achievable) TOILET not on wet_wall_line. Expect LayoutCompositionError with reason wet_wall_alignment_fail.
10. **Dimension fail:** Room below min area or min dimension. Expect LayoutCompositionError with reason room_min_dim_fail.

List above is the minimum test matrix; add more as needed for edge cases (e.g. STUDIO-only room set, corridor_edge None handling).

---

## 13. Explicitly Forbidden (Phase 2)

Phase 2 **must never**:

- Use **AI** or machine learning in any form.
- Use **search** or optimization (e.g. try multiple layouts and pick the “best”).
- **Mutate** input geometry (skeleton, zone, frame) or any shared state.
- **Read placement_label** or any skeleton field other than via the frame derived from derive_unit_local_frame.
- **Read strategy engine** data (development_strategy, slab_metrics, strategy generator outputs).
- **Stretch or resize** rooms to consume residual space; room dimensions are template-driven only.
- **Depend on** repetition count, n_units, or module_width.
- **Silently degrade:** every failure must raise an explicit exception and be logged with a structured reason.
- **Use implicit fallback:** fallback order is STANDARD → COMPACT → STUDIO only; no other order or “maybe try X”.

---

## Document Control

- **Version:** 1.0  
- **Source:** Level 2 Residential Layout Engine (Phase 2). Aligned with [level2-residential-layout-engine_866bbf85.plan.md](level2-residential-layout-engine_866bbf85.plan.md) and Phase 1.5 UnitLocalFrame.  
- **Changes:** Any contradiction with deterministic design or introduction of circular dependency must be corrected in this document and in the main plan.
