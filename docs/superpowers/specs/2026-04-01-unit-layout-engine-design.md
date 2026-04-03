# Unit Layout Engine — Design Spec
**Date:** 2026-04-01
**Status:** Approved for implementation

---

## 1. Problem Statement

The existing floor plan pipeline uses text-to-image models (DALL-E, Gemini, Recraft) to produce raster images of floor plans. These are illustrative only — non-deterministic, inaccurate, and not usable for design or construction.

This spec defines a replacement system that generates **precise, GDCR-compliant architectural floor plans** as DXF files (downloadable) and SVG (browser viewer), with proper walls, doors, windows, room labelling, and dimension annotations.

---

## 2. Scope

### V1 Included
- Unit types: 1BHK, 2BHK, 3BHK
- Layout solver: strip decomposition + beam search + grid fallback
- Hard adjacency enforcement with retry/downgrade protocol
- Circulation pre-allocation (entry band + adaptive spine)
- Geometry: planar graph, wall thickness (230mm ext / 115mm int), junction resolution
- Door placement: adjacency-driven, swing drawn
- Window placement: room-type rules, external wall preference, clear span check
- Unit replication: mirror across corridor axis
- Global optimization: wall dedup, wet room clustering, plumbing shafts, dead space
- Post-optimization validation: GDCR area, hard adjacency, overlaps, boundary
- DXF export: 7 layers via ezdxf
- SVG export: labeled rooms, dimension lines, room areas
- Frontend: standalone floor plan viewer panel, floor selector, DXF download button
- Remove all text-to-image calls (DALL-E, Gemini, Recraft) entirely

### V1 Excluded
- Unit rotation (90°/180°) — mirror only
- Multi-wing buildings (L/T/U shapes)
- Balcony geometry (annotated only)
- Furniture layout
- Structural columns
- 3D / IFC export

---

## 3. Pipeline Overview

```
[Stage 1+2] Existing Engine (unchanged)
  plot polygon + road_width_m + GDCR rules
    → BuildingEnvelope { footprint, n_floors, height_m, core_zone,
                         corridor_band, unit_zones[], mirror_axis }

[Stage 2.5] Feasibility Checker
  For each UnitZone: verify area + width + depth fit unit_type
  → downgrade cascade: 3BHK → 2BHK → 1BHK → STUDIO
  → STUDIO zones skip LLM, get single-room layout

[Stage 3] LLM (strict role — semantics only)
  Input: unit_type, external_walls[], corridor_wall, orientation
  Output: UnitLayoutSpec { rooms[], adjacency[], circulation_sequence[] }
  NO dimensions. NO coordinates. NO sizes.
  Result cached by (zone_hash, unit_type).

[Stage 4] Layout Solver (deterministic)
  1. plan_circulation_zones() — reserve entry band + spine BEFORE packing
  2. assess_zone_regularity() → REGULAR | ELONGATED | CORNER | IRREGULAR
  3. Route to: strip_solver (REGULAR/ELONGATED) | corner solver | grid solver
  4. solve_with_beam_search() — beam_width=8, max_candidates=48
  5. enforce_hard_adjacency() — 3 attempts, then downgrade/reject
  Output: UnitLayout { rooms[], score, strategy, plumbing_anchors }

[Stage 5] Geometry Engine
  build_planar_graph() → NodeRegistry + EdgeRegistry (snapped to 5mm grid)
  apply_wall_thickness() → WallSegment[] (230mm ext, 115mm int)
  resolve_all_junctions() → T/L/cross joins resolved
  place_doors() → DoorSpec[] (adjacency-driven, swing clearance checked)
  place_windows() → WindowSpec[] (room-type rules, clear span)

[Stage 6] Replication + Assembly
  mirror_units() across corridor axis (east ↔ west)
  validate_replication() — 1mm tolerance boundary check
  assemble_full_floor() → FullFloorGeometry

[Stage 7] Global Optimization
  - Wall deduplication (coincident shared walls collapsed)
  - Wet room clustering (back-to-back plumbing, max 600mm shift)
  - Plumbing shaft consolidation (600mm min overlap)
  - Dead space conversion (≥1.5 sqm gaps → UTILITY rooms)
  - External wall fenestration symmetry enforcement
  → validate_after_global_opt() — if errors: conservative re-opt, then rollback

[Stage 8] DXF Export (ezdxf)
  Layers: WALL_EXT, WALL_INT, DOOR, WINDOW, ROOM_LABEL, DIMENSION, HATCH

[Stage 9] SVG Export
  Labeled rooms, dimension lines, room areas, north arrow

[Stage 10] Frontend Viewer
  Standalone panel (not Leaflet canvas)
  Floor selector (floor 1 → N)
  DXF download button
```

---

## 4. GDCR Constraints

### Minimum Room Areas (sqm)
```
LIVING:          9.5    BEDROOM_MASTER: 9.5
BEDROOM:         7.5    KITCHEN:        5.5
BATHROOM:        2.25   TOILET:         1.10
FOYER:           2.00   BALCONY:        1.50
```

### Unit Room Manifests
```
1BHK: LIVING, BEDROOM_MASTER, KITCHEN, BATHROOM, FOYER
2BHK: LIVING, BEDROOM_MASTER, BEDROOM, KITCHEN, BATHROOM, TOILET, FOYER
3BHK: LIVING, BEDROOM_MASTER, BEDROOM×2, KITCHEN, BATHROOM, TOILET, FOYER
```

### Minimum Zone Dimensions (metres)
```
          Width   Depth
1BHK:     4.5     6.0
2BHK:     6.0     7.5
3BHK:     8.0     8.5
```

---

## 5. Layout Solver Detail

### Adjacency Constraints
```
HARD (must share wall edge — HardAdjacencyFailure if unresolvable):
  FOYER ↔ LIVING
  LIVING ↔ KITCHEN
  BATHROOM ↔ BEDROOM_MASTER  (ensuite)

SOFT (scored, not enforced):
  LIVING ↔ BALCONY     weight=0.20
  KITCHEN ↔ UTILITY    weight=0.10
  BEDROOM ↔ TOILET     weight=0.15
```

### Strip Assignment
```
Strip 0 (corridor wall):  FOYER
Strip 1 (primary ext):    LIVING, BEDROOM_MASTER
Strip 2 (internal):       KITCHEN, BATHROOM, TOILET
Strip 3 (secondary ext):  BEDROOM (2BHK/3BHK only)
```

### Strip Depths
```
Strip 0: fixed 1.80m
Strip 2: fixed 2.50m
Strips 1+3: remaining depth split proportionally
  2BHK: 55% strip 1 / 45% strip 3
  3BHK: 50% / 50%
```

### Beam Search
- beam_width=8, max_candidates=48
- Fully deterministic: priority sort + stable alphabetical tie-break
- Prune: hard adjacency violations, GDCR violations, aspect ratio > 2.5
- On empty beam: widen to beam_width=24, then fallback to grid solver

### Hard Adjacency Retry Protocol
```
Attempt 1: slide rb within strip to touch ra
Attempt 2: slide ra within strip to touch rb
Attempt 3: cross-strip x-range alignment
→ All fail: HardAdjacencyFailure
  → downgrade unit type
  → retry with beam_width=24
  → retry with grid solver
  → all fail: FailedUnitLayout (render as HATCHED_VOID)
```

### Grid Fallback
```
GRID resolution = clamp(sqrt(area/1600), 0.20, 1.00) rounded to 0.05m
Hard cap: max 80×80 cells (bump resolution if exceeded)
Containment: vectorized numpy + shapely.contains batch
```

### Scoring Function (weights)
```
adjacency satisfaction:    0.35
aspect ratio quality:      0.20
external wall utilization: 0.20
circulation efficiency:    0.15
dead space penalty:        0.10
```

---

## 6. Geometry Engine Detail

### Coordinate System
- All coordinates in metres, origin at zone bottom-left
- Snap grid: 5mm (0.005m)
- Epsilon for merge: 1mm (0.001m)

### Wall Thickness
```
WALL_EXT:      230mm (outward offset from room edge)
WALL_INT:      115mm (57.5mm each side of shared edge)
WALL_CORRIDOR: 230mm
```

### Junction Types
```
END:    1 incident edge — plain end cap
CORNER: 2 non-collinear — corner block filled
T:      3 edges — stub extended to continuous wall face
CROSS:  4 edges — center block filled at max thickness
```

### Window Rules
```
Room            min_wall  width  sill  head  corner_offset  ext_required
BEDROOM_MASTER  2.40m     1.50m  0.75  2.10  0.45m          yes
BEDROOM         2.00m     1.20m  0.75  2.10  0.45m          yes
LIVING          3.00m     1.80m  0.60  2.10  0.45m          yes
KITCHEN         1.50m     0.90m  1.05  2.00  0.30m          no
BATHROOM        1.20m     0.60m  1.50  2.00  0.20m          no
TOILET          1.00m     0.45m  1.50  2.00  0.15m          no
```

---

## 7. Failure Handling

```
Failure                          Handler                    User output
────────────────────────────────────────────────────────────────────────────────
Zone area too small              Downgrade cascade          Badge: "Unit simplified"
LLM parse error                  Retry once → default spec  Transparent
LLM timeout                      Cached spec → default spec Badge: "Offline layout"
Hard adjacency unresolvable      Downgrade → grid → FAIL    Hatched void + message
Beam search exhausted            Widen → grid fallback      Transparent if recovers
Post-opt GDCR violation          Conservative re-opt        Transparent if recovers
Post-opt still failing           Rollback + report in DXF   Note in DXF annotation
DXF write error                  HTTP 500                   "Export failed, retry"
SVG render error                 Outline-only fallback      Minimal plan shown
```

`FailedUnitLayout` propagates cleanly — DXF/SVG renders crosshatch at zone bounds.

---

## 8. Codebase Structure

```
backend/unit_layout_engine/
├── engine.py                    # generate_unit_floor_plan() entry point
├── models/
│   ├── zone.py                  # UnitZone, ZoneClass
│   ├── rooms.py                 # RoomSpec, PlacedRoom, RoomType
│   ├── layout.py                # UnitLayout, FailedUnitLayout, UnitLayoutSpec
│   ├── geometry.py              # WallSegment, DoorSpec, WindowSpec
│   └── floor.py                 # FullFloorGeometry, PlumbingShaft, ValidationReport
├── feasibility/
│   └── checker.py               # check_feasibility(), downgrade_unit_type()
├── llm/
│   ├── client.py                # call_llm() wrapper
│   ├── prompt.py                # build_unit_prompt()
│   ├── parser.py                # parse_llm_response() → UnitLayoutSpec
│   └── cache.py                 # LLMCache keyed by (zone_hash, unit_type)
├── solver/
│   ├── circulation.py           # plan_circulation_zones()
│   ├── strip_solver.py          # solve_strip(), pack_strip()
│   ├── beam_search.py           # solve_with_beam_search(), capped_permutations()
│   ├── grid_solver.py           # solve_irregular_zone(), adaptive_grid_resolution()
│   ├── adjacency.py             # enforce_hard_adjacency(), compute_soft_penalty()
│   ├── scoring.py               # score_layout()
│   └── dispatcher.py            # solve_unit() — routes to correct solver
├── geometry/
│   ├── registry.py              # NodeRegistry, EdgeRegistry (snapped)
│   ├── wall_builder.py          # build_planar_graph(), apply_wall_thickness()
│   ├── junction_resolver.py     # resolve_all_junctions()
│   ├── door_placer.py           # place_doors()
│   └── window_placer.py         # place_windows(), WINDOW_RULES
├── replication/
│   ├── mirror.py                # mirror_unit(), mirror_windows()
│   ├── symmetry.py              # validate_replication()
│   └── assembler.py             # assemble_full_floor()
├── optimization/
│   ├── global_optimizer.py      # global_optimize()
│   └── post_validator.py        # validate_after_global_opt()
└── export/
    ├── dxf_writer.py            # write_dxf() → bytes
    └── svg_writer.py            # write_svg() → str
```

### Files Removed
- `services/ai_floor_plan_service.py` → replaced by `unit_layout_engine/engine.py`
- `services/floor_plan_image_prompt.py` → deleted
- `services/ai_floor_plan_validator.py` → absorbed into `feasibility/checker.py`
- `services/ai_to_geojson_converter.py` → replaced by `geometry/wall_builder.py`
- `services/svg_blueprint_renderer.py` → replaced by `export/svg_writer.py`

---

## 9. Data Models (Pydantic)

```python
# UnitZone
id: str; x,y,w,d: float          # metres
unit_type: str                    # "1BHK"|"2BHK"|"3BHK"|"STUDIO"
external_walls: list[str]         # ["south","east"]
corridor_wall: str
orientation: float                # degrees CCW from north
zone_class: ZoneClass             # REGULAR|ELONGATED|CORNER|IRREGULAR

# RoomSpec (LLM output)
id: str; type: RoomType
preferred_wall: str               # "south"|"north"|"east"|"west"|"any"
priority: int                     # 3=high, 1=low
requires_window: bool
requires_ventilation: bool

# PlacedRoom (solver output)
id,type: str; x,y,w,d: float
external_walls: list[str]
area_sqm: float

# UnitLayoutSpec (LLM output)
unit_type: str
rooms: list[RoomSpec]
adjacency: list[tuple[str,str]]
circulation_sequence: list[str]

# UnitLayout (solver output)
zone: UnitZone
rooms: dict[str, PlacedRoom]
score: float
strategy: str                     # "STRIP"|"GRID"|"CORNER"
adjacency_violations: list[tuple] # soft only
plumbing_anchors: dict[str, tuple[float,float,float,float]]

# WallSegment
id: str; p1,p2: tuple[float,float]
thickness_m: float; length_m: float
layer: WallLayer                  # WALL_EXT|WALL_INT|WALL_CORRIDOR
junction_start,junction_end: str  # END|CORNER|T|CROSS

# DoorSpec
id,wall_id: str; offset_m,width_m: float
swing: str; angle_deg: float
room_a,room_b: str

# WindowSpec
id,wall_id,room_id: str
offset_m,width_m,sill_height,head_height: float

# FullFloorGeometry
floor_level: int
units: list[UnitLayout | FailedUnitLayout]
corridor,core: dict              # GeoJSON from existing engine
walls: list[WallSegment]
doors: list[DoorSpec]
windows: list[WindowSpec]
plumbing_shafts: list[PlumbingShaft]
validation_report: ValidationReport | None
global_opt_log: list[str]
```

---

## 10. Testing Strategy

### Unit Tests
- `test_feasibility`: area/width/depth thresholds, downgrade cascade
- `test_strip_solver`: rooms within zone bounds, GDCR min areas, no overlaps
- `test_beam_search`: deterministic output (run twice, assert equal), prune hard violations
- `test_hard_adjacency`: all HARD pairs share edges, retry/downgrade protocol
- `test_grid_solver`: adaptive resolution, vectorized containment, room placement
- `test_node_registry`: snap merging, epsilon merge, no duplicate nodes
- `test_wall_builder`: no duplicate walls, correct thickness, layer classification
- `test_junction_resolver`: T/L/cross joins produce no gap or overlap at node
- `test_window_placer`: external wall only (where required), corner offset respected
- `test_post_validator`: catches overlap, boundary violation, GDCR violation

### Integration Tests
- Full pipeline: plot → DXF bytes + SVG string (no exception)
- FailedUnitLayout propagates: DXF renders hatched void, no crash
- Mirror symmetry: mirrored unit rooms are geometrically reflected
- Plumbing shafts: wet rooms back-to-back within 600mm after global opt

---

## 11. API Changes

### New endpoint
`POST /api/floor-plan/generate/`
```json
Request:  { "plot_id": "fp133", "floor_level": 1 }
Response: {
  "svg": "<svg>...</svg>",
  "dxf_url": "/api/floor-plan/fp133/1/download.dxf",
  "validation": { "errors": [], "warnings": [] },
  "units": [{ "id": "...", "type": "2BHK", "score": 0.87 }]
}
```

### Removed endpoints
- `/api/ai-floor-plan/generate/` (DALL-E pipeline) — removed

### Frontend changes
- `DirectFloorPlanView.tsx` → replaced by `StandaloneFloorPlanViewer.tsx`
- `ZoomableImageViewer.tsx` — no longer used for floor plans
- Add floor selector (1 → N floors)
- Add DXF download button
