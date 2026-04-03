"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { PlannerLayerKey } from "@/state/plannerStore";

const LAYER_LABELS: Record<PlannerLayerKey, string> = {
  plotBoundary: "Plot boundary",
  envelope: "Envelope",
  cop: "Common Plot",
  copMargin: "Setbacks",
  internalRoads: "Internal Roads",
  roadCorridors: "Road Corridors",
  towerZones: "Tower Zones",
  towerFootprints: "Tower Footprints",
  spacingLines: "Spacing Lines",
  labels: "Labels",
  buildableEnvelope: "Buildable Envelope",
  copCandidateZones: "COP Candidate Zones",
  roadNetwork: "Road Network",
};

const MAIN_LAYERS: PlannerLayerKey[] = [
  "plotBoundary",
  "copMargin",
  "envelope",
  "cop",
  "internalRoads",
  "roadCorridors",
  "towerZones",
  "towerFootprints",
  "spacingLines",
  "labels",
];

const DEBUG_LAYERS: PlannerLayerKey[] = [
  "buildableEnvelope",
  "copCandidateZones",
  "roadNetwork",
];

export function LayerControl() {
  const layerVisibility = usePlannerStore((s) => s.layerVisibility);
  const setLayerVisibility = usePlannerStore((s) => s.setLayerVisibility);
  const debugMode = usePlannerStore((s) => s.debugMode);

  function toggle(key: PlannerLayerKey) {
    setLayerVisibility({ [key]: !layerVisibility[key] });
  }

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm font-sans">
      <h3 className="text-sm font-semibold text-neutral-900 border-b border-neutral-100 pb-2">
        Layers
      </h3>
      <div className="flex flex-col gap-2">
        {MAIN_LAYERS.map((key) => (
          <label
            key={key}
            className="group flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 transition-colors hover:bg-orange-50/50"
          >
            <span className="text-[13px] font-medium text-neutral-600 group-hover:text-neutral-900">
              {LAYER_LABELS[key]}
            </span>
            <input
              type="checkbox"
              checked={layerVisibility[key] ?? false}
              onChange={() => toggle(key)}
              className="h-4 w-4 rounded border-neutral-300 text-orange-500 focus:ring-orange-500/20 transition-all hover:border-orange-400"
            />
          </label>
        ))}
      </div>
      {debugMode && (
        <>
          <h3 className="mt-2 text-sm font-semibold text-amber-700 border-b border-amber-100 pb-2">
            Debug Layers
          </h3>
          <div className="flex flex-col gap-2">
            {DEBUG_LAYERS.map((key) => (
              <label
                key={key}
                className="group flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 transition-colors hover:bg-amber-50"
              >
                <span className="text-[13px] font-medium text-neutral-500 group-hover:text-amber-900">
                  {LAYER_LABELS[key]}
                </span>
                <input
                  type="checkbox"
                  checked={layerVisibility[key] ?? false}
                  onChange={() => toggle(key)}
                  className="h-4 w-4 rounded border-neutral-300 text-amber-500 focus:ring-amber-500/20 transition-all hover:border-amber-400"
                />
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
