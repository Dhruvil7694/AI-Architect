# Step 1 — Current Planning Implementation Analysis

## 1. How the envelope is computed

**Entry**: `envelope_engine.services.envelope_service.compute_envelope(plot_wkt, building_height, road_width, road_facing_edges, enforce_gc=True, cop_strategy="edge")`.

**Steps**:
1. **Parse** plot WKT → Shapely polygon (DXF feet).
2. **Edge classification** (`edge_classifier.classify_edges`): each exterior edge is ROAD, SIDE, or REAR (REAR = non-road edge most parallel to first road edge).
3. **Margin resolution** (`margin_resolver.resolve_margins`): ROAD → Table 6.24 (max(road_width_lookup, H/5, min_road_side_margin)); SIDE/REAR → Table 6.26 height-band. Margins stored in metres and DXF on each EdgeSpec.
4. **Envelope build** (`envelope_builder.build_envelope`): per-edge half-plane intersection (offset each edge inward by required_margin_dxf, intersect keep half-planes with plot) → **margin_polygon** (setback polygon).
5. **Ground coverage** (`coverage_enforcer.enforce_ground_coverage`): clip margin polygon to GDCR max GC % (e.g. 40%) → **gc_polygon**.
6. **COP carve** (`common_plot_carver.carve_common_plot`): carve 10% (or max(10%, 200 sqm)) from plot using EDGE (rear strip) or CENTER (centred rectangle) → **common_plot_polygon**.
7. **Final envelope**: gc_polygon minus (COP + COP height-based margin band) → **envelope_polygon**.

So: **envelope** = inside all setbacks, under GC cap, with COP and COP margin removed. All geometry Shapely, DXF feet.

---

## 2. How COP is generated

**Two paths**:

- **Inside envelope_engine**: `common_plot_carver.carve_common_plot(plot_polygon, gc_polygon, edge_specs, cop_strategy)` — used by `compute_envelope`. EDGE = rear-strip bisection to meet required area; CENTER = axis-aligned rectangle at plot centroid, scaled to meet area and min width/depth from GDCR.
- **Standalone**: `envelope_engine.geometry.common_plot_generator.generate_common_plot(plot_polygon, envelope_polygon, required_area_sqft, ...)` — not currently called by the pipeline. It takes **available = plot.difference(envelope)**, then tries to place a rectangle (area ≥ required, min dimension ≥ 7.5 m) in each connected component’s centroid. Picks largest valid rectangle. No explicit “near road” or “touch internal road” logic; no validation that COP is inside plot or doesn’t overlap setbacks (relies on available = plot − envelope).

**Weaknesses**: COP can be oversized (generator aims for “≥ required” and picks largest); placement is centroid-based, not road- or road-access-oriented; no guarantee COP touches internal road; no explicit check that COP ⊂ plot or COP ∩ setbacks = ∅.

---

## 3. How internal roads are generated

**Module**: `architecture.engines.road_network_engine`.

**Flow** (`generate_internal_road_network`):
1. **Entry**: midpoint of first road-facing edge (or longest edge if none given).
2. **Spine**: line from entry inward along edge inward normal, length = spine_length_ratio × plot depth extent; clipped to plot.
3. **COP connection**: if COP polygon given, append LineString from spine end to COP centroid, clipped to plot. Connection is **optional** (only if COP present).
4. **Width**: 6 m default; `road_network_corridor_polygons(centrelines, width_dxf)` buffers each centreline by width/2 to produce corridor polygons.

**Weaknesses**: No explicit “road entry detection” (relies on caller’s road_facing_edge_indices); COP connection is optional, so COP can be unreachable by road; no tower access nodes along spine; no validation that roads stay inside plot or don’t cross setbacks; corridor polygons are returned but not validated.

---

## 4. How tower placement works

**Entry**: `placement_engine.services.placement_service.compute_placement(envelope_wkt, building_height_m, n_towers, min_width_m=5, min_depth_m=4)`.

**Flow**:
1. Parse envelope WKT → Shapely polygon.
2. **Orientation** from envelope MBR (`orientation_finder`).
3. **Packing** (`packer.pack_towers`): two strategies — ROW_WISE (dual orientation per step) and COL_WISE (force perpendicular). Each iteration: find best inscribed rectangle in remaining polygon (`find_best_in_components`), add **H/3 exclusion zone** around it (`spacing_enforcer.compute_exclusion_zone`), subtract from envelope, repeat. Winner = more towers, then larger total area, then ROW_WISE.
4. **Spacing audit**: pairwise gap check; **core fit** per tower (lift/core compliance).

**Weaknesses**: Placement is on a single polygon (the envelope after road subtraction); no explicit “zones” — one contiguous envelope, so no prioritisation of better zones; no check that tower entry is reachable from road network; no max_tower_width / max_tower_depth; road corridor boundaries are only respected indirectly (envelope already has corridors subtracted).

---

## 5. Where geometry is converted to GeoJSON

- **plan_job_service._build_envelope_plan_result**:
  - `plot_boundary` = `json.loads(geom.geojson)` (GeoDjango).
  - `envelope_geo` = `geometry_to_geojson(final_envelope)` or `wkt_to_geojson(final_envelope.wkt)`.
  - `cop_geo`, `margin_geo` = `wkt_to_geojson(env.common_plot_polygon.wkt)` etc.
  - `internal_roads_geojson` = list of `geometry_to_geojson(ls)` for each centreline.
  - Tower footprints = `wkt_to_geojson(fp.footprint_polygon.wkt)`; spacing lines built as dicts `{ type: "LineString", coordinates: [...] }`.
- **utils.geometry_geojson**: `wkt_to_geojson(wkt_string)` (Shapely load + mapping), `geometry_to_geojson(geom)` (Shapely mapping).

No geometry validation is applied before these conversions.

---

## Weaknesses summary

| Area | Weakness |
|------|----------|
| **COP placement** | Can be oversized; not explicitly “near road”; not forced to touch internal road; no explicit “inside plot” or “no overlap setbacks” checks. |
| **Road access** | COP connection to road is optional; no tower access nodes; no validation that roads are inside plot / don’t cross setbacks. |
| **Tower placement** | Single envelope, no zone splitting or ranking; no reachability from road; no max tower dimensions. |
| **Geometry validation** | No polygon validity, self-intersection, or min width/area checks before API return. |

---

## Architecture diagram (current)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PlanJob worker / development_pipeline                                       │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  detect_road_edges_with_meta(plot) → road_facing_edge_indices                │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  envelope_engine.compute_envelope(plot_wkt, height, road_width, road_edges)  │
│    → EdgeClassifier → MarginResolver → build_envelope → margin_polygon      │
│    → enforce_ground_coverage → gc_polygon                                    │
│    → carve_common_plot → common_plot_polygon                                 │
│    → envelope_polygon = gc_polygon − (COP + COP margin)                      │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  road_network_engine.generate_internal_road_network(plot, envelope, cop,      │
│      road_edges) → centreline LineStrings                                    │
│  road_network_corridor_polygons(centrelines, width_dxf) → corridors         │
│  final_envelope = envelope.difference(corridor_union)                        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  placement_engine.compute_placement(final_envelope.wkt, height, n_towers)    │
│    → pack_towers (ROW_WISE / COL_WISE) → footprints + spacing audit          │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  geometry_to_geojson / wkt_to_geojson → geometry dict (no validation)        │
│  Return: plotBoundary, envelope, cop, copMargin, internalRoads,              │
│          towerFootprints, spacingLines, debug                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

End of Step 1. No code modified.

---

## Post-implementation: Updated pipeline and output (Steps 2–10)

### Final pipeline order

```
plot ingestion
  → setbacks (edge classification + margin resolution)
  → GC enforcement → gc_polygon
  → COP generation (carve_common_plot / generate_common_plot; area ≈ required, near road, validation)
  → envelope = gc_polygon − (COP + COP margin)
  → internal road generation (entry, spine, mandatory COP connection, tower access nodes)
  → road corridor subtraction → final_envelope
  → placement zone generation (split into islands, filter by min area, rank by area)
  → tower placement (on final_envelope)
  → parking preparation (parkingCandidateZones)
  → floor layout (optional)
```

### Example GeoJSON output structure

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
    "roadCorridors": [ { "type": "Polygon", "coordinates": [ ... ] }, ... ],
    "towerZones": [ { "type": "Polygon", "coordinates": [ ... ] }, ... ],
    "towerFootprints": [ { "type": "Polygon", "coordinates": [ ... ] }, ... ],
    "spacingLines": [ { "type": "LineString", "coordinates": [ ... ] }, ... ],
    "parkingCandidateZones": [ { "type": "Polygon", "coordinates": [ ... ] }, ... ]
  },
  "debug": {
    "buildableEnvelope": { "type": "Polygon", "coordinates": [ ... ] },
    "copCandidateZones": [ ... ],
    "roadNetwork": [ { "type": "LineString", "coordinates": [ ... ] }, ... ],
    "towerZones": [ ... ]
  }
}
```

### Regulatory and logic improvements

- **COP**: Area targeted to required minimum (not oversized); placement preferred near road-facing edge; validation that COP is inside plot and does not overlap setbacks; optional “must touch internal road” when roads are passed.
- **Internal roads**: Mandatory connection to COP when COP exists; tower access nodes along spine; road corridor polygons returned and subtracted from envelope; minimum width 6 m.
- **Placement zones**: Envelope after road subtraction split into candidate zones, filtered by minimum area, ranked by area for deterministic placement.
- **Parking**: Placeholder engine returns parkingCandidateZones for future allocation.

### Geometry validation improvements

- **utils.geometry_validation**: `validate_polygon` (validity, optional repair, min area, min dimension); `validate_polygon_strict` (validity + explain_validity); `validate_linestring`; `validate_geojson_geometry` (repair invalid GeoJSON).
- **API**: Envelope and COP are passed through `validate_geojson_geometry` before being included in the result.
