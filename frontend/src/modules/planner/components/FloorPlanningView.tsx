"use client";

import { usePlannerStore } from "@/state/plannerStore";
import { usePlanGeometry } from "@/modules/planner/hooks/usePlannerData";
import { groupFeaturesByLayer } from "@/geometry/layerManager";
import { SvgCanvas, type SvgCanvasHandle } from "@/modules/planner/components/visualization/SvgCanvas";
import { useRef } from "react";
import { TowerLayer } from "@/modules/planner/components/layers";
import type { GeometryModel } from "@/geometry/geojsonParser";

type FloorPlanningViewProps = {
  geometryModel: GeometryModel | null;
};

/** Placeholder floor view: shows selected tower footprint. Backend floor layout (core, corridor, units, walls) will be added when API is ready. */
export function FloorPlanningView({ geometryModel }: FloorPlanningViewProps) {
  const canvasRef = useRef<SvgCanvasHandle>(null);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);

  if (selectedTowerIndex == null) {
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

  if (!geometryModel || geometryModel.features.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded border border-dashed border-neutral-300 bg-neutral-50">
        <p className="text-xs text-neutral-500">No geometry. Generate a site plan first.</p>
      </div>
    );
  }

  const grouped = groupFeaturesByLayer(geometryModel);
  const towerFeatures = grouped.towerFootprints ?? [];
  const selectedTower = towerFeatures[selectedTowerIndex] ?? null;

  if (!selectedTower) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 rounded border border-dashed border-neutral-300 bg-neutral-50 p-8">
        <p className="text-sm text-neutral-600">Tower {selectedTowerIndex + 1} not found.</p>
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

  // Show only the selected tower footprint in a dedicated model for the canvas bounds
  const floorModel: GeometryModel = {
    features: [selectedTower],
  };

  return (
    <div className="relative flex h-full w-full flex-col bg-white">
      <div className="absolute left-2 top-2 z-10 flex items-center gap-2 rounded bg-white/90 p-2 shadow">
        <span className="text-xs font-medium text-neutral-700">
          Floor plan — Tower {selectedTowerIndex + 1}
        </span>
        <button
          type="button"
          onClick={() => setPlanningStep("site")}
          className="rounded bg-neutral-200 px-2 py-1 text-xs font-medium text-neutral-800 hover:bg-neutral-300"
        >
          Back to Site Plan
        </button>
      </div>
      <div className="absolute right-2 top-2 z-10 flex gap-1 rounded bg-white/90 p-1 shadow">
        <button
          type="button"
          onClick={() => canvasRef.current?.fitInView()}
          className="rounded px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100"
        >
          Fit
        </button>
        <button
          type="button"
          onClick={() => canvasRef.current?.resetView()}
          className="rounded px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100"
        >
          Reset
        </button>
      </div>
      <SvgCanvas geometryModel={floorModel} canvasRef={canvasRef}>
        {({ viewTransform }) => (
          <>
            <TowerLayer
              features={[selectedTower]}
              viewTransform={viewTransform}
              visible={true}
              selectedTowerIndex={0}
            />
            {/* TODO: Core, Corridor, Units, Walls when backend provides floor layout geometry */}
          </>
        )}
      </SvgCanvas>
      <p className="absolute bottom-2 left-2 text-[10px] text-neutral-400">
        Floor layout layers (core, corridor, units, walls) will appear when backend provides floor geometry.
      </p>
    </div>
  );
}
