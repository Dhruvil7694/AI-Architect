"use client";

import type { GeometryModel } from "@/geometry/geojsonParser";
import { FloorPlanningView } from "@/modules/planner/components/FloorPlanningView";

export type FloorCanvasProps = {
  /** Geometry from the placement job (tower footprints). When null or empty, a fallback is shown. */
  geometryModel: GeometryModel | null;
  onBackFromFloor?: () => void;
  backFromFloorLabel?: string;
  /**
   * True while the site-plan job (envelope + placement) is still running.
   * Shows the unified generation loader instead of the "no layout" fallback,
   * so the user sees only ONE loading screen from click → final image.
   */
  sitePlanPending?: boolean;
};

/**
 * Floor-design canvas. Wraps FloorPlanningView.
 * Lazy-loaded from PlannerWorkspace via dynamic().
 */
export function FloorCanvas({
  geometryModel,
  onBackFromFloor,
  backFromFloorLabel,
  sitePlanPending = false,
}: FloorCanvasProps) {
  // Unified loader: covers both site-plan generation AND AI floor plan generation.
  // Shown whenever the site plan is still running OR there's no geometry yet.
  if (sitePlanPending || !geometryModel || !geometryModel.features?.length) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-neutral-50/50">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-neutral-200 border-t-neutral-800" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="h-3 w-3 rounded-full bg-neutral-800 animate-pulse" />
            </div>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-neutral-700">Generating floor plan</p>
            <p className="mt-1 text-xs text-neutral-400">
              Analysing plot, placing towers and designing your layout…
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <FloorPlanningView
      geometryModel={geometryModel}
      onBackFromFloor={onBackFromFloor}
      backFromFloorLabel={backFromFloorLabel}
    />
  );
}
