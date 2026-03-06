# Architecture AI — Backend Audit Before Phase 1.5 (UnitLocalFrame) and Phase 2 (UnitComposer)

**Scope:** Code-only inventory and gap audit. No implementation. No speculation.

**Code bases:** `backend/floor_skeleton/*`, `backend/presentation_engine/*`, `backend/development_strategy/*`, `backend/architecture/*`, `backend/placement_engine/*`, `backend/envelope_engine/*`, `backend/placement_engine/geometry/core_fit.py`. No `backend/core_fit/` module exists. No `backend/residential_layout/` module exists.

---

## PART 1 — Current Geometry Contracts

### 1.1 What FloorSkeleton exposes

**File:** `backend/floor_skeleton/models.py`

**Attributes (all):**

| Attribute | Type | Source |
|-----------|------|--------|
| `footprint_polygon` | `Polygon` | Builder: `shapely_box(0, 0, W, D)` |
| `core_polygon` | `Polygon` | From `CoreCandidate.core_box` |
| `corridor_polygon` | `Optional[Polygon]` | Builder; `None` for END_CORE |
| `unit_zones` | `list[UnitZone]` | Builder |
| `pattern_used` | `str` | DOUBLE_LOADED / SINGLE_LOADED / END_CORE / NO_SKELETON |
| `placement_label` | `str` | From `CoreCandidate.label` (one of `LABEL_*`) |
| `area_summary` | `dict` | Populated by `skeleton_evaluator.compute_area_summary()` |
| `efficiency_ratio` | `float` | Set in evaluator |
| `is_geometry_valid` | `bool` | Set in evaluator |
| `passes_min_unit_guard` | `bool` | Set in evaluator |
| `is_architecturally_viable` | `bool` | Set in evaluator |
| `audit_log` | `list[dict]` | Set in `floor_skeleton/services.py` after evaluation |

**Metadata:**

- **orientation_axis:** Not on `FloorSkeleton`. It exists only on each `UnitZone` (`UnitZone.orientation_axis`).
- **pattern_used:** On `FloorSkeleton`; set in builder per pattern.
- **placement_label:** On `FloorSkeleton`; comes from `CoreCandidate.label`.
- **Core/corridor relationships:** No explicit relationship object. Relationship is implicit: builder creates `core_polygon`, `corridor_polygon`, and `unit_zones` in the same local frame; adjacency is by shared boundaries (used in `wall_builder._extract_partition_lines` via polygon boundary intersection).

**Explicit tagging:**

- **Frontage edge:** Does NOT exist. No attribute or constant for “frontage edge” or “road-facing edge” on skeleton or unit zones.
- **Core-facing edge:** Does NOT exist. No tagging of which edge of a unit zone touches the core.
- **Corridor-facing edge:** Does NOT exist. No tagging of which edge faces the corridor.

**Inference today:** `room_splitter` infers “core-adjacent” side for toilet placement using only `skeleton.placement_label`: if `placement_label != LABEL_END_CORE_RIGHT` then toilet at min-x of zone; else toilet at max-x. It uses `uz.polygon.bounds` (minx, miny, maxx, maxy) to build boxes. So “core-facing” is inferred from placement label + bounds, not from a tagged edge.

---

### 1.2 UnitZone

**File:** `backend/floor_skeleton/models.py`

**Geometry stored:**

- `polygon`: Shapely `Polygon` in local metres (axis-aligned rectangle in POC v1).

**Dimensional metadata:**

- `zone_width_m`: float (explicit).
- `zone_depth_m`: float (explicit).
- Docstring: “zone_width_m = dimension along X, zone_depth_m = dimension along Y” for current builder; “explicit fields allow future non-rectangular zones.”

**Semantic adjacency:**

- None. No field or structure for “adjacent to core,” “adjacent to corridor,” or “adjacent to zone j.”

**Orientation:**

- `orientation_axis`: `str` — `AXIS_WIDTH_DOMINANT` or `AXIS_DEPTH_DOMINANT` (constants in `floor_skeleton/models.py`).
- Meaning (docstring): WIDTH_DOMINANT = long axis along X (horizontal core); DEPTH_DOMINANT = long axis along Y (vertical core).

---

### 1.3 Where WIDTH_DOMINANT vs DEPTH_DOMINANT is used

| File | Usage |
|------|--------|
| `floor_skeleton/models.py` | Constants defined; `UnitZone.orientation_axis` type. |
| `floor_skeleton/skeleton_builder.py` | Every `UnitZone` is constructed with explicit `orientation_axis`. Vertical-core patterns use `AXIS_DEPTH_DOMINANT`; horizontal END_CORE uses `AXIS_WIDTH_DOMINANT`. |
| `floor_skeleton/skeleton_evaluator.py` | `check_min_unit_guard()`: if `DEPTH_DOMINANT` then short side = `zone_width_m`, long side = `zone_depth_m` (min_unit_width_m / min_unit_depth_m); if `WIDTH_DOMINANT` then short side = `zone_depth_m`, no long-side depth check for END_CORE. |
| `development_strategy/slab_metrics.py` | Reads `uz.orientation_axis` into `band_orientation_axes` list. |
| `development_strategy/strategy_generator.py` | `_repeat_and_depth_for_band()`: if axis == WIDTH_DOMINANT then repeat_len = width, depth = length; else swap. |
| `development_strategy/mixed_generator.py` | Same `_repeat_and_depth_for_band()` convention; passes `orientation_axis` into `BandCombination`. |
| `architecture/tests/test_development_strategy.py`, `test_mixed_strategy.py` | Construct mock skeletons with explicit `orientation_axis`. |

**Multiple code paths by pattern:** Yes. In `skeleton_builder.py`, pattern and `candidate.is_horizontal` select builder: `_build_double_loaded`, `_build_single_loaded`, `_build_vertical_end_core`, `_build_horizontal_end_core`. Orientation is set inside each path (always DEPTH_DOMINANT for vertical; WIDTH_DOMINANT for horizontal).

**Centralized vs scattered:** Orientation semantics are documented in one place (`models.py`) and applied in builder and evaluator; repetition convention is duplicated in `strategy_generator._repeat_and_depth_for_band` and `mixed_generator._repeat_and_depth_for_band` (same logic, same convention).

---

## PART 2 — Core & Wet Wall Information

### 2.1 CoreValidationResult geometric data

**File:** `backend/placement_engine/geometry/core_fit.py`

**Fields:** `core_fit_status`, `selected_pattern`, `core_area_estimate_sqm`, `remaining_usable_sqm`, `lift_required`, `n_staircases_required`, `core_pkg_width_m`, `core_pkg_depth_m`, `audit_log`. No polygon, no edge list, no geometry. Pure dimensional result.

**Deterministic “which core edge touches which UnitZone”:** Not available from `CoreValidationResult`. That relationship is only implied by how `skeleton_builder` builds geometry (same W, D, cpw, cpd, pattern): core box and unit boxes are positioned in the same local frame, so adjacency is geometric (shared boundary) only. No explicit “core edge i touches zone j.”

### 2.2 DOUBLE_LOADED: UnitZones and position relative to core

**File:** `backend/floor_skeleton/skeleton_builder.py`, `_build_double_loaded()`

- Two `UnitZone`s created: `unit_a` (y=0 to y0), `unit_b` (y=y1 to D). Corridor at y0..y1. Core is a vertical strip (same as other vertical patterns); unit zones are on the same X interval (nc_x0..nc_x1) on both sides of the corridor.
- Which side of the core each band lies on: not stored. It is fixed by builder logic (e.g. unit_a is “below” corridor, unit_b “above”); there is no “band_index” or “side_of_core” on `UnitZone`. Order in `unit_zones` is deterministic (A then B).

### 2.3 Shaft / wet wall abstraction

- **Shaft or wet wall abstraction:** Does NOT exist in code. No dataclass, no module, no “wet wall” or “shaft” type.
- **Geometry that would be needed:** Would require at least a polygon or segment (e.g. line or strip) in the same local frame plus a label (e.g. “wet” / “shaft”); not present.

---

## PART 3 — Repetition Feasibility

### 3.1 Per UnitZone: band direction, depth direction, band length

- **Band direction:** Not stored on `UnitZone`. Derived only at slab level: `SlabMetrics.band_widths_m[i]`, `band_lengths_m[i]`, `band_orientation_axes[i]` (from `skeleton.unit_zones` and `area_summary`). Strategy/mixed generators use `_repeat_and_depth_for_band(slab, i)` so that for band i, repeat_len and depth_avail come from (width, length) swapped or not by axis.
- **Depth direction:** Same: implied by orientation_axis (DEPTH_DOMINANT ⇒ depth along Y; WIDTH_DOMINANT ⇒ depth along the other axis). Not stored as a “direction vector” on the zone.
- **Band length (repeat length):** Not on `UnitZone`. Available only as `SlabMetrics.band_widths_m[i]` or `band_lengths_m[i]` after interpretation by axis: in `strategy_generator` and `mixed_generator`, `repeat_len_m` = width or length depending on `band_orientation_axes[i]`.

### 3.2 Band origin and local coordinate frame

- **Band origin corner:** Does NOT exist. No “origin” or “first unit corner” on `UnitZone` or `FloorSkeleton`.
- **Consistent local coordinate frame per band:** Not present. The only frame is the footprint frame (0,0)→(W,D) in metres. Unit zones are boxes in that frame; no per-zone or per-band origin or axes.

### 3.3 Constraints (no overlap, containment, corridor width)

- **No overlap / containment:** Enforced in `skeleton_evaluator.check_geometry()`: area partition check (`core + corridor + unit_area ≈ footprint_area`), `unary_union(zone_polys).area` vs footprint area, and each `unit_zone.polygon.within(footprint.buffer(tol))`.
- **Corridor width:** Preserved by builder: corridor is built with fixed `dims.corridor_m` in `_build_single_loaded` and `_build_double_loaded`; no separate “constraint check” after build.

---

## PART 4 — Presentation Contract

### 4.1 What presentation_engine expects as input

- **Entry point:** `presentation_engine/drawing_composer.py`: `compose(skeleton, *, tp_num, fp_num, height_m)`.
- **Required:** `skeleton` is a `FloorSkeleton` (type hint in `compose()`). No other required input for geometry; tp_num, fp_num, height_m are optional for annotations.

### 4.2 PresentationModel required fields

**File:** `backend/presentation_engine/models.py`

- `skeleton`: `FloorSkeleton` (reference).
- `external_walls`: `list[WallGeometry]`.
- `core_walls`: `list[WallGeometry]`.
- `partition_lines`: `list[list[tuple[float, float]]]`.
- `rooms`: `list[RoomGeometry]`.
- `doors`: `list[DoorSymbol]`.
- `title_block`: `AnnotationBlock`.
- `room_labels`: `list[AnnotationBlock]`.
- `used_fallback_walls`, `used_fallback_rooms`, `used_fallback_doors`: bool.

All are required (no optional in the dataclass).

### 4.3 Minimal data to render walls, rooms, doors

- **Walls:** `wall_builder.build(skeleton)` uses `skeleton.footprint_polygon`, `skeleton.core_polygon`, `skeleton.corridor_polygon`, `skeleton.unit_zones` (polygons only). Partition lines from `_extract_partition_lines(skeleton)` (shared boundaries between core, corridor, unit_zones).
- **Rooms:** `room_splitter.split(skeleton)` uses `skeleton.unit_zones`, `skeleton.placement_label`; produces `list[RoomGeometry]` (polygon + label + area_sqm).
- **Doors:** `door_placer.place(skeleton, rooms)` uses `skeleton.core_polygon`, `skeleton.corridor_polygon`, and `rooms` (polygons); finds shared boundaries and places symbols. No skeleton fields beyond core/corridor polygons and the rooms list.

### 4.4 Coupling to skeleton structure

- Presentation is tightly coupled to `FloorSkeleton`: it expects `footprint_polygon`, `core_polygon`, `corridor_polygon`, `unit_zones` (each with `polygon`, and room_splitter uses `zone_width_m` and `placement_label`). It does not consume a separate “UnitLayoutContract” type; there is no such type in code.

### 4.5 Replacing room_splitter with UnitComposer

- **What would break:**
  - `drawing_composer.compose()` calls `room_splitter.split(skeleton)` and `room_splitter.split_fallback(skeleton)`. Replacing that with a UnitComposer would require the new function to return `list[RoomGeometry]` (same type) to keep `compose()` and downstream unchanged.
  - `door_placer.place(skeleton, rooms)` expects `rooms` to be a list of `RoomGeometry` with `.polygon` and `.label`; it also relies on labels "TOILET" and "ROOM" for intra-unit doors.
  - `annotation_builder.build(skeleton, rooms, ...)` expects `rooms` and uses room centroids for labels.
- **Functions that depend on room_splitter output:** `drawing_composer.compose()` (rooms), `door_placer.place(skeleton, rooms)`, `annotation_builder.build(skeleton, rooms, ...)`. So: composer, door_placer, annotation_builder all depend on the current room list shape and labels. If UnitComposer produced a different structure (e.g. different labels or extra metadata), only the return type `list[RoomGeometry]` is the current contract; any new fields would need to be either optional on `RoomGeometry` or a new contract type that presentation can accept.

---

## PART 5 — Development Strategy Coupling

### 5.1 Room-level vs slab-level

- **development_strategy** does not use room-level geometry. It uses only:
  - `SlabMetrics` from `compute_slab_metrics(skeleton)` in `development_strategy/slab_metrics.py`, which reads `skeleton.area_summary` and `skeleton.unit_zones` (zone_width_m, zone_depth_m, orientation_axis).
  - No `RoomGeometry`, no room polygons, no room_splitter.

### 5.2 Effect of UnitComposer on strategy scoring

- Strategy and mixed strategy use `SlabMetrics` (band_widths_m, band_lengths_m, band_orientation_axes, net_usable_area_sqm, etc.). UnitComposer would produce room-level layout inside unit zones; that output is not consumed by `development_strategy` in current code. So strategy scoring would be unaffected unless (a) strategy layer were later changed to consume room-level data, or (b) skeleton/unit zones were changed in a way that changes `area_summary` or `unit_zones` (e.g. if UnitComposer replaced unit zones with subdivided polygons and that replaced `skeleton.unit_zones`).

---

## PART 6 — Missing Abstractions

### 6.1 UnitLocalFrame

- **Exists?** No. There is no dataclass or type named “UnitLocalFrame” or “local frame” for a unit/band. No origin point, no axis vectors, no “frontage edge index” or “core-facing edge index” on UnitZone or elsewhere.

**Partial equivalents:**

- `UnitZone.orientation_axis` plus `zone_width_m` / `zone_depth_m` give axis semantics and dimensions.
- Repetition direction is derived in strategy/mixed code from `band_orientation_axes[i]` and band_widths_m / band_lengths_m, not from a first-class “frame” object.

### 6.2 Assumptions that would be affected

- **Introducing a local frame:** Code that currently uses `uz.polygon.bounds` (room_splitter, and implicitly strategy via area_summary) assumes global footprint frame. A local frame would require either (1) storing origin + axes on each zone and converting when needed, or (2) defining “band origin” and “repeat axis” in a way that does not change existing polygon coordinates. Current code does not assume a per-zone origin.
- **Introducing module_width_m logic:** Strategy and mixed generator use `unit_frontage_m` and `unit_depth_m` from templates and `repeat_len_m // unit_frontage_m`; there is no “module_width_m” constant. Adding it would touch `strategy_generator` and `mixed_generator` (tiling step); slab_metrics and skeleton itself do not reference module width.

### 6.3 Circular dependencies

- **Strategy ↔ Skeleton:** Strategy (and mixed) depend on skeleton (via SlabMetrics from skeleton). Skeleton does not depend on strategy. No cycle.
- **Skeleton ↔ Presentation:** Presentation depends on skeleton. Skeleton does not depend on presentation. No cycle.
- **Strategy ↔ Presentation:** No direct dependency. Strategy does not import presentation; presentation does not import strategy. No cycle.
- **Future layout layer:** Not present. If a layout layer sat between skeleton and presentation and consumed skeleton and produced something presentation could consume, the dependency would be skeleton → layout → presentation; strategy could remain skeleton-only unless explicitly wired to layout.

---

## PART 7 — Readiness Assessment

### 7.1 Geometry readiness for Phase 1.5 (0–10)

- **Score: 5**
- **Reasons:** Orientation and band dimensions exist (UnitZone.orientation_axis, zone_width_m, zone_depth_m; area_summary.unit_band_widths/depths; band_orientation_axes). No origin, no edge tagging (frontage/core-facing/corridor-facing), no per-band local frame, no wet wall/shaft. Core–zone adjacency is implicit (geometry only). Phase 1.5 (UnitLocalFrame) would add new concepts; existing data is enough to derive a frame convention but not stored as a first-class abstraction.

### 7.2 Risk level for Phase 2 slicing (Low/Medium/High)

- **Medium.** Room_splitter is a single, simple code path; replacing it with UnitComposer is feasible if the output remains `list[RoomGeometry]`. Risk: (1) UnitComposer may need band origin / repeat direction / core-facing edge — none of these exist today; (2) door_placer and annotation_builder assume current room labels and polygon structure; (3) any change to UnitZone semantics (e.g. subdivision of zones by composer) must not break slab_metrics and strategy, which assume one polygon per band and current area_summary semantics.

### 7.3 Immediate blockers

- No hard blocker. For Phase 1.5 the main gaps are: no UnitLocalFrame, no edge tagging, no band origin. For Phase 2: no wet wall/shaft abstraction; no explicit “core-facing” or “corridor-facing” edge on UnitZone; room_splitter’s core-adjacent logic is placement_label + bounds, which may not generalize to all patterns or multi-band layouts.

### 7.4 Recommended order of implementation

1. **Phase 1.5:** Define UnitLocalFrame (and optionally band origin / repeat axis) from existing skeleton + orientation; add to UnitZone or a parallel structure without breaking existing consumers (slab_metrics, strategy, presentation). Optionally add edge tagging (e.g. core-facing edge index or segment) for layout and presentation.
2. **Phase 2:** Implement UnitComposer that consumes skeleton (+ UnitLocalFrame if added) and produces `list[RoomGeometry]` (or a contract presentation can accept). Then swap composer in for room_splitter in drawing_composer; keep or extend door_placer and annotation_builder to work with new labels/structure if needed. Introduce wet wall/shaft only if required by composer or compliance.

### 7.5 Hidden coupling risks

- **room_splitter ↔ placement_label:** Toilet placement is tied to `LABEL_END_CORE_RIGHT` vs others. Any new placement labels or multi-tower skeletons would need a clear rule for “core-adjacent” or the concept moved to a tagged edge.
- **area_summary.unit_band_widths / unit_band_depths:** Populated from `unit_zones` in order. Strategy and mixed assume band index i corresponds to `unit_zones[i]` and that band_widths_m[i] and band_lengths_m[i] match zone_width_m/zone_depth_m after axis swap. Any reordering or splitting of unit zones could break that alignment unless slab_metrics and strategy are updated.
- **Presentation expects exactly the current FloorSkeleton shape:** footprint_polygon, core_polygon, corridor_polygon, unit_zones. Adding fields to FloorSkeleton or UnitZone is safe if optional or backward compatible; changing or removing fields would require coordinated changes in wall_builder, room_splitter, door_placer, annotation_builder.

---

**End of audit.** All statements above are tied to the listed files and functions; where something is absent, it is stated explicitly.
