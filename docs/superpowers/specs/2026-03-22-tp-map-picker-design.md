# TP Map Picker — Design Spec

**Date**: 2026-03-22
**Status**: Approved
**Scope**: Replace the broken `WholeTpMap` SVG renderer with a clean, reusable `TpMapPicker` component that displays all FP numbers, road width labels, and designation colors — functioning as a plot picker on both `/plots` and `/planner` pages.

---

## Problem

The current `WholeTpMap` component renders the TP14 scheme map poorly:

1. **Almost no FP labels visible** — aggressive collision detection (bounding-box greedy algorithm at 800×480 viewport) hides ~174 of 175 labels.
2. **No road width labels** — road widths exist in the data but are never rendered on the map.
3. **Plot boundaries unclear** — 0.8px strokes and washed-out fills (0.25 opacity) make plots indistinguishable.
4. **No layer separation** — roads are mixed into the same `plots[]` array as FP plots; no separate rendering pass.
5. **Data source mismatch** — uses `usePlotsQuery` (flat plot list) instead of `useTpMapBundle` which already returns separated layers (`fpPolygons`, `roads`, `roadCenterlines`, `fpLabelPoints`, `blockLabels`).

## Goal

A read-only "plot picker" map where the user sees every FP number, road width labels, and designation colors, then clicks a plot to select it.

---

## Architecture

### Component: `TpMapPicker`

A single reusable SVG component that replaces `WholeTpMap`.

**Props:**
```ts
type TpMapPickerProps = {
  tpScheme: string;
  city?: string;
  onPlotSelect?: (plotId: string) => void;
  selectedPlotId?: string;
  className?: string;
};
```

The component fetches its own data internally via the existing `useTpMapBundle` hook at `frontend/src/modules/plots/hooks/useTpMapBundle.ts` — consumers only pass `tpScheme`.

`plotId` is the string format `"{tp_scheme}-{fp_number}"` (e.g., `"TP14-133"`), consistent with what the planner page expects and what `fpPolygons` features carry in `properties.plotId`.

### Data Source

Uses `getTpMapBundle()` from `tpMapService.ts` (existing, no backend changes). Returns:
- `layers.fpPolygons` — GeoJSON FeatureCollection of plot polygons with properties (`plotId`, `name`, `fpLabel`, `areaSqm`, `designation`, `roadWidthM`, `kind`)
- `layers.fpLabelPoints` — GeoJSON FeatureCollection of polylabel-computed optimal label positions (Point geometry)
- `layers.roads` — GeoJSON FeatureCollection of road polygons
- `layers.roadCenterlines` — GeoJSON FeatureCollection of road centerlines with properties (`label`, `widthM`)
- `layers.blockLabels` — GeoJSON FeatureCollection of CAD overlay labels (not rendered — out of scope)
- `meta.bbox` — bounding box for viewport computation

### Coordinate System

All geometry is in `LOCAL_DXF` coordinate space (DXF feet, SRID=0, Y-up). SVG is Y-down. Use `createViewTransform(bounds, width, height, padding, { flipY: true })` from `@/geometry/transform` to produce the view transform — same approach as the existing `WholeTpMap`.

### Rendering Layers (bottom to top)

1. **Background** — SVG rect with `#f8fafc` fill
2. **Road polygons** — from `layers.roads`, strong orange fill, thin stroke
3. **Plot polygons** — from `layers.fpPolygons`, designation-colored fills, darker strokes
4. **Road centerline labels** — from `layers.roadCenterlines`, width labels placed at centerline midpoint
5. **FP number labels** — from `layers.fpLabelPoints`, always visible (no collision detection), adaptive font size

### Label Strategy

#### FP Numbers — always show all labels

The original PDF renders all ~175 labels readably. Instead of collision detection, use adaptive font sizing based on each plot's screen-space area:

| Screen-space area | Font size | Weight |
|---|---|---|
| Large (>2000 sq px) | 11px | bold |
| Medium (500–2000 sq px) | 8px | semibold |
| Small (<500 sq px) | 6px | medium |

**Label-to-polygon association**: Build a `Map<plotId, GeoJSON.Feature>` from `fpPolygons`. For each label point in `fpLabelPoints`, look up the corresponding polygon via `properties.plotId` (present on both layers). Compute screen-space area by projecting the polygon's outer ring through the view transform and applying the shoelace formula.

**Label positions**: Extract coordinates directly from `fpLabelPoints` features via `feature.geometry.coordinates` (a `[x, y]` pair) — do NOT pass Point geometries through `parseGeoJsonToModel` or `geometryFeatureToPath`, which only handle Polygon/LineString. Project the `[x, y]` through `projectPosition(coord, transform)` to get SVG coordinates.

**Label text**: Use `feature.properties.fpLabel` (e.g., `"133"`) from the label point feature.

#### Road Labels

Use `feature.properties.widthM` from `roadCenterlines` features. Format as `"18m"` (concise — `Math.round(widthM) + "m"`). If `widthM` is null/undefined, skip the label.

**Placement**: For each road centerline (LineString geometry), compute the midpoint by interpolating along the polyline at 50% of total length. The rotation angle is the tangent at that midpoint — computed as `Math.atan2(dy, dx)` between the two vertices straddling the midpoint. If the angle would render text upside-down (> 90° or < -90°), flip by 180°.

White text (`#ffffff`) with dark stroke outline (`stroke="#1e293b" strokeWidth="3" paintOrder="stroke"`) for contrast against the orange road fill. Font: 7px bold.

---

## Visual Styling

### Designation Color Palette

| Designation | Fill | Stroke |
|---|---|---|
| Residential | `rgba(254,202,202,0.5)` | `#dc2626` |
| Commercial | `rgba(254,240,138,0.55)` | `#ca8a04` |
| Public Purpose | `rgba(253,186,116,0.5)` | `#c2410c` |
| Open Space / Garden | `rgba(134,239,172,0.5)` | `#16a34a` |
| S.E.W / Sewage | `rgba(196,181,253,0.4)` | `#7c3aed` |
| Road | `rgba(251,191,114,0.6)` | `#b45309` |
| Default / Unknown | `rgba(226,232,240,0.4)` | `#475569` |

### Strokes & Interactions

- Default plot stroke: `1px`
- Hovered plot: `2.5px` blue (`#2563eb`), fill `rgba(59,130,246,0.2)`
- Selected plot: `2.5px` emerald (`#059669`), dashed stroke (`strokeDasharray="6 3"`)
- Road polygon stroke: `0.5px`
- Cursor: `pointer` on plots, `default` on roads
- SVG background: `#f8fafc` (slate-50)

### Tooltip

Inline the tooltip within `TpMapPicker` (adapted from the existing `PlotTooltip` in `WholeTpMap.tsx`). Map `fpPolygons` feature properties to tooltip data:
- `properties.plotId` → tooltip `id`
- `properties.name` → tooltip `name` (e.g., "FP 133")
- `properties.areaSqm` → tooltip `areaSqm`
- `properties.roadWidthM` → tooltip `roadWidthM`
- `properties.designation` → tooltip `designation`

Tooltip shows on hover: plot name, area (sqft + sqm), road width, designation badge. Includes "Open in planner →" link.

### Loading / Error / Empty States

- **Loading**: Centered spinner with "Loading TP map..." text, same dimensions as the SVG would occupy
- **Error**: "Failed to load map" message with a retry button
- **Empty** (no features): "No geometry to show" placeholder (same as current `WholeTpMap` empty state)

---

## Integration

### `/plots` page
```tsx
<TpMapPicker
  tpScheme="TP14"
  onPlotSelect={(id) => router.push(`/planner?plotId=${id}`)}
/>
```

### `/planner` page
```tsx
<TpMapPicker
  tpScheme="TP14"
  selectedPlotId={selectedPlotId}
  onPlotSelect={(id) => setSelectedPlotId(id)}
/>
```

---

## File Changes

| File | Action |
|---|---|
| `frontend/src/modules/plots/components/TpMapPicker.tsx` | **Create** — new reusable component |
| `frontend/src/modules/plots/hooks/useTpMapBundle.ts` | **Use existing** — already exists, no changes needed |
| `frontend/src/modules/plots/components/WholeTpMap.tsx` | **Delete** — replaced by TpMapPicker |
| `frontend/src/app/(protected)/plots/page.tsx` | **Edit** — swap WholeTpMap → TpMapPicker |
| `frontend/src/app/(protected)/planner/page.tsx` | **Edit** — add TpMapPicker as plot selection step |

### No backend changes required

The `TpBundleAPIView` already returns all necessary layers.

---

## Out of Scope

- Zoom/pan (can be added later with SVG transform if needed)
- Measuring tools
- Layer toggle UI
- Block labels rendering (data is available but not needed for plot picking)
- Backend DXF re-ingestion or geometry fixes

---

## Implementation Notes

- Font size thresholds (2000/500 sq px) are approximate — may need tuning after visual inspection.
- The `city` prop defaults to undefined; the existing `useTpMapBundle` hook handles this correctly.
