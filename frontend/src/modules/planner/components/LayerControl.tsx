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
    <div className="flex flex-col gap-2 rounded border border-neutral-200 bg-white p-3 shadow-sm">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-600">
        Layers
      </h3>
      <div className="flex flex-col gap-1">
        {MAIN_LAYERS.map((key) => (
          <label
            key={key}
            className="flex cursor-pointer items-center gap-2 text-sm"
          >
            <input
              type="checkbox"
              checked={layerVisibility[key] ?? false}
              onChange={() => toggle(key)}
              className="h-3.5 w-3.5 rounded border-neutral-300"
            />
            <span>{LAYER_LABELS[key]}</span>
          </label>
        ))}
      </div>
      {debugMode && (
        <>
          <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
            Debug
          </h3>
          <div className="flex flex-col gap-1">
            {DEBUG_LAYERS.map((key) => (
              <label
                key={key}
                className="flex cursor-pointer items-center gap-2 text-sm text-neutral-600"
              >
                <input
                  type="checkbox"
                  checked={layerVisibility[key] ?? false}
                  onChange={() => toggle(key)}
                  className="h-3.5 w-3.5 rounded border-neutral-300"
                />
                <span>{LAYER_LABELS[key]}</span>
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
