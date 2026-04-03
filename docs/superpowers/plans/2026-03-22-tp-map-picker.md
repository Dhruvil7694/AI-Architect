# TP Map Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken `WholeTpMap` SVG renderer with a clean `TpMapPicker` component that shows all FP numbers, road width labels, and designation colors — usable as a plot picker on both `/plots` and `/planner` pages.

**Architecture:** A single SVG component (`TpMapPicker`) that fetches data via the existing `useTpMapBundle` hook. It renders 5 layers bottom-to-top: background, road polygons, plot polygons, road labels, FP labels. All labels are always visible (no collision detection) with adaptive font sizing. Utility functions are extracted into a separate file for testability.

**Tech Stack:** React, SVG, TypeScript, TanStack Query, existing geometry utilities (`createViewTransform`, `projectPosition`, `geometryFeatureToPath` from `@/geometry/*`)

**Spec:** `docs/superpowers/specs/2026-03-22-tp-map-picker-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/modules/plots/components/tpMapPickerUtils.ts` | **Create** | Pure utility functions: designation colors, screen-space area, road midpoint/angle computation, adaptive font sizing |
| `frontend/src/modules/plots/components/TpMapPicker.tsx` | **Create** | Main SVG component: data fetching, layer rendering, hover/click, tooltip |
| `frontend/src/modules/plots/components/WholeTpMap.tsx` | **Delete** | Replaced by TpMapPicker |
| `frontend/src/app/(protected)/plots/page.tsx` | **Edit** | Swap `WholeTpMap` → `TpMapPicker` |
| `frontend/src/app/(protected)/planner/page.tsx` | **Edit** | Swap `PlannerTpMap` → `TpMapPicker` |

Existing files used (read-only):
- `frontend/src/modules/plots/hooks/useTpMapBundle.ts` — existing hook, no changes
- `frontend/src/services/tpMapService.ts` — existing service, no changes
- `frontend/src/geometry/transform.ts` — `createViewTransform`, `projectPosition`
- `frontend/src/geometry/pathBuilder.ts` — `geometryFeatureToPath`
- `frontend/src/geometry/bounds.ts` — `computeBoundsFromPositions`
- `frontend/src/geometry/geojsonParser.ts` — `parseGeoJsonToModel`, `GeometryFeature`, `GeometryModel`
- `frontend/src/lib/units.ts` — `formatArea`

---

### Task 1: Create utility functions (`tpMapPickerUtils.ts`)

**Files:**
- Create: `frontend/src/modules/plots/components/tpMapPickerUtils.ts`

These are pure functions with no React dependency — easy to test independently.

- [ ] **Step 1: Create the utility file with all functions**

```ts
// frontend/src/modules/plots/components/tpMapPickerUtils.ts

import type { Position } from "@/geometry/geometryNormalizer";
import type { ViewTransform } from "@/geometry/transform";
import { projectPosition } from "@/geometry/transform";

// ── Designation colors ──────────────────────────────────────────────

export type DesignationStyle = { fill: string; stroke: string };

export function getDesignationColor(designation?: string | null): DesignationStyle {
  if (!designation) return { fill: "rgba(226,232,240,0.4)", stroke: "#475569" };
  const d = designation.toUpperCase();
  if (d.includes("RESIDENTIAL") || d.includes("SALE FOR RES"))
    return { fill: "rgba(254,202,202,0.5)", stroke: "#dc2626" };
  if (d.includes("COMMERCIAL") || d.includes("SALE FOR COM"))
    return { fill: "rgba(254,240,138,0.55)", stroke: "#ca8a04" };
  if (d.includes("PUBLIC PURPOSE") || d.includes("PUBLIC"))
    return { fill: "rgba(253,186,116,0.5)", stroke: "#c2410c" };
  if (d.includes("OPEN SPACE") || d.includes("GARDEN"))
    return { fill: "rgba(134,239,172,0.5)", stroke: "#16a34a" };
  if (d.includes("S.E.W") || d.includes("SEWAGE") || d.includes("E.W.S"))
    return { fill: "rgba(196,181,253,0.4)", stroke: "#7c3aed" };
  if (d.includes("ROAD") || d.includes("SCHEME ROAD"))
    return { fill: "rgba(251,191,114,0.6)", stroke: "#b45309" };
  return { fill: "rgba(226,232,240,0.4)", stroke: "#475569" };
}

// ── Screen-space polygon area (shoelace) ────────────────────────────

/**
 * Compute screen-space area of a polygon ring after projecting through
 * the view transform. Uses the shoelace formula.
 */
export function computeScreenArea(
  ring: Position[],
  transform: ViewTransform,
): number {
  if (ring.length < 3) return 0;
  let acc = 0;
  const projected = ring.map((p) => projectPosition([Number(p[0]), Number(p[1])], transform));
  for (let i = 0; i < projected.length; i++) {
    const [x1, y1] = projected[i];
    const [x2, y2] = projected[(i + 1) % projected.length];
    acc += x1 * y2 - x2 * y1;
  }
  return Math.abs(acc) / 2;
}

// ── Adaptive font size ──────────────────────────────────────────────

export function getAdaptiveFontSize(screenArea: number): {
  fontSize: number;
  fontWeight: string;
} {
  if (screenArea > 2000) return { fontSize: 11, fontWeight: "700" };
  if (screenArea > 500) return { fontSize: 8, fontWeight: "600" };
  return { fontSize: 6, fontWeight: "500" };
}

// ── Road centerline midpoint + angle ────────────────────────────────

export type RoadLabelPlacement = {
  x: number;
  y: number;
  angle: number; // degrees
};

/**
 * Compute the midpoint of a polyline at 50% of total arc length,
 * plus the tangent angle (in degrees) at that point.
 * Flips the angle if the text would render upside-down.
 */
export function computeRoadLabelPlacement(
  coords: Position[],
  transform: ViewTransform,
): RoadLabelPlacement | null {
  if (coords.length < 2) return null;

  const projected = coords.map((c) =>
    projectPosition([Number(c[0]), Number(c[1])], transform),
  );

  // Compute total length
  let totalLen = 0;
  const segLens: number[] = [];
  for (let i = 0; i < projected.length - 1; i++) {
    const dx = projected[i + 1][0] - projected[i][0];
    const dy = projected[i + 1][1] - projected[i][1];
    const len = Math.sqrt(dx * dx + dy * dy);
    segLens.push(len);
    totalLen += len;
  }
  if (totalLen === 0) return null;

  // Walk to 50% of total length
  const half = totalLen / 2;
  let walked = 0;
  for (let i = 0; i < segLens.length; i++) {
    if (walked + segLens[i] >= half) {
      const t = (half - walked) / segLens[i];
      const x = projected[i][0] + t * (projected[i + 1][0] - projected[i][0]);
      const y = projected[i][1] + t * (projected[i + 1][1] - projected[i][1]);
      const dx = projected[i + 1][0] - projected[i][0];
      const dy = projected[i + 1][1] - projected[i][1];
      let angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
      // Flip if text would be upside-down
      if (angleDeg > 90) angleDeg -= 180;
      if (angleDeg < -90) angleDeg += 180;
      return { x, y, angle: angleDeg };
    }
    walked += segLens[i];
  }
  return null;
}

// ── Extract outer ring from GeoJSON geometry ────────────────────────

export function extractOuterRing(geometry: unknown): Position[] | null {
  const g = geometry as { type?: string; coordinates?: unknown };
  if (!g?.type || !g.coordinates) return null;
  if (g.type === "Polygon" && Array.isArray(g.coordinates) && Array.isArray(g.coordinates[0])) {
    return g.coordinates[0] as Position[];
  }
  if (
    g.type === "MultiPolygon" &&
    Array.isArray(g.coordinates) &&
    Array.isArray(g.coordinates[0]) &&
    Array.isArray(g.coordinates[0][0])
  ) {
    return g.coordinates[0][0] as Position[];
  }
  return null;
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors in `tpMapPickerUtils.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/plots/components/tpMapPickerUtils.ts
git commit -m "feat(tp-map): add utility functions for TpMapPicker

Extract designation colors, screen-space area computation,
adaptive font sizing, and road label placement into pure
utility functions."
```

---

### Task 2: Create the `TpMapPicker` component

**Files:**
- Create: `frontend/src/modules/plots/components/TpMapPicker.tsx`
- Read: `frontend/src/modules/plots/components/tpMapPickerUtils.ts` (from Task 1)
- Read: `frontend/src/modules/plots/hooks/useTpMapBundle.ts`
- Read: `frontend/src/geometry/transform.ts`
- Read: `frontend/src/geometry/pathBuilder.ts`
- Read: `frontend/src/geometry/bounds.ts`
- Read: `frontend/src/geometry/geojsonParser.ts`
- Read: `frontend/src/lib/units.ts`

- [ ] **Step 1: Create the TpMapPicker component**

```tsx
// frontend/src/modules/plots/components/TpMapPicker.tsx
"use client";

import { useMemo, useState, useCallback } from "react";
import Link from "next/link";
import type { Position } from "@/geometry/geometryNormalizer";
import {
  parseGeoJsonToModel,
  type GeometryFeature,
  type GeometryModel,
} from "@/geometry/geojsonParser";
import type { GeoJsonInput } from "@/geometry/geometryNormalizer";
import { computeBoundsFromPositions } from "@/geometry/bounds";
import { createViewTransform, projectPosition, type ViewTransform } from "@/geometry/transform";
import { geometryFeatureToPath } from "@/geometry/pathBuilder";
import { useTpMapBundle } from "@/modules/plots/hooks/useTpMapBundle";
import type { TpMapBundle } from "@/services/tpMapService";
import { formatArea } from "@/lib/units";
import {
  getDesignationColor,
  computeScreenArea,
  getAdaptiveFontSize,
  computeRoadLabelPlacement,
  extractOuterRing,
  type RoadLabelPlacement,
} from "./tpMapPickerUtils";

// ── Types ───────────────────────────────────────────────────────────

type TpMapPickerProps = {
  tpScheme: string;
  city?: string;
  onPlotSelect?: (plotId: string) => void;
  selectedPlotId?: string;
  className?: string;
};

type PlotFeatureData = {
  plotId: string;
  name: string;
  fpLabel: string;
  areaSqm: number;
  roadWidthM: number | null;
  designation: string;
};

type FpLabelEntry = {
  plotId: string;
  fpLabel: string;
  svgX: number;
  svgY: number;
  fontSize: number;
  fontWeight: string;
};

type RoadLabelEntry = {
  key: string;
  text: string;
  placement: RoadLabelPlacement;
};

// ── Constants ───────────────────────────────────────────────────────

const SVG_WIDTH = 960;
const SVG_HEIGHT = 700;
const PADDING = 28;

// ── Tooltip ─────────────────────────────────────────────────────────

function PlotTooltip({
  plot,
  x,
  y,
}: {
  plot: PlotFeatureData;
  x: number;
  y: number;
}) {
  return (
    <div
      className="fixed z-50 min-w-[200px] max-w-[280px] rounded-lg border border-neutral-200 bg-white px-3 py-2.5 text-left shadow-lg pointer-events-none"
      style={{ left: x + 14, top: y + 10 }}
    >
      <div className="border-b border-neutral-100 pb-1.5 font-semibold text-sm text-neutral-900">
        {plot.name}
      </div>
      {plot.designation && (
        <div className="mt-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
          {plot.designation}
        </div>
      )}
      <dl className="mt-1.5 space-y-0.5 text-xs text-neutral-600">
        <div className="flex justify-between gap-4">
          <dt>Plot ID</dt>
          <dd className="font-mono text-neutral-800">{plot.plotId}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Area</dt>
          <dd>
            {formatArea(plot.areaSqm, "sqft")}
            <span className="ml-1 text-neutral-500">
              ({formatArea(plot.areaSqm, "sqm")})
            </span>
          </dd>
        </div>
        {plot.roadWidthM != null && (
          <div className="flex justify-between gap-4">
            <dt>Road</dt>
            <dd>{plot.roadWidthM} m</dd>
          </div>
        )}
      </dl>
      <div className="mt-2 text-[10px] text-center text-orange-500 font-semibold">
        Click to select
      </div>
    </div>
  );
}

// ── Data processing ─────────────────────────────────────────────────

type ProcessedMapData = {
  // Road layer
  roadFeatures: GeometryFeature[];
  // Plot layer
  plotFeatures: GeometryFeature[];
  plotDataMap: Map<string, PlotFeatureData>;
  featureToPlotId: Map<string, string>;
  // Labels
  fpLabels: FpLabelEntry[];
  roadLabels: RoadLabelEntry[];
  // Transform
  transform: ViewTransform;
};

function processBundle(bundle: TpMapBundle): ProcessedMapData | null {
  // ── Collect all positions for bounds ──
  const allPositions: Position[] = [];

  // ── Road polygons ──
  const roadFeatures: GeometryFeature[] = [];
  for (const feature of bundle.layers.roads.features) {
    if (!feature.geometry) continue;
    const model = parseGeoJsonToModel(feature.geometry as GeoJsonInput, "plotBoundary");
    for (const f of model.features) {
      const fid = `road-${feature.id ?? Math.random().toString(36).slice(2)}`;
      roadFeatures.push({ ...f, id: fid });
      const ring = extractOuterRing(f.geometry);
      if (ring) for (const p of ring) allPositions.push([Number(p[0]), Number(p[1])]);
    }
  }

  // ── Plot polygons ──
  const plotFeatures: GeometryFeature[] = [];
  const plotDataMap = new Map<string, PlotFeatureData>();
  const featureToPlotId = new Map<string, string>();
  const plotGeometryMap = new Map<string, unknown>(); // plotId → raw geometry for area calc

  for (const feature of bundle.layers.fpPolygons.features) {
    if (!feature.geometry) continue;
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const plotId = String(props.plotId ?? "");
    if (!plotId) continue;

    const model = parseGeoJsonToModel(feature.geometry as GeoJsonInput, "plotBoundary");
    for (const f of model.features) {
      const fid = `plot-${plotId}-${f.id}`;
      plotFeatures.push({ ...f, id: fid });
      featureToPlotId.set(fid, plotId);
      const ring = extractOuterRing(f.geometry);
      if (ring) for (const p of ring) allPositions.push([Number(p[0]), Number(p[1])]);
    }

    const roadWidthRaw = props.roadWidthM;
    plotDataMap.set(plotId, {
      plotId,
      name: String(props.name ?? `FP ${plotId}`),
      fpLabel: String(props.fpLabel ?? ""),
      areaSqm: Number(props.areaSqm ?? 0),
      roadWidthM:
        typeof roadWidthRaw === "number" && Number.isFinite(roadWidthRaw)
          ? roadWidthRaw
          : null,
      designation: String(props.designation ?? ""),
    });
    plotGeometryMap.set(plotId, feature.geometry);
  }

  if (allPositions.length === 0) return null;

  // ── Compute transform ──
  const bounds = computeBoundsFromPositions(allPositions);
  if (!bounds) return null;
  const transform = createViewTransform(bounds, SVG_WIDTH, SVG_HEIGHT, PADDING, { flipY: true });

  // ── FP label points ──
  const fpLabels: FpLabelEntry[] = [];
  for (const feature of bundle.layers.fpLabelPoints.features) {
    if (!feature.geometry || (feature.geometry as { type?: string }).type !== "Point") continue;
    const coords = (feature.geometry as { coordinates?: unknown }).coordinates;
    if (!Array.isArray(coords) || coords.length < 2) continue;

    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const plotId = String(props.plotId ?? "");
    const fpLabel = String(props.fpLabel ?? "");
    if (!fpLabel) continue;

    // Project label point
    const [svgX, svgY] = projectPosition([Number(coords[0]), Number(coords[1])], transform);

    // Compute screen-space area from the corresponding polygon
    let screenArea = 1000; // default to medium
    const rawGeom = plotGeometryMap.get(plotId);
    if (rawGeom) {
      const ring = extractOuterRing(rawGeom);
      if (ring) screenArea = computeScreenArea(ring, transform);
    }

    const { fontSize, fontWeight } = getAdaptiveFontSize(screenArea);

    fpLabels.push({ plotId, fpLabel, svgX, svgY, fontSize, fontWeight });
  }

  // ── Road centerline labels ──
  const roadLabels: RoadLabelEntry[] = [];
  for (const feature of bundle.layers.roadCenterlines.features) {
    if (!feature.geometry) continue;
    const geom = feature.geometry as { type?: string; coordinates?: unknown };
    if (geom.type !== "LineString" || !Array.isArray(geom.coordinates)) continue;
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const widthM = props.widthM;
    if (typeof widthM !== "number" || !Number.isFinite(widthM)) continue;

    const placement = computeRoadLabelPlacement(
      geom.coordinates as Position[],
      transform,
    );
    if (!placement) continue;

    roadLabels.push({
      key: `road-label-${feature.id ?? Math.random().toString(36).slice(2)}`,
      text: `${Math.round(widthM)}m`,
      placement,
    });
  }

  return {
    roadFeatures,
    plotFeatures,
    plotDataMap,
    featureToPlotId,
    fpLabels,
    roadLabels,
    transform,
  };
}

// ── Main Component ──────────────────────────────────────────────────

export function TpMapPicker({
  tpScheme,
  city,
  onPlotSelect,
  selectedPlotId,
  className = "",
}: TpMapPickerProps) {
  const { data: bundle, isLoading, isError, refetch } = useTpMapBundle(tpScheme, city);
  const [hoveredPlotId, setHoveredPlotId] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const mapData = useMemo(() => {
    if (!bundle) return null;
    return processBundle(bundle);
  }, [bundle]);

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent<SVGElement>, plotId: string) => {
      setHoveredPlotId(plotId);
      setTooltipPos({ x: e.clientX, y: e.clientY });
    },
    [],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (hoveredPlotId) setTooltipPos({ x: e.clientX, y: e.clientY });
    },
    [hoveredPlotId],
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredPlotId(null);
  }, []);

  const handlePlotClick = useCallback(
    (plotId: string) => {
      onPlotSelect?.(plotId);
    },
    [onPlotSelect],
  );

  // ── Loading state ──
  if (isLoading) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-neutral-200 bg-neutral-50 ${className}`}
        style={{ aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
      >
        <div className="flex flex-col items-center gap-3">
          <span className="h-8 w-8 animate-spin rounded-full border-4 border-neutral-200 border-t-orange-500" />
          <span className="text-sm text-neutral-500">Loading TP map...</span>
        </div>
      </div>
    );
  }

  // ── Error state ──
  if (isError) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-red-200 bg-red-50 ${className}`}
        style={{ aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
      >
        <span className="text-sm text-red-600">Failed to load map.</span>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-md bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200"
        >
          Retry
        </button>
      </div>
    );
  }

  // ── Empty state ──
  if (!mapData) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-dashed border-neutral-200 bg-neutral-50 text-sm text-neutral-500 ${className}`}
        style={{ aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
      >
        No geometry to show
      </div>
    );
  }

  const { transform, roadFeatures, plotFeatures, plotDataMap, featureToPlotId, fpLabels, roadLabels } = mapData;
  const hoveredPlot = hoveredPlotId ? plotDataMap.get(hoveredPlotId) ?? null : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className={`overflow-hidden rounded-lg border border-neutral-200 ${className}`}
        style={{ width: "100%", height: "auto", aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
        aria-label="TP scheme map — click a plot to select"
        onMouseLeave={handleMouseLeave}
        onMouseMove={handleMouseMove}
      >
        {/* Layer 1: Background */}
        <rect x="0" y="0" width={SVG_WIDTH} height={SVG_HEIGHT} fill="#f8fafc" />

        {/* Layer 2: Road polygons */}
        <g>
          {roadFeatures.map((f) => (
            <path
              key={f.id}
              d={geometryFeatureToPath(f, transform)}
              fill="rgba(251,191,114,0.6)"
              stroke="#b45309"
              strokeWidth={0.5}
            />
          ))}
        </g>

        {/* Layer 3: Plot polygons */}
        <g>
          {plotFeatures.map((f) => {
            const plotId = featureToPlotId.get(f.id);
            const plotData = plotId ? plotDataMap.get(plotId) : undefined;
            const isHovered = plotId === hoveredPlotId;
            const isSelected = plotId === selectedPlotId;
            const colors = getDesignationColor(plotData?.designation);

            let fill = colors.fill;
            let stroke = colors.stroke;
            let strokeWidth = 1;
            let strokeDasharray: string | undefined;

            if (isSelected) {
              stroke = "#059669";
              strokeWidth = 2.5;
              strokeDasharray = "6 3";
            }
            if (isHovered) {
              fill = "rgba(59,130,246,0.2)";
              stroke = "#2563eb";
              strokeWidth = 2.5;
              strokeDasharray = undefined;
            }

            return (
              <path
                key={f.id}
                d={geometryFeatureToPath(f, transform)}
                fill={fill}
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeDasharray={strokeDasharray}
                style={{ cursor: "pointer" }}
                onMouseEnter={(e) => plotId && handleMouseEnter(e, plotId)}
                onClick={() => plotId && handlePlotClick(plotId)}
              />
            );
          })}
        </g>

        {/* Layer 4: Road centerline labels */}
        <g aria-hidden="true">
          {roadLabels.map((rl) => (
            <text
              key={rl.key}
              x={rl.placement.x}
              y={rl.placement.y}
              textAnchor="middle"
              dominantBaseline="middle"
              transform={`rotate(${rl.placement.angle}, ${rl.placement.x}, ${rl.placement.y})`}
              fill="#ffffff"
              stroke="#1e293b"
              strokeWidth={3}
              paintOrder="stroke"
              style={{ fontSize: "7px", fontWeight: 700, fontFamily: "sans-serif" }}
              className="select-none"
            >
              {rl.text}
            </text>
          ))}
        </g>

        {/* Layer 5: FP number labels */}
        <g aria-hidden="true">
          {fpLabels.map((lbl) => (
            <text
              key={`fp-${lbl.plotId}`}
              x={lbl.svgX}
              y={lbl.svgY}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="#1e293b"
              stroke="#ffffff"
              strokeWidth={2.5}
              paintOrder="stroke"
              style={{
                fontSize: `${lbl.fontSize}px`,
                fontWeight: lbl.fontWeight,
                fontFamily: "sans-serif",
              }}
              className="select-none"
            >
              {lbl.fpLabel}
            </text>
          ))}
        </g>
      </svg>

      {/* Tooltip */}
      {hoveredPlot && (
        <PlotTooltip plot={hoveredPlot} x={tooltipPos.x} y={tooltipPos.y} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors in `TpMapPicker.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/plots/components/TpMapPicker.tsx
git commit -m "feat(tp-map): create TpMapPicker SVG component

Renders all FP labels (adaptive font sizing, no collision detection),
road width labels on centerlines, designation-colored polygons,
and separate road polygon layer. Uses useTpMapBundle for data."
```

---

### Task 3: Update `/plots` page to use `TpMapPicker`

**Files:**
- Modify: `frontend/src/app/(protected)/plots/page.tsx`

- [ ] **Step 1: Replace WholeTpMap with TpMapPicker**

In `frontend/src/app/(protected)/plots/page.tsx`, make these changes:

1. Remove this import:
   - `import { WholeTpMap } from "@/modules/plots/components/WholeTpMap";`
   - **Keep** `import type { GeoJsonInput } from "@/geometry/geometryNormalizer";` — still used by `MiniPlotPreview` on line 72.

2. Add these imports:
   - `import { TpMapPicker } from "@/modules/plots/components/TpMapPicker";`
   - `import { useRouter } from "next/navigation";`

3. Add router hook inside `PlotsPage`:
   - `const router = useRouter();`

4. Remove the `plotsWithGeometry` filter (lines 13-15) — no longer needed.

5. Replace the entire WholeTpMap conditional block (lines 26-33, which is guarded by `!isLoading && !isError && plotsWithGeometry.length > 0`) with an unconditional block. `TpMapPicker` handles its own loading/error/empty states internally, so no outer guard is needed:

```tsx
<div className="rounded-md border border-neutral-200 bg-white p-4">
  <h3 className="mb-2 text-sm font-medium text-neutral-700">
    Whole TP overview
  </h3>
  <TpMapPicker
    tpScheme="TP14"
    onPlotSelect={(id) => router.push(`/planner?plotId=${encodeURIComponent(id)}`)}
  />
</div>
```

The plot cards section below can remain — it still uses `usePlotsQuery` independently.

- [ ] **Step 2: Verify the file compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(protected\)/plots/page.tsx
git commit -m "feat(plots): use TpMapPicker on plots page

Replace WholeTpMap with TpMapPicker. The map now fetches its
own data via useTpMapBundle and shows all FP labels."
```

---

### Task 4: Update `/planner` page to use `TpMapPicker`

**Files:**
- Modify: `frontend/src/app/(protected)/planner/page.tsx`

- [ ] **Step 1: Replace PlannerTpMap with TpMapPicker**

In `frontend/src/app/(protected)/planner/page.tsx`:

1. Remove import:
   - `import { PlannerTpMap } from "@/modules/planner/components/PlannerTpMap";`

2. Add import:
   - `import { TpMapPicker } from "@/modules/plots/components/TpMapPicker";`

3. Add `locationPreference` to the `PlannerContent` function body (after the existing `usePlannerStore` lines, around line 30):
   ```tsx
   const locationPreference = usePlannerStore((s) => s.locationPreference);
   ```

4. Replace lines 131-136 (the no-plot-selected section):

Before:
```tsx
{/* No FP selected — show full TP map for selection */}
<div className="min-h-0 flex-1 rounded-[2rem] border border-neutral-100 bg-white shadow-inner overflow-hidden relative">
  <PlannerTpMap />
</div>
```

After:
```tsx
{/* No FP selected — show full TP map for selection */}
<div className="min-h-0 flex-1 rounded-[2rem] border border-neutral-100 bg-white shadow-inner overflow-hidden relative p-6">
  <TpMapPicker
    tpScheme={locationPreference.tpId ?? "TP14"}
    city={locationPreference.districtName}
    selectedPlotId={selectedPlotId ?? undefined}
    onPlotSelect={(id) => setSelectedPlotId(id)}
  />
</div>
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/\(protected\)/planner/page.tsx
git commit -m "feat(planner): use TpMapPicker for plot selection

Replace PlannerTpMap (MapLibre) with TpMapPicker (SVG) for the
plot selection step. Lighter weight, consistent with /plots page."
```

---

### Task 5: Delete `WholeTpMap.tsx`

**Files:**
- Delete: `frontend/src/modules/plots/components/WholeTpMap.tsx`

- [ ] **Step 1: Verify no other files import WholeTpMap**

Run: `cd frontend && grep -r "WholeTpMap" src/ --include="*.ts" --include="*.tsx" | grep -v node_modules`
Expected: No results (all imports should have been replaced in Tasks 3-4)

- [ ] **Step 2: Delete the file**

```bash
rm frontend/src/modules/plots/components/WholeTpMap.tsx
```

- [ ] **Step 3: Verify build still compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/modules/plots/components/WholeTpMap.tsx
git commit -m "chore: remove WholeTpMap (replaced by TpMapPicker)"
```

---

### Task 6: Visual verification

- [ ] **Step 1: Start the dev server**

Run: `cd frontend && npm run dev`

- [ ] **Step 2: Verify `/plots` page**

Open `http://localhost:3000/plots` in browser. Verify:
- All ~175 FP numbers are visible on the map
- Road width labels (e.g., "18m", "15m") appear along road centerlines
- Plots are colored by designation (pink residential, yellow commercial, green open space, etc.)
- Hovering a plot shows blue highlight and tooltip with plot name, area, road width
- Clicking a plot navigates to `/planner?plotId=...`

- [ ] **Step 3: Verify `/planner` page (no plot selected)**

Open `http://localhost:3000/planner` (with no `plotId` query param). Verify:
- The TpMapPicker map appears in the main area
- Clicking a plot selects it and transitions to the planner workspace

- [ ] **Step 4: Tune font size thresholds if needed**

If labels look too small or too large on certain plots, adjust the thresholds in `tpMapPickerUtils.ts:getAdaptiveFontSize()`. The values `2000` and `500` (screen-space sq px) are approximate and may need visual tuning.
