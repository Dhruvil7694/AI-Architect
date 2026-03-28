 "use client";

import { useEffect, useRef, useMemo, useCallback, useState, memo, forwardRef, useImperativeHandle } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useFloorPlan, useFloorCore, useAIFloorPlan, useFloorPlanPreviewImage } from "@/modules/planner/hooks/usePlannerData";
import { groupFeaturesByLayer } from "@/geometry/layerManager";
import { SvgCanvas, type SvgCanvasHandle } from "@/modules/planner/components/visualization/SvgCanvas";
import { projectPosition } from "@/geometry/transform";
import type { ViewTransform } from "@/geometry/transform";
import type { GeometryModel, GeometryFeature } from "@/geometry/geojsonParser";
import type {
  FloorPlanFeature,
  FloorPlanLayout,
  FloorPlanMetrics,
  FloorPlanGdcr,
  PlacementDebugMetrics,
  PlacementDebugGeoJson,
  FloorCoreRequest,
  FloorCoreResponse,
  FloorCoreGraphNode,
  FloorCoreGraphEdge,
} from "@/services/plannerService";
import type { SelectedUnitInfo } from "@/state/plannerStore";
import { ZoomableImageViewer } from "./ZoomableImageViewer";

// ─── Colour palette ────────────────────────────────────────────────────────────
const LAYER_STYLE: Record<string, { fill: string; stroke: string; strokeWidth?: number; strokeDasharray?: string }> = {
  footprint_bg: { fill: "#fdfdfd", stroke: "#0f172a", strokeWidth: 2 },
  corridor:     { fill: "rgba(241, 245, 249, 0.9)", stroke: "#cbd5e1", strokeWidth: 1 },
  core:         { fill: "rgba(226, 232, 240, 0.8)", stroke: "#94a3b8", strokeWidth: 1.5 },
  stair:        { fill: "#f8fafc", stroke: "#64748b", strokeWidth: 1, strokeDasharray: "3 2" },
  lobby:        { fill: "rgba(7, 89, 133, 0.05)", stroke: "#0ea5e9", strokeWidth: 0.8 },
  lift:         { fill: "#1e293b", stroke: "#0f172a", strokeWidth: 1 },
  balcony:      { fill: "rgba(34, 197, 94, 0.05)", stroke: "#22c55e", strokeWidth: 0.8, strokeDasharray: "4 2" },
  // Units: outline-only (rooms provide the internal detail)
  unit_2BHK:    { fill: "none", stroke: "#f97316", strokeWidth: 1.5 },
  unit_3BHK:    { fill: "none", stroke: "#ea580c", strokeWidth: 1.5 },
  unit_4BHK:    { fill: "none", stroke: "#e11d48", strokeWidth: 1.5 },
  unit_1BHK:    { fill: "none", stroke: "#0ea5e9", strokeWidth: 1.5 },
  unit_1RK:     { fill: "none", stroke: "#8b5cf6", strokeWidth: 1.5 },
  unit_STUDIO:  { fill: "none", stroke: "#7c3aed", strokeWidth: 1.5 },
  unit_default: { fill: "none", stroke: "#f97316", strokeWidth: 1.5 },
  // Room subdivisions
  room_LIVING:  { fill: "rgba(255, 251, 235, 0.55)", stroke: "#d97706", strokeWidth: 0.8 },
  room_BEDROOM: { fill: "rgba(239, 246, 255, 0.55)", stroke: "#3b82f6", strokeWidth: 0.8 },
  room_KITCHEN: { fill: "rgba(254, 242, 242, 0.55)", stroke: "#ef4444", strokeWidth: 0.8 },
  room_TOILET:  { fill: "rgba(236, 253, 245, 0.55)", stroke: "#10b981", strokeWidth: 0.8 },
  room_PASSAGE: { fill: "rgba(249, 250, 251, 0.4)",  stroke: "#9ca3af", strokeWidth: 0.6 },
  // Thick walls (filled rectangles)
  wall:         { fill: "#334155", stroke: "#1e293b", strokeWidth: 0.5 },
  wall_entry:   { fill: "#475569", stroke: "#1e293b", strokeWidth: 0.5 },
  // Door arcs
  door:         { fill: "rgba(148, 163, 184, 0.15)", stroke: "#64748b", strokeWidth: 0.6, strokeDasharray: "2 1" },
  // Windows
  window:       { fill: "#93c5fd", stroke: "#3b82f6", strokeWidth: 0.8 },
};

// ─── Debug layer colour palette ────────────────────────────────────────────────
// Render order: buildable_envelope → spacing_buffer → leftover_polygon →
//               selected_footprint → cop_area  (bottom-to-top)
const DEBUG_LAYER_STYLE: Record<
  string,
  { fill: string; stroke: string; strokeWidth: number; strokeDasharray?: string }
> = {
  buildable_envelope: { fill: "none",                     stroke: "#6b7280", strokeWidth: 1.5, strokeDasharray: "8 4" },
  spacing_buffer:     { fill: "rgba(239,68,68,0.10)",     stroke: "#ef4444", strokeWidth: 1.5, strokeDasharray: "5 3" },
  leftover_polygon:   { fill: "rgba(245,158,11,0.14)",    stroke: "#f59e0b", strokeWidth: 1.5, strokeDasharray: "5 3" },
  selected_footprint: { fill: "rgba(59,130,246,0.14)",    stroke: "#3b82f6", strokeWidth: 2   },
  cop_area:           { fill: "rgba(34,197,94,0.14)",     stroke: "#22c55e", strokeWidth: 1.5 },
};

// Render order index for sorting (lower = rendered first = further back)
const DEBUG_RENDER_ORDER = [
  "buildable_envelope",
  "spacing_buffer",
  "leftover_polygon",
  "selected_footprint",
  "cop_area",
];

function styleForFeature(f: FloorPlanFeature) {
  const layer = f.properties.layer;
  if (layer === "unit") {
    const unit_type = f.properties.unit_type;
    return LAYER_STYLE[`unit_${unit_type}`] ?? LAYER_STYLE.unit_default;
  }
  if (layer === "room") {
    const roomType = f.properties.room_type;
    return LAYER_STYLE[`room_${roomType}`] ?? LAYER_STYLE.room_LIVING;
  }
  if (layer === "wall") {
    const wt = f.properties.wall_type;
    return wt === "entry" ? LAYER_STYLE.wall_entry : LAYER_STYLE.wall;
  }
  if (layer === "door") {
    return LAYER_STYLE.door;
  }
  if (layer === "window") {
    return LAYER_STYLE.window;
  }
  return LAYER_STYLE[layer] ?? { fill: "rgba(200,200,200,0.6)", stroke: "#888", strokeWidth: 1 };
}

// ─── SVG path builder for a Polygon feature ───────────────────────────────────
function featureToPath(
  geom: { type: "Polygon"; coordinates: number[][][] },
  vt: ViewTransform,
): string {
  const ring = geom.coordinates[0];
  if (!ring || ring.length < 3) return "";
  const pts = ring.map(([x, y]) => projectPosition([x, y], vt));
  const [first, ...rest] = pts;
  return `M${first[0]},${first[1]} ` + rest.map(([x, y]) => `L${x},${y}`).join(" ") + " Z";
}

// ─── Centroid of a ring (screen coords) ───────────────────────────────────────
function ringCentroid(
  coords: number[][],
  vt: ViewTransform,
): [number, number] {
  let sx = 0, sy = 0;
  const n = coords.length;
  for (const [x, y] of coords) {
    const [px, py] = projectPosition([x, y], vt);
    sx += px; sy += py;
  }
  return [sx / n, sy / n];
}

// ─── Floor plan SVG layers ─────────────────────────────────────────────────────
function FloorPlanLayers({
  layout,
  viewTransform,
  onUnitClick,
}: {
  layout: FloorPlanLayout;
  viewTransform: ViewTransform;
  onUnitClick?: (f: FloorPlanFeature) => void;
}) {
  // Render in layer order: rooms inside units, walls on top, unit outlines last
  const ordered = useMemo(() => {
    const order = ["footprint_bg", "balcony", "core", "corridor", "room", "wall", "door", "window", "lobby", "stair", "lift", "unit"];
    const sorted = [...layout.features].sort((a: FloorPlanFeature, b: FloorPlanFeature) => {
      const ai = order.indexOf(a.properties.layer);
      const bi = order.indexOf(b.properties.layer);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
    return sorted;
  }, [layout]);

  // Room label colour by type
  const roomLabelColor: Record<string, string> = {
    LIVING: "#92400e", BEDROOM: "#1e40af", KITCHEN: "#991b1b",
    TOILET: "#065f46", PASSAGE: "#6b7280",
  };

  return (
    <g>
      {ordered.map((f) => {
        const style = styleForFeature(f);
        const layer = f.properties.layer;

        // All features are now Polygons (walls, doors, windows included)
        const geom = f.geometry as { type: "Polygon"; coordinates: number[][][] };
        const d = featureToPath(geom, viewTransform);
        if (!d) return null;
        const isUnit    = layer === "unit";
        const isRoom    = layer === "room";
        const isLift    = layer === "lift";
        const isStair   = layer === "stair";
        const isBalcony = layer === "balcony";
        const [cx, cy] = ringCentroid(geom.coordinates[0], viewTransform);

        return (
          <g key={f.id}>
            <path
              d={d}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={style.strokeWidth ?? 1}
              strokeDasharray={style.strokeDasharray}
              onClick={isUnit ? () => onUnitClick?.(f) : undefined}
              style={{ cursor: isUnit ? "pointer" : "default" }}
            />
            {/* Stair cross-hatch */}
            {isStair && (
              <path
                d={d}
                fill="url(#stairHatch)"
                stroke="none"
                style={{ pointerEvents: "none" }}
              />
            )}
            {/* Room labels */}
            {isRoom && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={7} fontWeight="500"
                fill={roomLabelColor[f.properties.room_type ?? ""] ?? "#374151"}
                style={{ pointerEvents: "none" }}
              >
                {f.properties.label}
              </text>
            )}
            {/* Labels */}
            {isLift && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={9} fontWeight="600" fill="white"
                style={{ pointerEvents: "none" }}
              >
                {f.properties.label ?? `L${f.properties.index}`}
              </text>
            )}
            {isStair && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={9} fontWeight="600" fill="#1e293b"
                style={{ pointerEvents: "none" }}
              >
                {f.properties.label ?? `S${f.properties.index}`}
              </text>
            )}
            {layer === "lobby" && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={8} fill="#0369a1"
                style={{ pointerEvents: "none" }}
              >
                Lobby
              </text>
            )}
            {layer === "corridor" && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={8} fill="#1d4ed8"
                style={{ pointerEvents: "none" }}
              >
                {`Corridor  ${f.properties.width_m ?? 1.8}m`}
              </text>
            )}
            {isBalcony && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={7} fill="#15803d"
                style={{ pointerEvents: "none" }}
              >
                Balcony
              </text>
            )}
            {isUnit && (
              <>
                <text
                  x={cx} y={cy - 7}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={9} fontWeight="600" fill="#1e293b"
                  style={{ pointerEvents: "none" }}
                >
                  {f.properties.unit_type}
                </text>
                <text
                  x={cx} y={cy + 6}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={8} fill="#374151"
                  style={{ pointerEvents: "none" }}
                >
                  {f.properties.carpet_area_sqm != null
                    ? `${Math.round(f.properties.carpet_area_sqm)} m²`
                    : ""}
                </text>
                {/* Ventilation warning — red dot if §13.1.11 check fails */}
                {f.properties.ventilation_ok === false && (
                  <circle
                    cx={cx + 14} cy={cy - 12}
                    r={4} fill="#ef4444" opacity={0.9}
                    style={{ pointerEvents: "none" }}
                  />
                )}
              </>
            )}
          </g>
        );
      })}
    </g>
  );
}

// ─── Debug geometry overlay ────────────────────────────────────────────────────
/**
 * Renders the 5 placement-debug GeoJSON layers behind the architecture layout.
 * Memoised so it only re-renders when the GeoJSON or transform actually changes.
 * Handles both Polygon and MultiPolygon geometries (leftover_polygon is often
 * a MultiPolygon when multiple disconnected residual areas exist).
 */
const DebugLayers = memo(function DebugLayers({
  debugGeoJson,
  viewTransform,
}: {
  debugGeoJson: PlacementDebugGeoJson;
  viewTransform: ViewTransform;
}) {
  const sorted = useMemo(() => {
    return [...debugGeoJson.features].sort((a, b) => {
      const ai = DEBUG_RENDER_ORDER.indexOf(a.properties.layer);
      const bi = DEBUG_RENDER_ORDER.indexOf(b.properties.layer);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
  }, [debugGeoJson.features]);

  return (
    <g style={{ pointerEvents: "none" }}>
      {sorted.flatMap((f, fi) => {
        const style = DEBUG_LAYER_STYLE[f.properties.layer] ?? {
          fill: "none", stroke: "#888", strokeWidth: 1,
        };

        if (f.geometry.type === "Polygon") {
          const d = featureToPath(
            f.geometry as { type: "Polygon"; coordinates: number[][][] },
            viewTransform,
          );
          if (!d) return [];
          return [
            <path
              key={`dbg-${fi}`}
              d={d}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={style.strokeWidth}
              strokeDasharray={style.strokeDasharray}
            />,
          ];
        }

        if (f.geometry.type === "MultiPolygon") {
          // MultiPolygon: iterate each polygon component
          const mpCoords = f.geometry.coordinates as number[][][][];
          return mpCoords.flatMap((polyCoords, pi) => {
            const d = featureToPath(
              { type: "Polygon", coordinates: polyCoords },
              viewTransform,
            );
            if (!d) return [];
            return [
              <path
                key={`dbg-${fi}-${pi}`}
                d={d}
                fill={style.fill}
                stroke={style.stroke}
                strokeWidth={style.strokeWidth}
                strokeDasharray={style.strokeDasharray}
              />,
            ];
          });
        }

        return [];
      })}
    </g>
  );
});

// ─── Core overlay layers ──────────────────────────────────────────────────────

const CORE_OVERLAY_STYLE: Record<string, { fill: string; stroke: string; strokeWidth: number; strokeDasharray?: string }> = {
  lift:     { fill: "rgba(30, 41, 59, 0.85)", stroke: "#0f172a", strokeWidth: 1.5 },
  stair:    { fill: "url(#stairHatch)",        stroke: "#64748b", strokeWidth: 1.2 },
  lobby:    { fill: "rgba(6, 182, 212, 0.15)", stroke: "#06b6d4", strokeWidth: 1 },
  corridor: { fill: "rgba(241, 245, 249, 0.6)", stroke: "#94a3b8", strokeWidth: 1 },
  core:     { fill: "rgba(226, 232, 240, 0.5)", stroke: "#64748b", strokeWidth: 1.5, strokeDasharray: "4 2" },
};

const GRAPH_NODE_COLOR: Record<string, string> = {
  LOBBY: "#06b6d4",
  LIFT: "#1e293b",
  STAIR: "#64748b",
  CORRIDOR: "#94a3b8",
  CORRIDOR_END: "#ef4444",
};

/**
 * Renders the circulation-core GeoJSON features + optional graph overlay.
 */
const CoreOverlayLayers = memo(function CoreOverlayLayers({
  layout,
  graph,
  corridorCenterline,
  viewTransform,
  showGraph,
  layerVisibility,
}: {
  layout: FloorPlanLayout;
  graph: { nodes: FloorCoreGraphNode[]; edges: FloorCoreGraphEdge[] };
  corridorCenterline?: { type: "LineString"; coordinates: number[][] } | null;
  viewTransform: ViewTransform;
  showGraph: boolean;
  layerVisibility: Record<string, boolean>;
}) {
  // Render order: core → corridor → lobby → stair → lift (back to front)
  const renderOrder = ["core", "corridor", "lobby", "stair", "lift"];

  const sorted = useMemo(() => {
    return [...layout.features]
      .filter((f) => {
        const layer = f.properties.layer;
        return layerVisibility[layer] !== false;
      })
      .sort((a, b) => {
        const al = renderOrder.indexOf(a.properties.layer);
        const bl = renderOrder.indexOf(b.properties.layer);
        return (al === -1 ? 99 : al) - (bl === -1 ? 99 : bl);
      });
  }, [layout.features, layerVisibility]);

  // Build node lookup for graph edges
  const nodeMap = useMemo(() => {
    const m = new Map<string, FloorCoreGraphNode>();
    for (const n of graph.nodes) m.set(n.id, n);
    return m;
  }, [graph.nodes]);

  return (
    <g style={{ pointerEvents: "none" }}>
      {/* Core geometry features */}
      {sorted.map((f, fi) => {
        const layer = f.properties.layer;
        const style = CORE_OVERLAY_STYLE[layer] ?? { fill: "none", stroke: "#888", strokeWidth: 1 };

        if (f.geometry.type === "Polygon") {
          const d = featureToPath(
            f.geometry as { type: "Polygon"; coordinates: number[][][] },
            viewTransform,
          );
          if (!d) return null;
          return (
            <path
              key={`core-${fi}`}
              d={d}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={style.strokeWidth}
              strokeDasharray={style.strokeDasharray}
            />
          );
        }

        if ((f.geometry as { type: string }).type === "MultiPolygon") {
          const mpCoords = (f.geometry as unknown as { coordinates: number[][][][] }).coordinates;
          return mpCoords.map((polyCoords, pi) => {
            const d = featureToPath({ type: "Polygon", coordinates: polyCoords }, viewTransform);
            if (!d) return null;
            return (
              <path
                key={`core-${fi}-${pi}`}
                d={d}
                fill={style.fill}
                stroke={style.stroke}
                strokeWidth={style.strokeWidth}
                strokeDasharray={style.strokeDasharray}
              />
            );
          });
        }
        return null;
      })}

      {/* Corridor centerline */}
      {corridorCenterline && corridorCenterline.coordinates.length >= 2 && (
        <path
          d={
            corridorCenterline.coordinates
              .map(([x, y], i) => {
                const [px, py] = projectPosition([x, y], viewTransform);
                return `${i === 0 ? "M" : "L"}${px},${py}`;
              })
              .join(" ")
          }
          fill="none"
          stroke="#06b6d4"
          strokeWidth={1}
          strokeDasharray="4 2"
          opacity={0.7}
        />
      )}

      {/* Graph overlay */}
      {showGraph && (
        <g>
          {/* Edges */}
          {graph.edges.map((e, ei) => {
            const fromNode = nodeMap.get(e.from);
            const toNode = nodeMap.get(e.to);
            if (!fromNode || !toNode) return null;
            const [x1, y1] = projectPosition(fromNode.centroid, viewTransform);
            const [x2, y2] = projectPosition(toNode.centroid, viewTransform);
            return (
              <g key={`ge-${ei}`}>
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#94a3b8" strokeWidth={0.8} strokeDasharray="2 2" opacity={0.6}
                />
                {e.distance_m > 0 && (
                  <text
                    x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 3}
                    fontSize={7} fill="#64748b" textAnchor="middle"
                  >
                    {e.distance_m.toFixed(1)}m
                  </text>
                )}
              </g>
            );
          })}
          {/* Nodes */}
          {graph.nodes.map((n) => {
            const [cx, cy] = projectPosition(n.centroid, viewTransform);
            const color = GRAPH_NODE_COLOR[n.type] ?? "#888";
            return (
              <g key={`gn-${n.id}`}>
                <circle cx={cx} cy={cy} r={3} fill={color} stroke="#fff" strokeWidth={0.5} />
                <text x={cx} y={cy - 5} fontSize={6} fill={color} textAnchor="middle" fontWeight={600}>
                  {n.id}
                </text>
              </g>
            );
          })}
        </g>
      )}
    </g>
  );
});

// ─── Placement diagnostics panel helpers ──────────────────────────────────────

function MetricRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-slate-50 bg-white px-3 py-2 text-xs shadow-sm">
      <span className="text-slate-500 font-medium">{label}</span>
      <div className="text-right">
        <span className="font-bold text-slate-900">{value}</span>
        {hint && <div className="text-[9px] text-slate-400 mt-0.5">{hint}</div>}
      </div>
    </div>
  );
}

/**
 * Shows the 8 placement quality metrics with GDCR violation highlights.
 *
 * Warnings triggered:
 *   - efficiency < 60 %  → amber warning
 *   - cop_min_dimension_m > 0 and < 6 m  → red GDCR violation
 */
function PlacementDiagnosticsPanel({ metrics }: { metrics: PlacementDebugMetrics }) {
  const efficiencyPct  = metrics.envelope_area_sqft > 0
    ? (metrics.footprint_area_sqft / metrics.envelope_area_sqft) * 100
    : 0;
  const lowEfficiency  = efficiencyPct < 60;
  const copViolation   = metrics.cop_min_dimension_m > 0 && metrics.cop_min_dimension_m < 6;
  const hasIssues      = lowEfficiency || copViolation;

  return (
    <div className="flex flex-col gap-3 overflow-y-auto p-4">
      {/* Section title + issue badge */}
      <div className="flex items-center justify-between">
        <h3 className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Placement Diagnostics
        </h3>
        {hasIssues && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-semibold text-amber-700">
            Issues found
          </span>
        )}
      </div>

      <div className="space-y-1">
        {/* 1 — Envelope area */}
        <MetricRow label="Envelope Area" value={`${metrics.envelope_area_sqft.toFixed(0)} sqft`} />

        {/* 2 — Footprint area */}
        <MetricRow label="Footprint Area" value={`${metrics.footprint_area_sqft.toFixed(0)} sqft`} />

        {/* Efficiency ratio — warn if < 60 % */}
        <div
          className={`flex items-center justify-between rounded px-2 py-1.5 text-xs ${
            lowEfficiency ? "bg-amber-50" : "bg-neutral-50"
          }`}
        >
          <div className="flex items-center gap-1">
            {lowEfficiency && <span className="text-amber-500">⚠</span>}
            <span className={lowEfficiency ? "font-medium text-amber-700" : "text-neutral-600"}>
              Efficiency Ratio
            </span>
          </div>
          <div className="text-right">
            <span className={`font-semibold ${lowEfficiency ? "text-amber-700" : "text-neutral-900"}`}>
              {efficiencyPct.toFixed(1)}%
            </span>
            {lowEfficiency && (
              <div className="text-[9px] text-amber-600">below 60% threshold</div>
            )}
          </div>
        </div>

        {/* 3 — Leftover area */}
        <MetricRow label="Leftover Area" value={`${metrics.leftover_area_sqft.toFixed(0)} sqft`} />

        {/* 4 — Leftover compactness */}
        <MetricRow
          label="Leftover Compactness"
          value={metrics.leftover_compactness_score.toFixed(3)}
          hint="0 = irregular  ·  1 = circle"
        />

        {/* 5 — Road frontage */}
        <MetricRow label="Road Frontage" value={`${metrics.road_frontage_length_m.toFixed(1)} m`} />

        {/* 7 — COP area */}
        <MetricRow label="COP Area" value={`${metrics.cop_area_sqft.toFixed(0)} sqft`} />

        {/* 8 — COP min dimension — red if GDCR < 6 m violated */}
        <div
          className={`flex items-center justify-between rounded px-2 py-1.5 text-xs ${
            copViolation ? "bg-red-50" : "bg-neutral-50"
          }`}
        >
          <div className="flex items-center gap-1">
            {copViolation && <span className="text-red-500">✕</span>}
            <span className={copViolation ? "font-semibold text-red-700" : "text-neutral-600"}>
              COP Min Dimension
            </span>
          </div>
          <div className="text-right">
            <span className={`font-semibold ${copViolation ? "text-red-700" : "text-neutral-900"}`}>
              {metrics.cop_min_dimension_m.toFixed(2)} m
            </span>
            {copViolation && (
              <div className="text-[9px] text-red-600">GDCR requires ≥ 6 m</div>
            )}
          </div>
        </div>

        {/* 6 — Tower orientation angles */}
        <div className="rounded bg-neutral-50 px-2 py-1.5">
          <div className="mb-1 text-[10px] text-neutral-500">Tower Orientations</div>
          <div className="flex flex-wrap gap-1">
            {metrics.tower_orientation_angles_deg.length === 0 ? (
              <span className="text-[9px] text-neutral-400">—</span>
            ) : (
              metrics.tower_orientation_angles_deg.map((a, i) => (
                <span
                  key={i}
                  className="rounded bg-blue-100 px-1.5 py-0.5 font-mono text-[9px] text-blue-700"
                >
                  T{i + 1}: {a.toFixed(1)}°
                </span>
              ))
            )}
          </div>
        </div>

        {/* Towers placed */}
        <MetricRow label="Towers Placed" value={String(metrics.n_towers_placed)} />
      </div>

      {/* GDCR reference note */}
      {copViolation && (
        <div className="rounded bg-red-50 p-2 text-[9px] text-red-700">
          GDCR §8.3 — Common open plot must have at least one dimension ≥ 6 m.
        </div>
      )}
    </div>
  );
}

// ─── GDCR compliance badge ──────────────────────────────────────────────────
function ComplianceBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs ${ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-green-500" : "bg-red-500"}`} />
      {label}
    </div>
  );
}

// ─── Unit detail panel ────────────────────────────────────────────────────────
function UnitDetailPanel({
  unit,
  onClose,
}: {
  unit: SelectedUnitInfo;
  onClose: () => void;
}) {
  const TYPE_COLOR: Record<string, string> = {
    "4BHK": "bg-red-50 text-red-700 border-red-200",
    "3BHK": "bg-amber-50 text-amber-700 border-amber-200",
    "2BHK": "bg-green-50 text-green-700 border-green-200",
    "1BHK": "bg-sky-50 text-sky-700 border-sky-200",
    "1RK":  "bg-purple-50 text-purple-700 border-purple-200",
    "STUDIO": "bg-purple-50 text-purple-700 border-purple-200",
  };
  const colorCls = TYPE_COLOR[unit.unitType ?? ""] ?? "bg-neutral-50 text-neutral-700 border-neutral-200";

  return (
    <div className="border-b border-neutral-200 bg-white p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`rounded border px-2 py-0.5 text-xs font-bold ${colorCls}`}>
            {unit.unitType ?? "Unit"}
          </span>
          <span className="text-xs font-semibold text-neutral-700">{unit.id}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-5 w-5 items-center justify-center rounded text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
          aria-label="Close unit details"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Area breakdown (RERA-compliant labelling) */}
      <div className="space-y-1.5">
        {[
          ["Built-up area",    unit.builtUpArea,  "Gross floor area including walls"],
          ["Carpet area",      unit.carpetArea,   "Usable internal floor area (RERA §2(k))"],
          ["RERA carpet area", unit.reraCarpet,   "Carpet + 50% of exclusive open areas"],
        ].map(([label, val, hint]) => (
          <div key={label as string} className="rounded bg-neutral-50 px-2.5 py-1.5">
            <div className="flex justify-between">
              <span className="text-[10px] text-neutral-500">{label as string}</span>
              <span className="text-xs font-semibold text-neutral-900">
                {val != null ? `${(val as number).toFixed(1)} m²` : "—"}
              </span>
            </div>
            <div className="mt-0.5 text-[9px] text-neutral-400">{hint as string}</div>
          </div>
        ))}

        {/* Plan efficiency */}
        {unit.efficiency != null && (
          <div className="flex items-center justify-between rounded border border-dashed border-neutral-200 px-2.5 py-1.5">
            <span className="text-[10px] text-neutral-500">Plan efficiency</span>
            <span className={`text-xs font-bold ${unit.efficiency >= 0.7 ? "text-green-700" : unit.efficiency >= 0.6 ? "text-amber-700" : "text-red-600"}`}>
              {(unit.efficiency * 100).toFixed(1)}%
            </span>
          </div>
        )}
      </div>

      {/* RERA note */}
      <p className="mt-2 text-[9px] leading-relaxed text-neutral-400">
        Carpet area as per RERA 2016 §2(k). Built-up area includes external walls and common-wall half-share.
      </p>

    </div>
  );
}

// ─── Metrics panel ─────────────────────────────────────────────────────────────
function FloorPlanMetricsPanel({ metrics }: { metrics: FloorPlanMetrics }) {
  const { gdcr } = metrics;

  const unitRows = Object.entries(metrics.unitTypeCounts).map(([type, count]) => (
    <div key={type} className="flex justify-between text-xs">
      <span className="text-neutral-600">{type}</span>
      <span className="font-medium">{count} / floor  ({count * metrics.nFloors} total)</span>
    </div>
  ));

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      {/* Floor plate */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Floor Plate
        </h3>
        <div className="grid grid-cols-2 gap-1.5">
          {[
            ["Length", `${metrics.floorLengthM.toFixed(1)} m`],
            ["Width",  `${metrics.floorWidthM.toFixed(1)} m`],
            ["Gross area", `${metrics.footprintSqm.toFixed(0)} m²`],
            ["Floors", `${metrics.nFloors}`],
            ["Height", `${metrics.buildingHeightM.toFixed(1)} m`],
            ["Storey ht.", `${metrics.storeyHeightM.toFixed(1)} m`],
          ].map(([k, v]) => (
            <div key={k} className="rounded bg-neutral-50 px-2 py-1.5 text-xs">
              <div className="text-neutral-500">{k}</div>
              <div className="font-semibold text-neutral-900">{v}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Area breakdown */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Area / Floor
        </h3>
        <div className="space-y-1">
          {[
            ["Core + Stair",     metrics.coreSqm,              "bg-slate-200"],
            ["Corridor",         metrics.corridorSqm,           "bg-blue-200"],
            ["FSI-exempt total", metrics.fsiExemptSqm ?? (metrics.coreSqm + metrics.corridorSqm), "bg-amber-100"],
            ["Net unit area",    metrics.unitAreaPerFloorSqm,   "bg-green-200"],
          ].map(([label, val, cls]) => (
            <div key={label as string} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <div className={`h-2.5 w-2.5 rounded-sm ${cls as string}`} />
                <span className="text-neutral-600">{label as string}</span>
              </div>
              <span className="font-medium">{(val as number).toFixed(0)} m²</span>
            </div>
          ))}
          {/* Balcony area (open-to-sky, FSI-exempt) */}
          {(metrics.balconySqmPerFloor ?? 0) > 0 && (
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <div className="h-2.5 w-2.5 rounded-sm bg-green-200 ring-1 ring-green-400 ring-offset-0" />
                <span className="text-neutral-600">Balconies (open, FSI-exempt)</span>
              </div>
              <span className="font-medium text-green-700">
                {(metrics.balconySqmPerFloor ?? 0).toFixed(0)} m²
              </span>
            </div>
          )}
          <div className="mt-1.5 flex items-center justify-between border-t border-neutral-200 pt-1.5 text-xs font-semibold">
            <span>Efficiency</span>
            <span className={metrics.efficiencyPct >= 65 ? "text-green-700" : "text-amber-700"}>
              {metrics.efficiencyPct.toFixed(1)}%
            </span>
          </div>
        </div>
      </section>

      {/* Unit mix */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Units
        </h3>
        <div className="space-y-1">
          {unitRows}
        </div>
      </section>

      {/* BUA / FSI */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          BUA / FSI
        </h3>
        <div className="space-y-1">
          {[
            ["Net BUA (saleable)",  `${metrics.netBuaSqm.toFixed(0)} m²`],
            ["Gross BUA (permit)",  `${metrics.grossBuaSqm.toFixed(0)} m²`],
            ["FSI (net / saleable)",`${metrics.achievedFSINet.toFixed(3)}`],
            ["FSI (gross / permit)",`${metrics.achievedFSIGross.toFixed(3)}`],
          ].map(([k, v]) => (
            <div key={k as string} className="flex justify-between text-xs">
              <span className="text-neutral-600">{k as string}</span>
              <span className="font-medium text-neutral-900">{v as string}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 rounded bg-blue-50 p-2 text-[10px] text-blue-700">
          Net BUA = unit areas only. Corridor + core are common areas excluded from FSI calculation as per developer convention.
        </div>
      </section>

      {/* GDCR compliance */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          GDCR Compliance  <span className="normal-case font-normal text-neutral-400">(Part III)</span>
        </h3>
        <div className="flex flex-col gap-1">
          {/* §13.12.2 — Lift count */}
          <ComplianceBadge ok={gdcr.lift_ok}
            label={gdcr.lift_required
              ? `Lifts: ${gdcr.lift_provided} provided, ${gdcr.lift_required_by_units ?? gdcr.lift_required_by_height} required (§13.12.2)`
              : `Lift: not required (≤ 10 m)`} />
          {/* §13.12.2 — Fire lift */}
          {gdcr.fire_lift_required && (
            <ComplianceBadge ok={!!gdcr.fire_lift_ok}
              label={`Fire lift: ${gdcr.fire_lift_provided ? "provided" : "MISSING"} (required > 25 m)`} />
          )}
          {/* §13.12.3 — Lift landing */}
          {gdcr.lift_required && (
            <ComplianceBadge ok={!!gdcr.lift_landing_ok}
              label={`Lift landing: ${(gdcr.lift_landing_w_m ?? 0).toFixed(2)} m × ${(gdcr.lift_landing_d_m ?? 0).toFixed(1)} m (min 1.8 × 2.0 m)`} />
          )}
          {/* Table 13.2 — Stair width */}
          <ComplianceBadge ok={gdcr.stair_width_ok}
            label={`Stair width: ${gdcr.stair_width_m.toFixed(2)} m (min ${(gdcr.stair_width_required_m ?? 1.0).toFixed(2)} m, Table 13.2)`} />
          {/* Corridor */}
          <ComplianceBadge ok={gdcr.corridor_width_ok}
            label={`Corridor: ${gdcr.corridor_width_m.toFixed(1)} m (min 1.2 m)`} />
          {/* §13.1.7 — Clearances */}
          <ComplianceBadge ok={gdcr.clearance_habitable_ok}
            label={`Storey ht: ${gdcr.storey_height_m.toFixed(1)} m (habitable min 2.9 m §13.1.7)`} />
          <ComplianceBadge ok={!!gdcr.clearance_service_ok}
            label={`Service clearance: ${gdcr.storey_height_m.toFixed(1)} m (min 2.1 m corridor/stair)`} />
          {/* §13.1.11 — Ventilation */}
          <ComplianceBadge ok={!!gdcr.ventilation_ok}
            label={
              gdcr.ventilation_ok
                ? `Ventilation: all ${gdcr.ventilation_units_total ?? "—"} units pass (§13.1.11)`
                : `Ventilation: ${gdcr.ventilation_units_fail ?? "?"} unit(s) shortfall (§13.1.11 — window ≥ 1/6 floor area)`
            } />
          {/* §13.1.12 — Balconies */}
          {gdcr.balcony_provided && (
            <ComplianceBadge ok={true}
              label={`Balconies: ${gdcr.balcony_count} units — ${(gdcr.balcony_depth_m ?? 1.5).toFixed(1)} m depth (§13.1.12, FSI-exempt)`} />
          )}
        </div>
        <div className="mt-2 rounded bg-amber-50 p-2 text-[10px] text-amber-700">
          FSI exemptions (Part II §8.2.2): staircase, corridors, lift well, landing &amp; open balconies are excluded from FSI computation.
        </div>
      </section>
    </div>
  );
}

// ─── Floor core metrics panel ─────────────────────────────────────────────────

function FloorCoreMetricsPanel({
  data,
  layerVisibility,
  onToggleLayer,
}: {
  data: FloorCoreResponse;
  layerVisibility: Record<string, boolean>;
  onToggleLayer: (layer: string) => void;
}) {
  const { metrics, capacity, compliance } = data;

  const CORE_TYPE_COLOR: Record<string, string> = {
    POINT_CORE:       "bg-purple-50 text-purple-700 border-purple-200",
    SINGLE_CORRIDOR:  "bg-sky-50 text-sky-700 border-sky-200",
    DOUBLE_CORRIDOR:  "bg-blue-50 text-blue-700 border-blue-200",
    DOUBLE_CORE:      "bg-indigo-50 text-indigo-700 border-indigo-200",
  };
  const typeColor = CORE_TYPE_COLOR[metrics.core_type] ?? "bg-neutral-50 text-neutral-700 border-neutral-200";

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      {/* Layer toggles */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Layers
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {(["lift", "stair", "lobby", "corridor", "graph"] as const).map((layer) => (
            <button
              key={layer}
              type="button"
              onClick={() => onToggleLayer(layer)}
              className={`rounded border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                layerVisibility[layer] !== false
                  ? "border-neutral-300 bg-neutral-100 text-neutral-700"
                  : "border-neutral-200 bg-white text-neutral-400"
              }`}
            >
              {layer}
            </button>
          ))}
        </div>
      </section>

      {/* Core layout */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Core Layout
        </h3>
        <div className="mb-2">
          <span className={`rounded border px-2 py-0.5 text-xs font-bold ${typeColor}`}>
            {metrics.core_type.replace(/_/g, " ")}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {[
            ["Lifts", `${metrics.n_lifts}`],
            ["Stairs", `${metrics.n_stairs}`],
            ["Core area", `${metrics.core_area_sqm.toFixed(1)} m\u00B2`],
            ["Corridor area", `${metrics.corridor_area_sqm.toFixed(1)} m\u00B2`],
            ["Footprint", `${metrics.footprint_area_sqm.toFixed(0)} m\u00B2`],
          ].map(([k, v]) => (
            <div key={k} className="rounded bg-neutral-50 px-2 py-1.5 text-xs">
              <div className="text-neutral-500">{k}</div>
              <div className="font-semibold text-neutral-900">{v}</div>
            </div>
          ))}
        </div>
        {/* Circulation % bar */}
        <div className="mt-2">
          <div className="flex justify-between text-xs">
            <span className="text-neutral-500">Circulation %</span>
            <span className="font-semibold text-neutral-900">{metrics.circulation_pct.toFixed(1)}%</span>
          </div>
          <div className="mt-1 h-1.5 w-full rounded-full bg-neutral-100">
            <div
              className={`h-full rounded-full ${metrics.circulation_pct <= 25 ? "bg-green-500" : metrics.circulation_pct <= 35 ? "bg-amber-500" : "bg-red-500"}`}
              style={{ width: `${Math.min(metrics.circulation_pct, 100)}%` }}
            />
          </div>
        </div>
      </section>

      {/* Travel & separation */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Travel &amp; Separation
        </h3>
        <div className="space-y-1">
          <MetricRow
            label="Max travel distance"
            value={`${metrics.max_travel_distance_m.toFixed(1)} m`}
            hint={compliance.travel_distance_ok ? "Within NBC limit" : "Exceeds 22.5 m NBC limit"}
          />
          <MetricRow
            label="Stair separation"
            value={`${metrics.stair_separation_m.toFixed(1)} m`}
            hint={`Required: ${compliance.stair_separation_required_m.toFixed(1)} m (1/3 diagonal)`}
          />
        </div>
      </section>

      {/* Capacity */}
      {capacity && (
        <section>
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
            Capacity Estimates
          </h3>
          <div className="space-y-1">
            <MetricRow label="People per lift" value={capacity.people_per_lift.toFixed(0)} />
            <MetricRow label="Stair capacity" value={`${capacity.stair_capacity_persons_per_min.toFixed(0)} pers/min`} />
            <MetricRow label="Corridor density" value={`${capacity.corridor_density_persons_per_m.toFixed(2)} pers/m`} />
          </div>
        </section>
      )}

      {/* Compliance */}
      <section>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          NBC Compliance
        </h3>
        <div className="flex flex-col gap-1">
          <ComplianceBadge ok={compliance.corridor_width_ok} label="Corridor width" />
          <ComplianceBadge
            ok={compliance.travel_distance_ok}
            label={`Travel distance: ${compliance.travel_distance_max_m.toFixed(1)} m (max 22.5 m)`}
          />
          <ComplianceBadge
            ok={compliance.dead_end_ok}
            label={`Dead ends: ${compliance.dead_end_count} (max ${compliance.dead_end_max_m.toFixed(1)} m)`}
          />
          <ComplianceBadge
            ok={compliance.stair_separation_ok}
            label={`Stair sep: ${compliance.stair_separation_m.toFixed(1)} m (min ${compliance.stair_separation_required_m.toFixed(1)} m)`}
          />
        </div>

        {/* Violations */}
        {compliance.violations.length > 0 && (
          <div className="mt-2 space-y-1">
            {compliance.violations.map((v, i) => (
              <div key={i} className="rounded bg-red-50 px-2 py-1 text-[10px] text-red-700">
                {v}
              </div>
            ))}
          </div>
        )}

        {/* Warnings */}
        {compliance.warnings.length > 0 && (
          <div className="mt-2 space-y-1">
            {compliance.warnings.map((w, i) => (
              <div key={i} className="rounded bg-amber-50 px-2 py-1 text-[10px] text-amber-700">
                {w}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ─── Zoomable / draggable SVG viewer ─────────────────────────────────────────

type ZoomableSvgHandle = {
  fitInView: () => void;
  resetView: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
};

/** Parse the `width` and `height` attributes from a raw SVG string. */
function parseSvgDimensions(svgHtml: string): { w: number; h: number } {
  const wm = svgHtml.match(/\bwidth="([\d.]+)"/);
  const hm = svgHtml.match(/\bheight="([\d.]+)"/);
  return { w: wm ? parseFloat(wm[1]) : 1200, h: hm ? parseFloat(hm[1]) : 900 };
}

const ZoomableSvgViewer = forwardRef<ZoomableSvgHandle, { svgHtml: string }>(
  function ZoomableSvgViewer({ svgHtml }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
    const [dragging, setDragging] = useState(false);
    const lastPos = useRef({ x: 0, y: 0 });

    const fitInView = useCallback(() => {
      const el = containerRef.current;
      if (!el) return;
      const { width, height } = el.getBoundingClientRect();
      const { w, h } = parseSvgDimensions(svgHtml);
      const PAD = 32;
      const scale = Math.min((width - PAD * 2) / w, (height - PAD * 2) / h);
      setTransform({
        scale,
        x: (width - w * scale) / 2,
        y: (height - h * scale) / 2,
      });
    }, [svgHtml]);

    const resetView = useCallback(() => setTransform({ x: 0, y: 0, scale: 1 }), []);
    const zoomIn    = useCallback(() => setTransform(t => ({ ...t, scale: Math.min(t.scale * 1.25, 20) })), []);
    const zoomOut   = useCallback(() => setTransform(t => ({ ...t, scale: Math.max(t.scale / 1.25, 0.05) })), []);

    useImperativeHandle(ref, () => ({ fitInView, resetView, zoomIn, zoomOut }), [fitInView, resetView, zoomIn, zoomOut]);

    // Auto-fit whenever the SVG changes
    useEffect(() => {
      const id = setTimeout(fitInView, 60);
      return () => clearTimeout(id);
    }, [fitInView]);

    // Wheel zoom — must be non-passive to call preventDefault
    const onWheel = useCallback((e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const rect = containerRef.current!.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setTransform(prev => {
        const newScale = Math.max(0.05, Math.min(20, prev.scale * factor));
        const r = newScale / prev.scale;
        return { scale: newScale, x: mx - r * (mx - prev.x), y: my - r * (my - prev.y) };
      });
    }, []);

    useEffect(() => {
      const el = containerRef.current;
      if (!el) return;
      el.addEventListener("wheel", onWheel, { passive: false });
      return () => el.removeEventListener("wheel", onWheel);
    }, [onWheel]);

    // Drag to pan
    const onMouseDown = useCallback((e: React.MouseEvent) => {
      if (e.button !== 0) return;
      setDragging(true);
      lastPos.current = { x: e.clientX, y: e.clientY };
    }, []);

    const onMouseMove = useCallback((e: React.MouseEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      lastPos.current = { x: e.clientX, y: e.clientY };
      setTransform(prev => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
    }, [dragging]);

    const stopDrag = useCallback(() => setDragging(false), []);

    return (
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden select-none"
        style={{ cursor: dragging ? "grabbing" : "grab" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
      >
        <div
          style={{
            transformOrigin: "0 0",
            transform: `translate(${transform.x}px,${transform.y}px) scale(${transform.scale})`,
            display: "inline-block",
            lineHeight: 0,
          }}
          dangerouslySetInnerHTML={{ __html: svgHtml }}
        />
      </div>
    );
  }
);

// ─── Main component ────────────────────────────────────────────────────────────

type FloorPlanningViewProps = {
  geometryModel: GeometryModel | null;
  /** Workspace flow: back goes to plot map + inputs instead of legacy site step. */
  onBackFromFloor?: () => void;
  backFromFloorLabel?: string;
};

export function FloorPlanningView({
  geometryModel,
  onBackFromFloor,
  backFromFloorLabel,
}: FloorPlanningViewProps) {
  const canvasRef           = useRef<SvgCanvasHandle>(null);
  const svgWrapperRef       = useRef<HTMLDivElement>(null);
  const selectedTowerIndex  = usePlannerStore((s) => s.selectedTowerIndex);
  const setPlanningStep     = usePlannerStore((s) => s.setPlanningStep);
  const setSelectedTowerIndex = usePlannerStore((s) => s.setSelectedTowerIndex);
  const setSelectedUnit     = usePlannerStore((s) => s.setSelectedUnit);
  const selectedUnit        = usePlannerStore((s) => s.selectedUnit);
  const scenarios           = usePlannerStore((s) => s.scenarios);
  const activeScenarioId    = usePlannerStore((s) => s.activeScenarioId);
  const inputs              = usePlannerStore((s) => s.inputs);

  const goToSitePlan = useCallback(() => {
    if (onBackFromFloor) {
      onBackFromFloor();
      return;
    }
    setPlanningStep("site");
    setSelectedTowerIndex(null);
    setSelectedUnit(null);
  }, [onBackFromFloor, setPlanningStep, setSelectedTowerIndex, setSelectedUnit]);

  const scenario    = scenarios.find((s) => s.id === activeScenarioId);
  const metrics     = (scenario?.planResultSummary as { metrics?: Record<string, unknown> })?.metrics ?? {};

  const { mutate: requestFloorPlan, data: floorPlanData, isPending, isError, error } = useFloorPlan();

  // AI floor plan is the primary mode
  const { mutate: requestAIFloorPlan, data: aiFloorPlanData, isPending: aiPending, isError: aiIsError, error: aiError } = useAIFloorPlan();

  const {
    mutate: requestPreviewImage,
    isPending: previewImagePending,
    isError: previewImageIsError,
    error: previewImageError,
    reset: resetPreviewImage,
  } = useFloorPlanPreviewImage();

  const [previewImageModalOpen, setPreviewImageModalOpen] = useState(false);
  const [previewImageSrc, setPreviewImageSrc] = useState<string | null>(null);

  // Debug overlay — off by default, only visible when debug data is present
  const [showDebug, setShowDebug] = useState(false);

  // Core overlay state
  const [showCoreOverlay, setShowCoreOverlay] = useState(false);
  const { mutate: requestFloorCore, data: floorCoreData, isPending: corePending } = useFloorCore();
  type RightPanelTab = "metrics" | "diagnostics" | "core";
  const [activeRightPanel, setActiveRightPanel] = useState<RightPanelTab>("metrics");
  const [coreLayerVisibility, setCoreLayerVisibility] = useState<Record<string, boolean>>({
    lift: true, stair: true, lobby: true, corridor: true, graph: false,
  });
  const toggleCoreLayer = useCallback((layer: string) => {
    setCoreLayerVisibility((prev) => ({ ...prev, [layer]: !prev[layer] }));
  }, []);

  // ── Select tower geometry ────────────────────────────────────────────────────
  const grouped       = geometryModel ? groupFeaturesByLayer(geometryModel) : null;
  const towerFeatures = grouped?.towerFootprints ?? [];
  const selectedTower = selectedTowerIndex != null ? towerFeatures[selectedTowerIndex] ?? null : null;

  // Build a single-feature GeometryModel scoped to the selected tower for SvgCanvas bounds
  const towerModel: GeometryModel | null = useMemo(() => {
    if (!selectedTower) return null;
    return { features: [selectedTower] };
  }, [selectedTower]);

  // Also include floor plan features in the bounds model once data arrives
  const canvasModel: GeometryModel | null = useMemo(() => {
    if (!selectedTower) return null;
    if (!floorPlanData?.layout) return { features: [selectedTower] };

    // Convert FloorPlanFeature → GeometryFeature for bounds computation
    const fpFeatures: GeometryFeature[] = floorPlanData.layout.features.map((f) => ({
      id: f.id,
      layer: "towerFootprints" as const,
      kind: "polygon" as const,
      geometry: f.geometry,
      properties: f.properties as unknown as Record<string, unknown>,
    }));
    return { features: [...fpFeatures, selectedTower] };
  }, [selectedTower, floorPlanData]);

  // ── Auto-request AI floor plan when tower is selected ────────────────────────
  useEffect(() => {
    if (!selectedTower) return;
    if (selectedTower.geometry.type !== "Polygon") return;

    const props = selectedTower.properties;
    const n_floors         = (props.floors as number)  ?? 10;
    const building_height  = (props.height as number)  ?? n_floors * 3;
    const plot_area_sqm    = (metrics.plotAreaSqm as number) ?? 0;

    requestAIFloorPlan({
      footprint: selectedTower.geometry as { type: "Polygon"; coordinates: number[][][] },
      n_floors,
      building_height_m: building_height,
      units_per_core: inputs.unitsPerCore ?? 4,
      segment: inputs.segment ?? "mid",
      unit_mix: inputs.unitMix ?? ["2BHK", "3BHK"],
      storey_height_m: 3.0,
      plot_area_sqm,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTower?.id]);

  // ── Log placement debug metrics to console whenever they arrive ──────────────
  useEffect(() => {
    const m = floorPlanData?.placement_debug_metrics;
    if (!m) return;
    console.group(`[PlacementDebug] Tower T${(selectedTowerIndex ?? 0) + 1}`);
    console.table({
      "Envelope area (sqft)":          m.envelope_area_sqft,
      "Footprint area (sqft)":         m.footprint_area_sqft,
      "Leftover area (sqft)":          m.leftover_area_sqft,
      "Leftover compactness (0–1)":    m.leftover_compactness_score,
      "Road frontage (m)":             m.road_frontage_length_m,
      "COP area (sqft)":               m.cop_area_sqft,
      "COP min dimension (m)":         m.cop_min_dimension_m,
      "Footprint utilisation (%)":     m.footprint_utilization_pct,
      "Leftover utilisation (%)":      m.leftover_utilization_pct,
      "Towers placed":                 m.n_towers_placed,
    });
    console.log(
      "Tower orientation angles (deg):",
      m.tower_orientation_angles_deg.map((a) => `T${m.tower_orientation_angles_deg.indexOf(a) + 1}: ${a.toFixed(2)}°`).join("  "),
    );
    if (floorPlanData?.placement_debug_geojson?.metadata) {
      console.log("GeoJSON metadata:", floorPlanData.placement_debug_geojson.metadata);
    }
    console.groupEnd();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [floorPlanData?.placement_debug_metrics]);

  // ── Guard: no tower selected (pick here when not auto-selected) ─────────────
  if (selectedTowerIndex == null || !selectedTower) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 rounded border border-dashed border-neutral-300 bg-neutral-50 p-8">
        <p className="text-sm text-neutral-600">
          {towerFeatures.length > 0
            ? "Select a tower to generate the AI floor plan."
            : "No tower footprints in this layout."}
        </p>
        {towerFeatures.length > 0 && (
          <div className="flex flex-wrap justify-center gap-2">
            {towerFeatures.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setSelectedTowerIndex(i)}
                className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-2 text-sm font-medium text-violet-800 hover:bg-violet-100"
              >
                Tower {i + 1}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          onClick={goToSitePlan}
          className="rounded bg-neutral-200 px-3 py-1.5 text-sm font-medium text-neutral-800 hover:bg-neutral-300"
        >
          {backFromFloorLabel ?? "Back to Site Plan"}
        </button>
      </div>
    );
  }

  const towerId = (selectedTower.properties.towerId as string) ?? `T${selectedTowerIndex + 1}`;
  const towerFloors = (selectedTower.properties.floors as number) ?? "—";

  const liftCapped    = floorPlanData?.metrics?.gdcr?.lift_capped;
  const liftCapReason = floorPlanData?.metrics?.gdcr?.lift_cap_reason;

  // ── SVG export ────────────────────────────────────────────────────────────
  const exportSvg = useCallback(() => {
    const svgEl = canvasRef.current?.getSvgElement();
    if (!svgEl || !floorPlanData?.metrics) return;

    // Clone so we can add metadata without mutating live DOM
    const clone = svgEl.cloneNode(true) as SVGSVGElement;

    // Add title / description for accessibility and archival
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `Tower ${towerId} — Typical Floor Plan`;
    clone.insertBefore(title, clone.firstChild);

    const desc = document.createElementNS("http://www.w3.org/2000/svg", "desc");
    const m = floorPlanData.metrics;
    desc.textContent = [
      `Tower: ${towerId}`,
      `Floors: ${m.nFloors}`,
      `Height: ${m.buildingHeightM.toFixed(1)} m`,
      `Net BUA: ${m.netBuaSqm.toFixed(0)} m²`,
      `Units/floor: ${m.nUnitsPerFloor}`,
      `Efficiency: ${m.efficiencyPct.toFixed(1)}%`,
      `Generated: ${new Date().toISOString()}`,
    ].join(" | ");
    clone.insertBefore(desc, clone.firstChild);

    // Serialise and trigger download
    const serialiser = new XMLSerializer();
    const svgStr = serialiser.serializeToString(clone);
    const blob = new Blob(
      [`<?xml version="1.0" encoding="UTF-8"?>\n`, svgStr],
      { type: "image/svg+xml;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `floor-plan-${towerId}-${m.nFloors}fl.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [canvasRef, floorPlanData, towerId]);

  // ── Layout ───────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Canvas — left 70% */}
      <div className="relative flex flex-1 flex-col bg-white">
        {/* Breadcrumb / top bar */}
        <div className="flex items-center justify-between border-b border-neutral-200 bg-white px-3 py-2">
          <div className="flex items-center gap-2">
            {/* Breadcrumb */}
            <button
              type="button"
              onClick={goToSitePlan}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              {backFromFloorLabel ?? "Site Plan"}
            </button>
            <span className="text-neutral-300">/</span>
            <span className="rounded-sm bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-800">
              AI Floor Plan
            </span>
            <span className="text-xs text-neutral-600">Tower {towerId}</span>
            {towerFeatures.length > 1 && (
              <span className="ml-2 flex flex-wrap items-center gap-1">
                {towerFeatures.map((_, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setSelectedTowerIndex(i);
                      setSelectedUnit(null);
                    }}
                    className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                      i === selectedTowerIndex
                        ? "bg-violet-200 text-violet-900"
                        : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
                    }`}
                  >
                    T{i + 1}
                  </button>
                ))}
              </span>
            )}
            {towerFloors && (
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                {towerFloors} fl
              </span>
            )}
            {/* Lift cap warning */}
            {liftCapped && (
              <span
                className="ml-1 cursor-help rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700"
                title={liftCapReason ?? "Lift count capped — floor plate too short for GDCR requirement"}
              >
                ⚠ Lifts capped
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => canvasRef.current?.fitInView()}
              className="rounded px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-100"
            >
              Fit
            </button>
            <button
              type="button"
              onClick={() => canvasRef.current?.resetView()}
              className="rounded px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-100"
            >
              Reset
            </button>
            {/* Export SVG — only available once floor plan is loaded */}
            {floorPlanData?.layout && (
              <button
                type="button"
                onClick={exportSvg}
                className="flex items-center gap-1 rounded border border-neutral-200 bg-white px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 hover:border-neutral-300"
                title="Download floor plan as SVG"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                SVG
              </button>
            )}
            {/* Placement debug toggle — only shown when debug data is available */}
            {floorPlanData?.placement_debug_metrics && (
              <button
                type="button"
                onClick={() => setShowDebug((v) => !v)}
                title={showDebug ? "Hide placement debug overlay" : "Show placement debug overlay"}
                className={`flex items-center gap-1 rounded border px-2 py-1 text-xs font-medium transition-colors ${
                  showDebug
                    ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
                    : "border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-50 hover:border-neutral-300"
                }`}
              >
                {/* Target / crosshair icon */}
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="3" strokeWidth={2} />
                  <path strokeLinecap="round" strokeWidth={2}
                    d="M12 2v4m0 12v4M2 12h4m12 0h4" />
                </svg>
                {showDebug ? "Hide Debug" : "Show Placement Debug"}
              </button>
            )}

            {/* Regenerate AI floor plan + optional text-to-image preview (separate API) */}
            {selectedTower && !aiPending && aiFloorPlanData && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    if (!selectedTower || selectedTower.geometry.type !== "Polygon") return;
                    const nFloors = (selectedTower.properties.floors as number) ?? 10;
                    requestAIFloorPlan({
                      footprint: selectedTower.geometry as { type: "Polygon"; coordinates: number[][][] },
                      n_floors: nFloors,
                      building_height_m: (selectedTower.properties.height as number) ?? nFloors * 3,
                      units_per_core: inputs.unitsPerCore ?? 4,
                      segment: inputs.segment ?? "mid",
                      unit_mix: inputs.unitMix ?? ["2BHK", "3BHK"],
                      storey_height_m: 3.0,
                      plot_area_sqm: (metrics.plotAreaSqm as number) ?? 0,
                    });
                  }}
                  className="flex items-center gap-1 rounded border border-violet-200 bg-violet-50 px-2 py-1 text-[10px] font-medium text-violet-700 hover:bg-violet-100"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
                  </svg>
                  Regenerate
                </button>
                <button
                  type="button"
                  disabled={previewImagePending}
                  title="Generate a stylized preview image from a detailed text prompt (Hugging Face). Requires HUGGINGFACE_API_TOKEN on the server."
                  onClick={() => {
                    if (!selectedTower || selectedTower.geometry.type !== "Polygon") return;
                    resetPreviewImage();
                    const nFloors = (selectedTower.properties.floors as number) ?? 10;
                    requestPreviewImage(
                      {
                        footprint: selectedTower.geometry as { type: "Polygon"; coordinates: number[][][] },
                        n_floors: nFloors,
                        building_height_m: (selectedTower.properties.height as number) ?? nFloors * 3,
                        units_per_core: inputs.unitsPerCore ?? 4,
                        segment: inputs.segment ?? "mid",
                        unit_mix: inputs.unitMix ?? ["2BHK", "3BHK"],
                        storey_height_m: 3.0,
                        plot_area_sqm: (metrics.plotAreaSqm as number) ?? 0,
                        design_notes: aiFloorPlanData.design_notes ?? "",
                        ai_metrics: aiFloorPlanData.metrics,
                      },
                      {
                        onSuccess: (res) => {
                          setPreviewImageSrc(`data:${res.mime_type};base64,${res.image_base64}`);
                          setPreviewImageModalOpen(true);
                        },
                      },
                    );
                  }}
                  className="flex items-center gap-1 rounded border border-sky-200 bg-sky-50 px-2 py-1 text-[10px] font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-50"
                >
                  {previewImagePending ? (
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border border-sky-400 border-t-sky-700" />
                  ) : (
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3A1.5 1.5 0 001.5 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
                    </svg>
                  )}
                  Image preview
                </button>
                {previewImageIsError && (
                  <span className="max-w-[200px] truncate text-[10px] text-red-600" title={previewImageError?.message}>
                    {previewImageError?.message ?? "Image preview failed"}
                  </span>
                )}
              </>
            )}
          </div>
        </div>

        {/* SVG canvas */}
        <div ref={svgWrapperRef} className="relative flex-1">
          {canvasModel && (
            <SvgCanvas geometryModel={canvasModel} canvasRef={canvasRef}>
              {({ viewTransform }) => (
                <g>
                  {/* SVG defs for stair hatch */}
                  <defs>
                    <pattern id="stairHatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                      <line x1="0" y1="0" x2="0" y2="6" stroke="#64748b" strokeWidth="1" strokeOpacity="0.35" />
                    </pattern>
                  </defs>

                  {/* Debug geometry overlay — rendered below architecture layers */}
                  {showDebug && floorPlanData?.placement_debug_geojson && (
                    <DebugLayers
                      debugGeoJson={floorPlanData.placement_debug_geojson}
                      viewTransform={viewTransform}
                    />
                  )}

                  {/* Core overlay — between debug and floor plan (below units) */}
                  {showCoreOverlay && floorCoreData?.layout && (
                    <CoreOverlayLayers
                      layout={floorCoreData.layout}
                      graph={floorCoreData.graph}
                      corridorCenterline={floorCoreData.corridor_centerline}
                      viewTransform={viewTransform}
                      showGraph={coreLayerVisibility.graph}
                      layerVisibility={coreLayerVisibility}
                    />
                  )}

                  {/* Floor plan layout */}
                  {floorPlanData?.layout && (
                    <FloorPlanLayers
                      layout={floorPlanData.layout}
                      viewTransform={viewTransform}
                      onUnitClick={(f) =>
                        setSelectedUnit({
                          id: f.id,
                          unitType: f.properties.unit_type,
                          carpetArea: f.properties.carpet_area_sqm,
                          builtUpArea: f.properties.area_sqm,
                          reraCarpet: f.properties.rera_carpet_sqm,
                          efficiency: f.properties.carpet_area_sqm && f.properties.area_sqm
                            ? f.properties.carpet_area_sqm / f.properties.area_sqm
                            : undefined,
                          unitWidthM: f.properties.width_m,
                          unitDepthM: f.properties.depth_m,
                        })
                      }
                    />
                  )}
                </g>
              )}
            </SvgCanvas>
          )}

          {/* AI Floor Plan — primary content */}
          {(aiFloorPlanData?.svg_blueprint || aiFloorPlanData?.architectural_image || aiFloorPlanData?.presentation_image) && !aiPending && (
            <div className="absolute inset-0 z-10 flex flex-col bg-white">
              {/* Header bar */}
              <div className="flex items-center gap-2 border-b border-violet-200 bg-violet-50 px-3 py-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-700">AI Floor Plan</span>
                {aiFloorPlanData.design_notes && (
                  <span className="text-[10px] text-violet-600">{aiFloorPlanData.design_notes}</span>
                )}
                {(aiFloorPlanData.architectural_image || aiFloorPlanData.presentation_image) && (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
                    DALL-E 3
                  </span>
                )}
              </div>

              {/* Image viewer with toggle */}
              <div className="flex-1 min-h-0">
                <ZoomableImageViewer
                  architecturalImage={aiFloorPlanData.architectural_image ?? null}
                  presentationImage={aiFloorPlanData.presentation_image ?? null}
                  svgFallback={aiFloorPlanData.svg_blueprint ?? null}
                />
              </div>

              {/* AI metrics summary footer */}
              {aiFloorPlanData.metrics && (
                <div className="flex items-center gap-4 border-t border-violet-200 bg-violet-50 px-3 py-1.5 text-[10px] text-violet-700">
                  <span>Units/floor: {aiFloorPlanData.metrics.nUnitsPerFloor}</span>
                  <span>Efficiency: {aiFloorPlanData.metrics.efficiencyPct}%</span>
                  <span>Net BUA: {aiFloorPlanData.metrics.netBuaSqm?.toFixed(0)} m²</span>
                  <span>Lifts: {aiFloorPlanData.metrics.nLifts}</span>
                  <span>Stairs: {aiFloorPlanData.metrics.nStairs}</span>
                </div>
              )}
            </div>
          )}

          {/* AI loading overlay */}
          {aiPending && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90">
              <div className="flex flex-col items-center gap-3">
                <div className="h-7 w-7 animate-spin rounded-full border-2 border-violet-300 border-t-violet-600" />
                <p className="text-xs text-violet-600">Generating AI floor plan…</p>
                <p className="text-[10px] text-neutral-400">This may take 10-30 seconds</p>
              </div>
            </div>
          )}

          {/* AI error overlay */}
          {aiIsError && !aiPending && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/90">
              <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
                <p className="text-sm font-medium text-red-700">AI floor plan generation failed</p>
                <p className="mt-1 text-xs text-red-600">{aiError?.message ?? "Unknown error"}</p>
                <button
                  type="button"
                  onClick={() => {
                    if (!selectedTower || selectedTower.geometry.type !== "Polygon") return;
                    const nFloors = (selectedTower.properties.floors as number) ?? 10;
                    requestAIFloorPlan({
                      footprint: selectedTower.geometry as { type: "Polygon"; coordinates: number[][][] },
                      n_floors: nFloors,
                      building_height_m: (selectedTower.properties.height as number) ?? nFloors * 3,
                      units_per_core: inputs.unitsPerCore ?? 4,
                      segment: inputs.segment ?? "mid",
                      unit_mix: inputs.unitMix ?? ["2BHK", "3BHK"],
                      storey_height_m: 3.0,
                      plot_area_sqm: (metrics.plotAreaSqm as number) ?? 0,
                    });
                  }}
                  className="mt-2 rounded bg-red-100 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-200"
                >
                  Retry
                </button>
              </div>
            </div>
          )}

          {/* Legend */}
          {floorPlanData?.layout && (
            <div className="absolute bottom-3 left-3 flex flex-col gap-1 rounded-lg border border-neutral-200 bg-white/95 p-2 shadow-sm">
              <p className="text-[9px] font-semibold uppercase tracking-widest text-neutral-500">Legend</p>
              {[
                ["#bfdbfe", "#3b82f6",  "Corridor"],
                ["#e2e8f0", "#64748b",  "Core / Stair"],
                ["#1e3a8a", "#1e3a8a",  "Lift"],
                ["#dcfce7", "#16a34a",  "2BHK Unit"],
                ["#fef3c7", "#d97706",  "3BHK Unit"],
                ["rgba(255,251,235,0.55)", "#d97706", "Living"],
                ["rgba(239,246,255,0.55)", "#3b82f6", "Bedroom"],
                ["rgba(254,242,242,0.55)", "#ef4444", "Kitchen"],
                ["rgba(236,253,245,0.55)", "#10b981", "Toilet"],
                ["#334155",               "#1e293b", "Wall"],
                ["#93c5fd",               "#3b82f6", "Window"],
              ].map(([fill, stroke, label]) => (
                <div key={label} className="flex items-center gap-1.5">
                  <div
                    className="h-3 w-4 rounded-sm border"
                    style={{ background: fill, borderColor: stroke }}
                  />
                  <span className="text-[9px] text-neutral-600">{label}</span>
                </div>
              ))}
              {/* Debug overlay legend — only when active */}
              {showDebug && floorPlanData.placement_debug_geojson && (
                <>
                  <div className="mt-1 border-t border-neutral-200 pt-1">
                    <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-amber-600">
                      Debug Overlay
                    </p>
                  </div>
                  {([
                    ["none",                  "#6b7280", "Buildable Envelope", "8 4"],
                    ["rgba(59,130,246,0.14)", "#3b82f6", "Tower Footprint",    undefined],
                    ["rgba(239,68,68,0.10)",  "#ef4444", "Spacing Buffer",     "5 3"],
                    ["rgba(245,158,11,0.14)", "#f59e0b", "Leftover Area",      "5 3"],
                    ["rgba(34,197,94,0.14)",  "#22c55e", "COP Area",           undefined],
                  ] as [string, string, string, string | undefined][]).map(([fill, stroke, label, dash]) => (
                    <div key={label} className="flex items-center gap-1.5">
                      <div
                        className="h-3 w-4 rounded-sm border"
                        style={{
                          background: fill === "none" ? "transparent" : fill,
                          borderColor: stroke,
                          borderStyle: dash ? "dashed" : "solid",
                        }}
                      />
                      <span className="text-[9px] text-neutral-600">{label}</span>
                    </div>
                  ))}
                </>
              )}
              {/* Core overlay legend */}
              {showCoreOverlay && floorCoreData && (
                <>
                  <div className="mt-1 border-t border-neutral-200 pt-1">
                    <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-cyan-600">
                      Core Overlay
                    </p>
                  </div>
                  {([
                    ["rgba(6, 182, 212, 0.15)", "#06b6d4", "Lobby"],
                    ["#1e293b",                  "#0f172a", "Lift Shaft"],
                    ["#f8fafc",                  "#64748b", "Staircase"],
                    ["rgba(241, 245, 249, 0.6)", "#94a3b8", "Corridor"],
                  ] as [string, string, string][]).map(([fill, stroke, label]) => (
                    <div key={label} className="flex items-center gap-1.5">
                      <div
                        className="h-3 w-4 rounded-sm border"
                        style={{ background: fill, borderColor: stroke }}
                      />
                      <span className="text-[9px] text-neutral-600">{label}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right panel — unit detail + metrics / diagnostics / core */}
      <div className="flex w-72 flex-shrink-0 flex-col border-l border-neutral-200 bg-white">
        {/* Panel header — shows tabs when debug data is present */}
        <div className="border-b border-neutral-200 px-4 py-2.5">
          {selectedUnit ? (
            <h2 className="text-xs font-semibold uppercase tracking-widest text-neutral-700">
              Unit Details
            </h2>
          ) : (floorPlanData?.placement_debug_metrics || floorCoreData) ? (
            /* Tab switcher: Metrics | Diagnostics | Core */
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => { setActiveRightPanel("metrics"); setShowDebug(false); }}
                className={`rounded px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                  activeRightPanel === "metrics"
                    ? "bg-neutral-900 text-white"
                    : "text-neutral-500 hover:bg-neutral-100"
                }`}
              >
                Metrics
              </button>
              {floorPlanData?.placement_debug_metrics && (
                <button
                  type="button"
                  onClick={() => { setActiveRightPanel("diagnostics"); setShowDebug(true); }}
                  className={`rounded px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                    activeRightPanel === "diagnostics"
                      ? "bg-amber-500 text-white"
                      : "text-neutral-500 hover:bg-neutral-100"
                  }`}
                >
                  Diagnostics
                </button>
              )}
              {floorCoreData && (
                <button
                  type="button"
                  onClick={() => { setActiveRightPanel("core"); setShowDebug(false); }}
                  className={`rounded px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                    activeRightPanel === "core"
                      ? "bg-cyan-600 text-white"
                      : "text-neutral-500 hover:bg-neutral-100"
                  }`}
                >
                  Core
                </button>
              )}
            </div>
          ) : (
            <h2 className="text-xs font-semibold uppercase tracking-widest text-neutral-700">
              Floor Plan Metrics
            </h2>
          )}
        </div>

        {/* Unit detail (shown when a unit is clicked, overrides tab content) */}
        {selectedUnit && (
          <UnitDetailPanel
            unit={selectedUnit}
            onClose={() => setSelectedUnit(null)}
          />
        )}

        {/* Loading */}
        {aiPending && (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-xs text-neutral-500">Generating AI floor plan…</div>
          </div>
        )}

        {/* AI metrics panel */}
        {aiFloorPlanData?.metrics && !aiPending && (
          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-violet-700">AI Floor Plan Metrics</h3>
            <div className="space-y-1.5 text-xs text-neutral-700">
              <div className="flex justify-between"><span>Footprint</span><span>{aiFloorPlanData.metrics.footprintSqm} m²</span></div>
              <div className="flex justify-between"><span>Units/floor</span><span>{aiFloorPlanData.metrics.nUnitsPerFloor}</span></div>
              <div className="flex justify-between"><span>Total units</span><span>{aiFloorPlanData.metrics.nTotalUnits}</span></div>
              <div className="flex justify-between"><span>Efficiency</span><span>{aiFloorPlanData.metrics.efficiencyPct}%</span></div>
              <div className="flex justify-between"><span>Core area</span><span>{aiFloorPlanData.metrics.coreSqm} m²</span></div>
              <div className="flex justify-between"><span>Corridor area</span><span>{aiFloorPlanData.metrics.corridorSqm} m²</span></div>
              <div className="flex justify-between"><span>Net BUA</span><span>{aiFloorPlanData.metrics.netBuaSqm?.toFixed(0)} m²</span></div>
              <div className="flex justify-between"><span>Gross BUA</span><span>{aiFloorPlanData.metrics.grossBuaSqm?.toFixed(0)} m²</span></div>
              <div className="flex justify-between"><span>Lifts</span><span>{aiFloorPlanData.metrics.nLifts}</span></div>
              <div className="flex justify-between"><span>Stairs</span><span>{aiFloorPlanData.metrics.nStairs}</span></div>
              <div className="flex justify-between"><span>Floors</span><span>{aiFloorPlanData.metrics.nFloors}</span></div>
              <div className="flex justify-between"><span>Building height</span><span>{aiFloorPlanData.metrics.buildingHeightM} m</span></div>
            </div>
          </div>
        )}

        {!aiPending && !aiFloorPlanData && !aiIsError && (
          <div className="flex flex-1 items-center justify-center p-4">
            <p className="text-center text-xs text-neutral-400">
              AI floor plan metrics will appear here after generation.
            </p>
          </div>
        )}
      </div>

      {/* Text-to-image preview (separate from vector floor plan pipeline) */}
      {previewImageModalOpen && previewImageSrc && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4"
          onClick={() => {
            setPreviewImageModalOpen(false);
            setPreviewImageSrc(null);
          }}
          role="presentation"
        >
          <div
            className="relative max-h-[90vh] max-w-5xl overflow-auto rounded-lg bg-white p-2 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Floor plan preview image"
          >
            <button
              type="button"
              className="absolute right-2 top-2 z-10 rounded bg-neutral-100 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-200"
              onClick={() => {
                setPreviewImageModalOpen(false);
                setPreviewImageSrc(null);
              }}
            >
              Close
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewImageSrc}
              alt="AI-generated floor plan style preview (text-to-image; not the CAD layout)"
              className="max-h-[85vh] w-auto object-contain"
            />
          </div>
        </div>
      )}
    </div>
  );
}
