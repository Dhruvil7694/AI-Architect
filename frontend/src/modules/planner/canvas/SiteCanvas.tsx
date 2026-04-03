"use client";

import { useRef, useImperativeHandle, forwardRef } from "react";
import { SvgCanvas, type SvgCanvasHandle } from "@/modules/planner/components/visualization/SvgCanvas";
import type { GeometryModel } from "@/geometry/geojsonParser";
import { groupFeaturesByLayer } from "@/geometry/layerManager";
import { usePlannerStore } from "@/state/plannerStore";
import {
  PlotLayer,
  PlotDimLayer,
  SetbackBandsLayer,
  EnvelopeLayer,
  CopLayer,
  TowerLayer,
  SpacingLayer,
  AnnotationLayer,
} from "@/modules/planner/components/layers";

export type SiteCanvasMetrics = {
  roadWidthM?: number;
  buildingHeightM?: number;
  // Full plan metrics forwarded to AnnotationLayer for scale bar + area labels
  planMetrics?: Record<string, unknown>;
};

export type SiteCanvasProps = {
  /** Geometry for site plan. When null or empty, a safe fallback is shown. */
  geometryModel: GeometryModel | null;
  /** Regulatory metrics for setback band computation. */
  metrics?: SiteCanvasMetrics;
  /** When true, show "Coming Soon" (e.g. non–high-rise mode). */
  showComingSoon?: boolean;
};

export type SiteCanvasHandle = SvgCanvasHandle;

/**
 * Site-stage canvas: plot boundary, setback bands, buildable envelope,
 * COP zone, tower footprints, spacing, and annotations.
 * Renders a clean architectural layered view after plan generation.
 */
export const SiteCanvas = forwardRef<SiteCanvasHandle, SiteCanvasProps>(function SiteCanvas(
  { geometryModel, metrics = {}, showComingSoon = false },
  ref,
) {
  const canvasRef = useRef<SvgCanvasHandle>(null);
  useImperativeHandle(ref, () => ({
    fitInView: () => canvasRef.current?.fitInView(),
    resetView: () => canvasRef.current?.resetView(),
    getSvgElement: () => canvasRef.current?.getSvgElement() ?? null,
  }), []);
  const layerVisibility = usePlannerStore((s) => s.layerVisibility);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const setSelectedTowerIndex = usePlannerStore((s) => s.setSelectedTowerIndex);

  if (showComingSoon) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50">
        <p className="text-center text-sm font-medium text-neutral-600">
          Coming Soon
        </p>
        <p className="mt-1 text-center text-xs text-neutral-400">
          Only high-rise residential site planning is available in this release.
        </p>
      </div>
    );
  }

  if (!geometryModel || !geometryModel.features?.length) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50">
        <p className="text-xs text-neutral-500">
          No geometry loaded. Select a plot and generate a plan to view the site layout.
        </p>
      </div>
    );
  }

  const grouped = groupFeaturesByLayer(geometryModel);
  const roadWidthM = metrics.roadWidthM ?? 12;
  const buildingHeightM = metrics.buildingHeightM ?? 16.5;
  const planMetrics = metrics.planMetrics ?? {};

  return (
    <div className="relative flex h-full w-full flex-1 flex-col" style={{ background: "#eeeae2" }}>
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
            {/* 1. Plot boundary — white-cream fill, dark border */}
            <PlotLayer
              features={grouped.plotBoundary ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.plotBoundary}
            />

            {/* 2. Setback bands — amber (front) + slate (side/rear) */}
            <SetbackBandsLayer
              features={grouped.plotBoundary ?? []}
              viewTransform={viewTransform}
              roadWidthM={roadWidthM}
              buildingHeightM={buildingHeightM}
              visible={!!layerVisibility.plotBoundary}
            />

            {/* 3. Buildable envelope — teal tint, dashed border */}
            <EnvelopeLayer
              features={grouped.envelope ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.envelope}
            />

            {/* 4. COP zone — green tint */}
            <CopLayer
              features={grouped.cop ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.cop}
            />

            {/* 5. Tower footprints — blue */}
            <TowerLayer
              features={grouped.towerFootprints ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.towerFootprints}
              selectedTowerIndex={selectedTowerIndex}
              onFeatureClick={(_, index) => setSelectedTowerIndex(index)}
            />

            {/* 6. Spacing lines — subtle */}
            <SpacingLayer
              features={grouped.spacingLines ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.spacingLines}
            />

            {/* 7. Annotations — envelope area, COP label, tower IDs + scale bar */}
            <AnnotationLayer
              visible={!!layerVisibility.labels}
              viewTransform={viewTransform}
              plotFeatures={[]}
              envelopeFeatures={grouped.envelope ?? []}
              copFeatures={grouped.cop ?? []}
              towerZoneFeatures={[]}
              towerFeatures={grouped.towerFootprints ?? []}
              metrics={planMetrics}
            />

            {/* 8. Plot edge dimension lines — lengths in metres */}
            <PlotDimLayer
              features={grouped.plotBoundary ?? []}
              viewTransform={viewTransform}
              visible={!!layerVisibility.labels}
            />
          </>
        )}
      </SvgCanvas>
    </div>
  );
});
