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
    const progressText =
      typeof loadingProgress === "number"
        ? ` (${Math.round(loadingProgress)}%)`
        : "";
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50">
        <div className="flex flex-col items-center gap-2">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-neutral-400 border-t-transparent" />
          <p className="text-xs text-neutral-600">
            Generating plan…{progressText}
          </p>
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
