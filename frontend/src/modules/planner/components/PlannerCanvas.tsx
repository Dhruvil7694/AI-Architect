"use client";

import { useRef, useState } from "react";
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

export function PlannerCanvas({
  geometryModel,
  isLoading = false,
  loadingProgress = null,
}: PlannerCanvasProps) {
  const canvasRef = useRef<SvgCanvasHandle>(null);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const layerVisibility = usePlannerStore((s) => s.layerVisibility);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const setSelectedTowerIndex = usePlannerStore((s) => s.setSelectedTowerIndex);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const scenarios = usePlannerStore((s) => s.scenarios);
  const debugMode = usePlannerStore((s) => s.debugMode);

  const scenario = scenarios.find((s) => s.id === activeScenarioId);
  const summary = (scenario?.planResultSummary as {
    metrics?: Record<string, unknown>;
  }) ?? {};
  const metrics = summary.metrics ?? {};

  if ((!geometryModel || geometryModel.features.length === 0) && isLoading) {
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

  if (!geometryModel || geometryModel.features.length === 0) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50">
        <p className="text-xs text-neutral-500">
          No geometry loaded. Select a plot and generate a scenario to view
          geometry.
        </p>
      </div>
    );
  }

  const grouped = groupFeaturesByLayer(geometryModel);

  return (
    <div className="relative flex h-full w-full flex-1 flex-col bg-white">
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
      </div>

      <SvgCanvas geometryModel={geometryModel} canvasRef={canvasRef}>
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
          </>
        )}
      </SvgCanvas>

      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-[200px] rounded border border-neutral-200 bg-white px-2 py-1.5 text-xs shadow-lg"
          style={{
            left: hover.screenPos[0] + 12,
            top: hover.screenPos[1] + 12,
          }}
        >
          {hover.feature.layer === "cop" && (
            <>
              <div className="font-medium">COP</div>
              <div>Area: {Math.round((Number(metrics.copAreaSqft) || 0) * SQFT_TO_SQM)} m²</div>
              <div>Required: {Math.round((Number((metrics as Record<string, unknown>).copRequiredSqm) ?? (Number(metrics.copAreaSqft) || 0) * SQFT_TO_SQM))} m²</div>
            </>
          )}
          {hover.feature.layer === "towerFootprints" && (
            <>
              <div className="font-medium">Tower</div>
              <div>Footprint: {getFeatureAreaM2(hover.feature) != null ? `${Math.round(getFeatureAreaM2(hover.feature)!)} m²` : "—"}</div>
              <div>Floors: {(hover.feature.properties?.floors as number) ?? "—"}</div>
            </>
          )}
          {hover.feature.layer === "plotBoundary" && (
            <>
              <div className="font-medium">Plot</div>
              <div>Area: {Math.round(Number(metrics.plotAreaSqm) || 0)} m²</div>
            </>
          )}
          {hover.feature.layer === "envelope" && (
            <>
              <div className="font-medium">Envelope</div>
              <div>Ground coverage: {typeof metrics.groundCoveragePct === "number" ? `${metrics.groundCoveragePct.toFixed(1)}%` : "—"}</div>
            </>
          )}
          {!["cop", "towerFootprints", "plotBoundary", "envelope"].includes(hover.feature.layer) && (
            <div className="font-medium">{hover.feature.layer}</div>
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
    </div>
  );
}
