"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { PlannerLayerKey } from "@/state/plannerStore";

const LAYERS: { key: PlannerLayerKey; label: string }[] = [
  { key: "plotBoundary", label: "Plot" },
  { key: "envelope", label: "Envelope" },
  { key: "cop", label: "COP" },
  { key: "copMargin", label: "Setbacks" },
  { key: "internalRoads", label: "Roads" },
  { key: "roadCorridors", label: "Corridors" },
  { key: "towerZones", label: "Zones" },
  { key: "towerFootprints", label: "Towers" },
  { key: "spacingLines", label: "Spacing" },
  { key: "labels", label: "Labels" },
];

export function Legend() {
  const visibility = usePlannerStore((state) => state.layerVisibility);
  const setLayerVisibility = usePlannerStore(
    (state) => state.setLayerVisibility,
  );

  return (
    <div className="inline-flex flex-wrap items-center gap-2 rounded-md border border-neutral-200 bg-white px-3 py-1 text-[11px] text-neutral-700">
      {LAYERS.map((layer) => (
        <button
          key={layer.key}
          type="button"
          onClick={() =>
            setLayerVisibility({
              [layer.key]: !visibility[layer.key],
            })
          }
          className={`flex items-center gap-1 rounded-full border px-2 py-0.5 ${
            visibility[layer.key]
              ? "border-neutral-800 bg-neutral-900 text-neutral-50"
              : "border-neutral-300 bg-white text-neutral-600"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              visibility[layer.key] ? "bg-emerald-400" : "bg-neutral-300"
            }`}
          />
          <span>{layer.label}</span>
        </button>
      ))}
    </div>
  );
}

