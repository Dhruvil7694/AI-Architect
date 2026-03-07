"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useFloorPlan } from "@/modules/planner/hooks/usePlannerData";
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
} from "@/services/plannerService";

// ─── Colour palette ────────────────────────────────────────────────────────────
const LAYER_STYLE: Record<string, { fill: string; stroke: string; strokeWidth?: number; strokeDasharray?: string }> = {
  footprint_bg: { fill: "rgba(241,245,249,0.95)", stroke: "#94a3b8", strokeWidth: 1.5 },
  corridor:     { fill: "rgba(219,234,254,0.85)", stroke: "#3b82f6", strokeWidth: 1 },
  core:         { fill: "rgba(226,232,240,0.90)", stroke: "#64748b", strokeWidth: 1.5 },
  stair:        { fill: "rgba(148,163,184,0.80)", stroke: "#475569", strokeWidth: 1, strokeDasharray: "3 2" },
  lobby:        { fill: "rgba(186,230,253,0.75)", stroke: "#0ea5e9", strokeWidth: 0.8 },
  lift:         { fill: "rgba(30,58,138,0.85)",   stroke: "#1e3a8a", strokeWidth: 1 },
  unit_2BHK:    { fill: "rgba(220,252,231,0.85)", stroke: "#16a34a", strokeWidth: 1 },
  unit_3BHK:    { fill: "rgba(254,243,199,0.85)", stroke: "#d97706", strokeWidth: 1 },
  unit_4BHK:    { fill: "rgba(254,226,226,0.85)", stroke: "#dc2626", strokeWidth: 1 },
  unit_1BHK:    { fill: "rgba(240,253,244,0.85)", stroke: "#22c55e", strokeWidth: 1 },
  unit_1RK:     { fill: "rgba(240,253,244,0.75)", stroke: "#4ade80", strokeWidth: 1 },
  unit_STUDIO:  { fill: "rgba(240,253,244,0.70)", stroke: "#86efac", strokeWidth: 1 },
  unit_default: { fill: "rgba(220,252,231,0.85)", stroke: "#16a34a", strokeWidth: 1 },
};

function styleForFeature(f: FloorPlanFeature) {
  const { layer, unit_type } = f.properties;
  if (layer === "unit") {
    return LAYER_STYLE[`unit_${unit_type}`] ?? LAYER_STYLE.unit_default;
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
  // Render in layer order so labels sit on top
  const ordered = useMemo(() => {
    const order = ["footprint_bg", "core", "corridor", "lobby", "stair", "lift", "unit"];
    const sorted = [...layout.features].sort((a: FloorPlanFeature, b: FloorPlanFeature) => {
      const ai = order.indexOf(a.properties.layer);
      const bi = order.indexOf(b.properties.layer);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
    return sorted;
  }, [layout]);

  return (
    <g>
      {ordered.map((f) => {
        const style = styleForFeature(f);
        const d = featureToPath(f.geometry, viewTransform);
        if (!d) return null;
        const isUnit = f.properties.layer === "unit";
        const isLift = f.properties.layer === "lift";
        const isStair = f.properties.layer === "stair";
        const [cx, cy] = ringCentroid(f.geometry.coordinates[0], viewTransform);

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
            {f.properties.layer === "lobby" && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={8} fill="#0369a1"
                style={{ pointerEvents: "none" }}
              >
                Lobby
              </text>
            )}
            {f.properties.layer === "corridor" && (
              <text
                x={cx} y={cy}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={8} fill="#1d4ed8"
                style={{ pointerEvents: "none" }}
              >
                {`Corridor  ${f.properties.width_m ?? 1.5}m`}
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
              </>
            )}
          </g>
        );
      })}
    </g>
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
            ["Core + Stair", metrics.coreSqm, "bg-slate-200"],
            ["Corridor",     metrics.corridorSqm, "bg-blue-200"],
            ["Net unit area",metrics.unitAreaPerFloorSqm, "bg-green-200"],
          ].map(([label, val, cls]) => (
            <div key={label as string} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <div className={`h-2.5 w-2.5 rounded-sm ${cls as string}`} />
                <span className="text-neutral-600">{label as string}</span>
              </div>
              <span className="font-medium">{(val as number).toFixed(0)} m²</span>
            </div>
          ))}
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
          GDCR Compliance
        </h3>
        <div className="flex flex-col gap-1">
          <ComplianceBadge ok={gdcr.lift_ok}
            label={gdcr.lift_required
              ? `Lift: ${gdcr.lift_provided} provided (required)`
              : `Lift: ${gdcr.lift_provided} provided (optional)`} />
          <ComplianceBadge ok={gdcr.stair_width_ok}
            label={`Stair width: ${gdcr.stair_width_m.toFixed(2)} m (min 1.0 m)`} />
          <ComplianceBadge ok={gdcr.corridor_width_ok}
            label={`Corridor: ${gdcr.corridor_width_m.toFixed(1)} m (min 1.2 m)`} />
          <ComplianceBadge ok={gdcr.clearance_habitable_ok}
            label={`Storey ht: ${gdcr.storey_height_m.toFixed(1)} m (min 2.75 m)`} />
        </div>
      </section>
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────

type FloorPlanningViewProps = {
  geometryModel: GeometryModel | null;
};

export function FloorPlanningView({ geometryModel }: FloorPlanningViewProps) {
  const canvasRef           = useRef<SvgCanvasHandle>(null);
  const selectedTowerIndex  = usePlannerStore((s) => s.selectedTowerIndex);
  const setPlanningStep     = usePlannerStore((s) => s.setPlanningStep);
  const setSelectedUnit     = usePlannerStore((s) => s.setSelectedUnit);
  const scenarios           = usePlannerStore((s) => s.scenarios);
  const activeScenarioId    = usePlannerStore((s) => s.activeScenarioId);
  const inputs              = usePlannerStore((s) => s.inputs);

  const scenario    = scenarios.find((s) => s.id === activeScenarioId);
  const metrics     = (scenario?.planResultSummary as { metrics?: Record<string, unknown> })?.metrics ?? {};

  const { mutate: requestFloorPlan, data: floorPlanData, isPending, isError, error } = useFloorPlan();

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
      properties: f.properties as Record<string, unknown>,
    }));
    return { features: [...fpFeatures, selectedTower] };
  }, [selectedTower, floorPlanData]);

  // ── Auto-request floor plan when tower is selected ───────────────────────────
  useEffect(() => {
    if (!selectedTower) return;
    if (selectedTower.geometry.type !== "Polygon") return;

    const props = selectedTower.properties;
    const n_floors         = (props.floors as number)  ?? 10;
    const building_height  = (props.height as number)  ?? n_floors * 3;
    const plot_area_sqm    = (metrics.plotAreaSqm as number) ?? 0;

    requestFloorPlan({
      footprint: selectedTower.geometry as { type: "Polygon"; coordinates: number[][][] },
      n_floors,
      building_height_m: building_height,
      unit_mix: inputs.unitMix ?? ["2BHK", "3BHK"],
      storey_height_m: 3.0,
      plot_area_sqm,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTower?.id]);

  // ── Guard: no tower selected ─────────────────────────────────────────────────
  if (selectedTowerIndex == null || !selectedTower) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 rounded border border-dashed border-neutral-300 bg-neutral-50 p-8">
        <p className="text-sm text-neutral-600">
          Select a tower on the site plan, then click &quot;Design Floor Plan&quot;.
        </p>
        <button
          type="button"
          onClick={() => setPlanningStep("site")}
          className="rounded bg-neutral-200 px-3 py-1.5 text-sm font-medium text-neutral-800 hover:bg-neutral-300"
        >
          Back to Site Plan
        </button>
      </div>
    );
  }

  const towerId = (selectedTower.properties.towerId as string) ?? `T${selectedTowerIndex + 1}`;
  const towerFloors = (selectedTower.properties.floors as number) ?? "—";

  // ── Layout ───────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Canvas — left 70% */}
      <div className="relative flex flex-1 flex-col bg-white">
        {/* Top bar */}
        <div className="flex items-center justify-between border-b border-neutral-200 bg-white px-3 py-2">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setPlanningStep("site")}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100"
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Site Plan
            </button>
            <span className="text-xs font-semibold text-neutral-800">
              Tower {towerId} — Typical Floor Plan
            </span>
            {towerFloors && (
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700">
                {towerFloors} floors
              </span>
            )}
          </div>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => canvasRef.current?.fitInView()}
              className="rounded px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100"
            >
              Fit
            </button>
            <button
              type="button"
              onClick={() => canvasRef.current?.resetView()}
              className="rounded px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100"
            >
              Reset
            </button>
          </div>
        </div>

        {/* SVG canvas */}
        <div className="relative flex-1">
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
                        })
                      }
                    />
                  )}
                </g>
              )}
            </SvgCanvas>
          )}

          {/* Loading overlay */}
          {isPending && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/80">
              <div className="flex flex-col items-center gap-3">
                <div className="h-7 w-7 animate-spin rounded-full border-2 border-neutral-300 border-t-blue-600" />
                <p className="text-xs text-neutral-600">Generating floor plan…</p>
              </div>
            </div>
          )}

          {/* Error overlay */}
          {isError && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/90">
              <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
                <p className="text-sm font-medium text-red-700">Floor plan generation failed</p>
                <p className="mt-1 text-xs text-red-600">{error?.message ?? "Unknown error"}</p>
                <button
                  type="button"
                  onClick={() => {
                    if (!selectedTower || selectedTower.geometry.type !== "Polygon") return;
                    const n = (selectedTower.properties.floors as number) ?? 10;
                    requestFloorPlan({
                      footprint: selectedTower.geometry as { type: "Polygon"; coordinates: number[][][] },
                      n_floors: n,
                      building_height_m: (selectedTower.properties.height as number) ?? n * 3,
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
              ].map(([fill, stroke, label]) => (
                <div key={label} className="flex items-center gap-1.5">
                  <div
                    className="h-3 w-4 rounded-sm border"
                    style={{ background: fill, borderColor: stroke }}
                  />
                  <span className="text-[9px] text-neutral-600">{label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Metrics panel — right 30% */}
      <div className="flex w-72 flex-shrink-0 flex-col border-l border-neutral-200 bg-white">
        <div className="border-b border-neutral-200 px-4 py-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-neutral-700">
            Floor Plan Metrics
          </h2>
        </div>

        {isPending && (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-xs text-neutral-500">Computing…</div>
          </div>
        )}

        {floorPlanData?.metrics && !isPending && (
          <FloorPlanMetricsPanel metrics={floorPlanData.metrics} />
        )}

        {!isPending && !floorPlanData && !isError && (
          <div className="flex flex-1 items-center justify-center p-4">
            <p className="text-center text-xs text-neutral-400">
              Floor plan metrics will appear here after generation.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
