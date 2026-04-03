"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { PlannerLayerKey } from "@/state/plannerStore";

const LAYERS: { key: PlannerLayerKey; label: string; activeColor: string }[] = [
  { key: "plotBoundary", label: "Plot", activeColor: "bg-neutral-800" },
  { key: "envelope", label: "Envelope", activeColor: "bg-blue-400" },
  { key: "cop", label: "COP", activeColor: "bg-emerald-400" },
  { key: "copMargin", label: "Setbacks", activeColor: "bg-emerald-200" },
  { key: "internalRoads", label: "Roads", activeColor: "bg-neutral-400" },
  { key: "roadCorridors", label: "Corridors", activeColor: "bg-neutral-200" },
  { key: "towerZones", label: "Zones", activeColor: "bg-orange-300" },
  { key: "towerFootprints", label: "Towers", activeColor: "bg-orange-600" },
  { key: "spacingLines", label: "Spacing", activeColor: "bg-red-400" },
  { key: "labels", label: "Labels", activeColor: "bg-neutral-800" },
];

export function Legend() {
  const visibility = usePlannerStore((state) => state.layerVisibility);
  const setLayerVisibility = usePlannerStore(
    (state) => state.setLayerVisibility,
  );

  return (
    <div className="hidden xl:flex flex-wrap items-center gap-2 rounded-full border border-neutral-100 bg-white px-3 py-1.5 shadow-sm text-[11px] font-medium text-neutral-700">
      {LAYERS.map((layer) => {
        const isVisible = visibility[layer.key];
        return (
          <button
            key={layer.key}
            type="button"
            onClick={() =>
              setLayerVisibility({
                [layer.key]: !isVisible,
              })
            }
            className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition-all duration-300 ${
              isVisible
                ? "border-neutral-200 bg-neutral-50 text-neutral-900 shadow-sm"
                : "border-transparent bg-transparent text-neutral-400 hover:bg-neutral-50 hover:text-neutral-600"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full transition-colors ${
                isVisible ? layer.activeColor : "bg-neutral-200"
              }`}
            />
            <span>{layer.label}</span>
          </button>
        );
      })}
    </div>
  );
}

