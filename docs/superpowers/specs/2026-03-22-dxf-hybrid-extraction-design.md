# DXF Hybrid Polygon Extraction — Design Spec

**Date**: 2026-03-22
**Status**: Approved
**Scope**: Fix `dxf_reader.py` to use closed LWPOLYLINES directly as plot polygons instead of breaking all geometry into segments and re-polygonizing.

---

## Problem

The current `read_dxf()` in `backend/tp_ingestion/services/dxf_reader.py` extracts all LINE/LWPOLYLINE/ARC entities as individual segments, then uses `shapely.ops.polygonize()` to reconstruct polygons from the segment soup. This approach loses geometry:

- **96/182 plots (53%)** have geometry areas >30% smaller than Excel reference areas
- Extreme cases: FP42 (99% area loss), FP11 (98%), FP116 (97%), FP181 (97%)
- Root cause: `polygonize` only works when edges form perfectly closed rings. Any tiny gap from coordinate snapping, arc approximation, or missing segments breaks polygon closure.

Meanwhile, the DXF file contains **186 closed LWPOLYLINES** on the "F.P." layer — these are the actual plot boundaries drawn by the surveyor. When used directly, **161/206 matched labels have area within 15% of Excel reference**.

## Goal

Replace the all-segments-then-polygonize approach with a three-tier hybrid extraction that preserves the surveyor's closed polylines.

---

## Architecture

### Three-Tier Extraction (in `read_dxf()`)

**Tier 1 — Closed LWPOLYLINES as direct polygons** (~143 plots)

Extract every closed LWPOLYLINE on the polygon layer directly as a Shapely Polygon. These are the surveyor's actual plot boundaries. No polygonization needed.

Implementation:
- Iterate entities on the polygon layer
- For LWPOLYLINE with `is_closed=True`: extract vertices with `get_points(format='xyseb')` to get (x, y, start_width, end_width, bulge) tuples
- Apply `snap_decimals` rounding to all coordinates (same as segments, for coordinate consistency)
- Handle bulge: for each vertex with `bulge != 0`, interpolate arc points via `_bulge_to_arc_points()` between that vertex and the next
- After snapping + bulge expansion, require `len(unique_pts) >= 3` (post-snap deduplication)
- Create `Polygon(pts)`, validate with `make_valid()`. If `make_valid()` returns `MultiPolygon`, keep the largest component (same strategy as existing `_repair()`)
- Filter by `min_polygon_area`

**Tier 2 — Block subdivision** (~20-30 plots)

Some closed LWPOLYLINEs are "block outlines" containing multiple sub-plots (e.g., FP 7+8, FP 130+127+128+129, FP 43+44+45). Internal LINE/ARC/open-LWPOLYLINE segments divide these blocks into individual plots.

Implementation:
- After Tier 1, perform an **internal-only** label-to-polygon match (point-in-polygon) using the labels extracted in the same pass. This is solely for block detection — the authoritative label-to-plot matching remains in `geometry_matcher.py` (called by `ingestion_service.py`)
- Use `_is_fp_number()` regex `^\d+(/\d+)?$` to classify labels as numeric vs designation text. Import from `geometry_matcher.py` to avoid duplication
- Identify "block polygons" — Tier 1 polygons containing 2+ *numeric* FP labels. Use `polygon.contains(Point(x,y))` with a 0.5-unit buffer on the polygon for label counting (handles labels near boundaries)
- For each block polygon:
  1. Collect all segments (LINE, ARC, open LWPOLYLINE) that intersect the block's bounding box expanded by **2.0 DXF units** (feet) — enough to capture shared boundary segments without pulling in distant geometry
  2. Add the block polygon's own boundary ring as segments (break exterior ring into individual edge LineStrings)
  3. Run `unary_union()` then `polygonize()` on these local segments
  4. Filter results by `min_polygon_area`
  5. Keep only sub-polygons where `block_polygon.contains(sub_poly.representative_point())` — this is more robust than full containment since sub-polygons may share the block boundary exactly
- Remove the block polygon from the Tier 1 result set, add sub-polygons in its place
- If polygonization produces 0 valid sub-polygons for a block, keep the original block polygon (don't lose data)

**Tier 3 — No change to existing recovery**

FP labels that aren't contained in any Tier 1 or Tier 2 polygon are left for the existing `_recover_polygon_for_label_point()` in `ingestion_service.py` to handle (it has access to Excel `target_area` for scoring, which `read_dxf()` does not). **No Tier 3 logic is added to `dxf_reader.py`.**

The existing recovery in `ingestion_service.py` uses `result.segments` to do local polygonization around unmatched label points. This path remains as-is.

### Polygon Merge Strategy

The final `result.polygons` list is constructed as:
1. Start with all Tier 1 polygons
2. For each identified block polygon, remove it and insert its Tier 2 sub-polygons at the same position
3. No Tier 3 polygons — those are recovered downstream in `ingestion_service.py`
4. No deduplication needed (each polygon comes from a unique closed LWPOLYLINE or a unique sub-polygon)

### Segments Field Contract

`result.segments` continues to hold **all** raw segments from the polygon layer (LINE, ARC, open LWPOLYLINE entities — same as today). This is required by `ingestion_service._recover_polygon_for_label_point()` for downstream area-validation recovery. The segments are also used for Tier 2 block subdivision internally.

The only change: closed LWPOLYLINEs used as Tier 1 polygons are **not** broken into segments (they go directly to polygons). Open LWPOLYLINEs and other entities still produce segments as before.

### Bulge Handling

LWPOLYLINE vertices can have bulge values (arc segments between vertices). For Tier 1 closed-LWPOLYLINE extraction:
1. Use `entity.get_points(format='xyseb')` which returns tuples of `(x, y, start_width, end_width, bulge)`
2. Iterate vertices. For each vertex with `bulge != 0`, call `_bulge_to_arc_points(p_current, p_next, bulge, snap_decimals)` to get interpolated arc points
3. Build the final coordinate list: for zero-bulge vertices, add the vertex directly; for non-zero-bulge vertices, add the arc interpolation points (which end at the next vertex)

Note: The existing `_bulge_to_arc_points()` function's sign convention has been validated against ezdxf's bulge definition and produces correct arc approximations for the TP14 DXF.

### Label Classification

To distinguish numeric FP labels from designation text (both on "FINAL F.P." layer), reuse `_is_fp_number()` from `geometry_matcher.py`:
- Numeric: matches `^\d+(/\d+)?$` (e.g., "133", "160/1")
- Designation text: everything else ("SALE FOR RESIDENCE", "GARDEN", "S.E.W.S.H.", etc.)

Only numeric labels count when determining if a polygon is a "block" needing subdivision.

---

## Interface

`DXFReadResult` stays unchanged:
```python
@dataclass
class DXFReadResult:
    polygons: List[Polygon]        # All extracted plot polygons (Tier 1 + Tier 2 sub-polygons)
    segments: List[LineString]     # Raw segments from non-closed entities (for debug/recovery)
    labels: List[Tuple[str, Point]]
    block_labels: List[Tuple[str, Point]]
    layer_names: List[str]
    entity_type_counts: dict
```

Consumers (`ingestion_service.py`, `geometry_matcher.py`) see no interface change.

---

## File Changes

| File | Action |
|---|---|
| `backend/tp_ingestion/services/dxf_reader.py` | **Rewrite** `read_dxf()` to use hybrid extraction. Keep all existing helper functions (`_entity_to_segments`, `_bulge_to_arc_points`, `_snap`, `_export_debug_geojson`, `read_dxf_road_widths`). Replace `_polygonize_segments()` with new Tier 1 + Tier 2 logic. |
| Re-ingestion command | **Run** `ingest_tp` management command for TP14 with `--update-existing` |

### No other file changes required

The ingestion service, geometry matcher, API views, and frontend all consume the same `DXFReadResult` / `Plot` model interface.

---

## Validation Criteria

After re-ingestion, measured against Excel reference areas:
1. **Plot count**: 170+ plots matched and saved (currently 182 in DB but many with wrong geometry)
2. **Area accuracy**: <20% of plots should have >30% area discrepancy vs Excel (currently 53% have >30% discrepancy — same metric, same threshold)
3. **Visual check**: Plot shapes on the map should resemble the original PDF layout
4. **No regressions**: Ingestion service runs without errors, existing `_recover_polygon_for_label_point()` still works (segments field populated)

---

## Out of Scope

- Changes to `ingestion_service.py` or `geometry_matcher.py` (except importing `_is_fp_number`)
- Frontend rendering changes
- New DXF file or PDF-based extraction
- Changes to other TP schemes (only TP14 re-ingestion)
- Fixing `_bulge_to_arc_points()` sign convention (existing behavior produces acceptable results for TP14; can be revisited separately)
