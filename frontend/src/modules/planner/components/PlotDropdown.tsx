"use client";

import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { usePlannerStore } from "@/state/plannerStore";

export function PlotDropdown() {
  const { data: plots, isLoading, isError } = usePlotsQuery();
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="plot-select" className="sr-only">
        Select plot
      </label>
      <select
        id="plot-select"
        value={selectedPlotId ?? ""}
        onChange={(e) =>
          setSelectedPlotId(e.target.value ? e.target.value : null)
        }
        disabled={isLoading}
        className="min-w-[180px] rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:bg-neutral-100"
      >
        <option value="">Select plot…</option>
        {plots?.map((plot) => (
          <option key={plot.id} value={plot.id}>
            {plot.name}
            {plot.areaSqm != null ? ` · ${Math.round(plot.areaSqm)} m²` : ""}
          </option>
        ))}
      </select>
      {isLoading && (
        <span className="text-xs text-neutral-400">Loading…</span>
      )}
      {isError && (
        <span className="text-xs text-red-600">Failed to load plots</span>
      )}
    </div>
  );
}
