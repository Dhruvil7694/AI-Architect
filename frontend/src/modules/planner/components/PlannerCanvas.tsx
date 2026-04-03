"use client";

import { useCallback, useRef, useState } from "react";
import { SvgCanvas, type SvgCanvasHandle } from "@/modules/planner/components/visualization/SvgCanvas";
import type { GeometryModel, GeometryFeature } from "@/geometry/geojsonParser";
import type { Position } from "@/geometry/geometryNormalizer";
import { groupFeaturesByLayer } from "@/geometry/layerManager";
import { projectPosition } from "@/geometry/transform";
import { getFeatureCentroid } from "@/geometry/centroid";
import { getFeatureAreaM2 } from "@/geometry/polygonArea";
import { usePlannerStore } from "@/state/plannerStore";
import {
  PlotLayer,
  SetbackLayer,
  EnvelopeLayer,
  CopLayer,
  RoadLayer,
  RoadCorridorLayer,
  TowerZoneLayer,
  TowerLayer,
  SpacingLayer,
  AnnotationLayer,
  BuildableEnvelopeLayer,
  CopCandidateZonesLayer,
  RoadNetworkLayer,
} from "@/modules/planner/components/layers";
import { InspectorPanel } from "@/modules/planner/components/InspectorPanel";
import { ScaleBar } from "@/modules/planner/components/ScaleBar";
import { NorthArrow } from "@/modules/planner/components/NorthArrow";
import { ScenarioSelector } from "@/modules/planner/components/ScenarioSelector";

const SQFT_TO_SQM = 0.09290304;

type PlannerCanvasProps = {
  geometryModel: GeometryModel | null;
  isLoading?: boolean;
  loadingProgress?: number | null;
};

type HoverInfo = {
  feature: GeometryFeature;
  screenPos: Position;
};

type InspectorSelectionKind = "tower" | "cop" | "plot";

type InspectorSelection = {
  kind: InspectorSelectionKind;
  properties: Record<string, unknown>;
};

export function PlannerCanvas({
  geometryModel,
  isLoading = false,
  loadingProgress = null,
}: PlannerCanvasProps) {
  const canvasRef = useRef<SvgCanvasHandle>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<InspectorSelection | null>(null);

  const layerVisibility = usePlannerStore((s) => s.layerVisibility);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const setSelectedTowerIndex = usePlannerStore((s) => s.setSelectedTowerIndex);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const scenarios = usePlannerStore((s) => s.scenarios);
  const debugMode = usePlannerStore((s) => s.debugMode);

  const activeScenario =
    scenarios.find((s) => s.id === activeScenarioId) ??
    (scenarios.length > 0 ? scenarios[0] : undefined);

  const summary = (activeScenario?.planResultSummary as {
    metrics?: Record<string, unknown>;
  }) ?? {};
  const metrics = summary.metrics ?? {};

  const exportSvg = useCallback(() => {
    const svgEl = canvasRef.current?.getSvgElement();
    if (!svgEl) return;

    const clone = svgEl.cloneNode(true) as SVGSVGElement;

    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = "Site Plan — Development Layout";
    clone.insertBefore(title, clone.firstChild);

    const desc = document.createElementNS("http://www.w3.org/2000/svg", "desc");
    desc.textContent = [
      metrics && typeof metrics.plotAreaSqm === "number" ? `Plot area: ${Math.round(metrics.plotAreaSqm)} m²` : null,
      metrics && typeof metrics.maxFSI === "number" ? `Max FSI: ${metrics.maxFSI.toFixed(2)}` : null,
      metrics && typeof metrics.achievedFSI === "number" ? `Achieved FSI: ${metrics.achievedFSI.toFixed(2)}` : null,
      `Generated: ${new Date().toISOString()}`,
    ]
      .filter(Boolean)
      .join(" | ");
    clone.insertBefore(desc, clone.firstChild);

    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(clone);
    const blob = new Blob(
      [`<?xml version="1.0" encoding="UTF-8"?>\n`, svgStr],
      { type: "image/svg+xml;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "site-plan.svg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [canvasRef, metrics]);

  const scenarioGeometryModel = (activeScenario as unknown as { geometryModel?: GeometryModel } | undefined)?.geometryModel;
  const effectiveGeometryModel: GeometryModel | null =
    scenarioGeometryModel ?? geometryModel;

  if ((!effectiveGeometryModel || effectiveGeometryModel.features.length === 0) && isLoading) {
    // Show actual progress when available (backend reports 10 = running, 100 = done).
    // Fall back to an indeterminate shimmer while the first status poll is in flight.
    const hasProgress =
      typeof loadingProgress === "number" && loadingProgress > 0;
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50">
        <div className="flex w-52 flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-700" />
          <div className="w-full text-center">
            <p className="mb-2 text-xs font-medium text-neutral-700">
              Generating plan…
            </p>
            {/* Progress bar — indeterminate shimmer when progress unknown */}
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-200">
              {hasProgress ? (
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-700"
                  style={{ width: `${Math.max(8, loadingProgress!)}%` }}
                />
              ) : (
                <div className="h-full w-full animate-pulse rounded-full bg-blue-400" />
              )}
            </div>
            <p className="mt-1.5 text-[10px] text-neutral-400">
              {hasProgress
                ? `${Math.round(loadingProgress!)}% — Computing layout`
                : "Submitting job…"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!effectiveGeometryModel || effectiveGeometryModel.features.length === 0) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50">
        <p className="text-xs text-neutral-500">
          No geometry loaded. Select a plot and generate a scenario to view
          geometry.
        </p>
      </div>
    );
  }

  const grouped = groupFeaturesByLayer(effectiveGeometryModel);


  return (
    <div className="relative flex h-full w-full flex-1 flex-col bg-white">
      <div className="z-10 flex items-center gap-2 px-3 pt-2">
        <ScenarioSelector />
        {metrics.generationSource && (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold shadow-sm ${
              metrics.generationSource === "ai"
                ? "bg-violet-100 text-violet-700 ring-1 ring-violet-200"
                : "bg-neutral-100 text-neutral-600 ring-1 ring-neutral-200"
            }`}
          >
            {metrics.generationSource === "ai" ? "AI-Generated" : "Algorithmic"}
          </span>
        )}
      </div>
      <div className="absolute right-2 top-2 z-10 flex gap-1 rounded bg-white/90 p-1 shadow">
        <button
          type="button"
          onClick={() => canvasRef.current?.fitInView()}
          className="rounded px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100"
          title="Fit to view"
        >
          Fit
        </button>
        <button
          type="button"
          onClick={() => canvasRef.current?.resetView()}
          className="rounded px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100"
          title="Reset view"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={exportSvg}
          className="rounded px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100"
          title="Export site plan as SVG"
        >
          SVG
        </button>
      </div>

      <SvgCanvas geometryModel={effectiveGeometryModel} canvasRef={canvasRef}>
        {({ viewTransform }) => (
          <>
            <PlotLayer
              features={grouped.plotBoundary ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.plotBoundary}
              onFeatureHover={(f) =>
                setHover(
                  f
                    ? {
                        feature: f,
                        screenPos: getFeatureCentroid(f)
                          ? projectPosition(getFeatureCentroid(f)!, viewTransform)
                          : [0, 0],
                      }
                    : null
                )
              }
            />
            <SetbackLayer
              features={grouped.copMargin ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.copMargin}
            />
            <EnvelopeLayer
              features={grouped.envelope ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.envelope}
              onFeatureHover={(f) =>
                setHover(
                  f
                    ? {
                        feature: f,
                        screenPos: getFeatureCentroid(f)
                          ? projectPosition(getFeatureCentroid(f)!, viewTransform)
                          : [0, 0],
                      }
                    : null
                )
              }
            />
            <CopLayer
              features={grouped.cop ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.cop}
              onFeatureHover={(f) =>
                setHover(
                  f
                    ? {
                        feature: f,
                        screenPos: getFeatureCentroid(f)
                          ? projectPosition(getFeatureCentroid(f)!, viewTransform)
                          : [0, 0],
                      }
                    : null
                )
              }
            />
            <RoadLayer
              features={grouped.internalRoads ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.internalRoads}
            />
            <RoadCorridorLayer
              features={grouped.roadCorridors ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.roadCorridors}
            />
            <TowerZoneLayer
              features={grouped.towerZones ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.towerZones}
            />
            <TowerLayer
              features={grouped.towerFootprints ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.towerFootprints}
              selectedTowerIndex={selectedTowerIndex}
              onFeatureHover={(f) =>
                setHover(
                  f
                    ? {
                        feature: f,
                        screenPos: getFeatureCentroid(f)
                          ? projectPosition(getFeatureCentroid(f)!, viewTransform)
                          : [0, 0],
                      }
                    : null
                )
              }
              onFeatureClick={(_, index) => setSelectedTowerIndex(index)}
            />
            <SpacingLayer
              features={grouped.spacingLines ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.spacingLines}
            />
            <AnnotationLayer
              visible={!!layerVisibility.labels}
              viewTransform={viewTransform}
              plotFeatures={grouped.plotBoundary ?? []}
              envelopeFeatures={grouped.envelope ?? []}
              copFeatures={grouped.cop ?? []}
              towerZoneFeatures={grouped.towerZones ?? []}
              towerFeatures={grouped.towerFootprints ?? []}
              metrics={metrics}
            />

            {debugMode && (
              <>
                <BuildableEnvelopeLayer
                  features={grouped.buildableEnvelope ?? []}
                  viewTransform={viewTransform}
                  visible={!!layerVisibility.buildableEnvelope}
                  fill="rgba(147,51,234,0.08)"
                  stroke="#7c3aed"
                  strokeDasharray="2 2"
                />
                <CopCandidateZonesLayer
                  features={grouped.copCandidateZones ?? []}
                  viewTransform={viewTransform}
                  visible={!!layerVisibility.copCandidateZones}
                  fill="rgba(236,72,153,0.1)"
                  stroke="#db2777"
                  strokeDasharray="2 2"
                />
                <RoadNetworkLayer
                  features={grouped.roadNetwork ?? []}
                  viewTransform={viewTransform}
                  visible={!!layerVisibility.roadNetwork}
                  fill="none"
                  stroke="#dc2626"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                />
              </>
            )}
            <ScaleBar viewTransform={viewTransform} />
            <NorthArrow />
          </>
        )}
      </SvgCanvas>


      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-[220px] rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs shadow-xl"
          style={{
            left: hover.screenPos[0] + 14,
            top: hover.screenPos[1] + 14,
          }}
        >
          {hover.feature.layer === "cop" && (() => {
            const p = hover.feature.properties ?? {};
            const areaSqm  = (p.area_sqm as number | undefined) ?? Math.round((Number(metrics.copAreaSqft) || 0) * SQFT_TO_SQM);
            const reqSqm   = (metrics as Record<string, unknown>).copRequiredSqm as number | undefined;
            const widthM   = p.width_m  as number | undefined;
            const depthM   = p.depth_m  as number | undefined;
            const minDim   = p.min_dimension_m as number | undefined;
            const copOk    = p.cop_ok   as boolean | undefined;
            return (
              <>
                <div className="mb-1 font-semibold text-green-700">Common Open Plot</div>
                <div className="space-y-0.5">
                  <div className="flex justify-between gap-4"><span className="text-neutral-500">Area</span><span className="font-medium">{Math.round(areaSqm)} m²</span></div>
                  {reqSqm != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Required</span><span className="font-medium">≥ {Math.round(reqSqm)} m²</span></div>}
                  {widthM != null && depthM != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Size</span><span className="font-medium">{widthM.toFixed(1)} × {depthM.toFixed(1)} m</span></div>}
                  {minDim != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Min dim</span><span className={`font-medium ${copOk === false ? "text-red-600" : "text-green-700"}`}>{minDim.toFixed(1)} m {copOk === false ? "⚠ < 7.5m" : "✓"}</span></div>}
                </div>
              </>
            );
          })()}

          {hover.feature.layer === "towerFootprints" && (() => {
            const p = hover.feature.properties ?? {};
            const areaSqm  = (p.area_sqm  as number | undefined) ?? getFeatureAreaM2(hover.feature);
            const widthM   = p.width_m    as number | undefined;
            const depthM   = p.depth_m    as number | undefined;
            const floors   = p.floors     as number | undefined;
            const heightM  = p.height_m   as number | undefined;
            const buaSqm   = p.bua_sqm    as number | undefined;
            const towerId  = p.towerId    as string | undefined;
            return (
              <>
                <div className="mb-1 font-semibold text-blue-700">{towerId ?? "Tower"}</div>
                <div className="space-y-0.5">
                  {areaSqm != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Footprint</span><span className="font-medium">{Math.round(areaSqm)} m²</span></div>}
                  {widthM != null && depthM != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Size</span><span className="font-medium">{widthM.toFixed(1)} × {depthM.toFixed(1)} m</span></div>}
                  {floors != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Floors</span><span className="font-medium">{floors} F</span></div>}
                  {heightM != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">Height</span><span className="font-medium">{heightM.toFixed(1)} m</span></div>}
                  {buaSqm != null && <div className="flex justify-between gap-4"><span className="text-neutral-500">BUA</span><span className="font-medium">{Math.round(buaSqm)} m²</span></div>}
                </div>
              </>
            );
          })()}

          {hover.feature.layer === "plotBoundary" && (
            <>
              <div className="mb-1 font-semibold text-neutral-700">Plot Boundary</div>
              <div className="space-y-0.5">
                <div className="flex justify-between gap-4"><span className="text-neutral-500">Area</span><span className="font-medium">{Math.round(Number(metrics.plotAreaSqm) || 0)} m²</span></div>
                {typeof (metrics as Record<string, unknown>).roadWidthM === "number" && <div className="flex justify-between gap-4"><span className="text-neutral-500">Road</span><span className="font-medium">{((metrics as Record<string, unknown>).roadWidthM as number).toFixed(0)} m wide</span></div>}
                {typeof (metrics as Record<string, unknown>).maxFSI === "number" && <div className="flex justify-between gap-4"><span className="text-neutral-500">FSI allowed</span><span className="font-medium">{((metrics as Record<string, unknown>).maxFSI as number).toFixed(2)}</span></div>}
              </div>
            </>
          )}

          {hover.feature.layer === "envelope" && (
            <>
              <div className="mb-1 font-semibold text-neutral-700">Buildable Envelope</div>
              <div className="space-y-0.5">
                <div className="flex justify-between gap-4"><span className="text-neutral-500">GC</span><span className="font-medium">{typeof metrics.groundCoveragePct === "number" ? `${metrics.groundCoveragePct.toFixed(1)}%` : "—"}</span></div>
                {typeof (metrics as Record<string, unknown>).envelopeAreaSqft === "number" && <div className="flex justify-between gap-4"><span className="text-neutral-500">Env area</span><span className="font-medium">{Math.round(((metrics as Record<string, unknown>).envelopeAreaSqft as number) * SQFT_TO_SQM)} m²</span></div>}
              </div>
            </>
          )}

          {!["cop", "towerFootprints", "plotBoundary", "envelope"].includes(hover.feature.layer) && (
            <div className="font-semibold capitalize text-neutral-600">{hover.feature.layer.replace(/([A-Z])/g, " $1")}</div>
          )}
        </div>
      )}

      {selectedTowerIndex !== null && (
        <div className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-lg border border-neutral-200 bg-white px-4 py-2 shadow-lg">
          <span className="mr-3 text-sm text-neutral-700">Tower {selectedTowerIndex + 1} selected</span>
          <button
            type="button"
            onClick={() => setPlanningStep("floor")}
            className="rounded bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700"
          >
            Design Floor Plan
          </button>
        </div>
      )}

      {selectedFeature && (
        <div className="absolute right-3 top-16 bottom-3 z-20 w-64">
          <InspectorPanel
            selectedFeature={selectedFeature}
            onClose={() => setSelectedFeature(null)}
          />
        </div>
      )}
    </div>
  );
}
