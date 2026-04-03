"use client";

import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { usePlannerStore } from "@/state/plannerStore";

export function PlotDropdown() {
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const { data: plots, isLoading, isError, refetch } = usePlotsQuery({
    tpScheme: locationPreference.tpId,
    city: locationPreference.districtName,
  });
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);

  return (
    <div className="flex items-center gap-3">
      <div className="relative group">
        <select
          id="plot-select"
          value={selectedPlotId ?? ""}
          onChange={(e) =>
            setSelectedPlotId(e.target.value ? e.target.value : null)
          }
          disabled={isLoading}
          className="appearance-none min-w-[240px] rounded-2xl border border-neutral-100 bg-white py-3 pl-5 pr-12 font-heading text-sm font-bold tracking-tight text-neutral-900 shadow-sm transition-all focus:border-orange-500 focus:outline-none focus:ring-4 focus:ring-orange-500/10 disabled:bg-neutral-50 disabled:text-neutral-400 group-hover:border-orange-200 cursor-pointer"
        >
          <option value="">Select a plot…</option>
          {plots?.map((plot) => (
            <option key={plot.id} value={plot.id}>
              {plot.name} {plot.areaSqm != null ? `(${Math.round(plot.areaSqm)} m²)` : ""}
            </option>
          ))}
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-neutral-400 group-hover:text-orange-500 transition-colors">
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2">
           <span className="h-4 w-4 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
           <span className="text-xs font-bold text-orange-500 uppercase tracking-wider">Loading...</span>
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-red-500 uppercase tracking-wider">Error loading plots</span>
          <button 
            onClick={() => refetch()}
            className="rounded-lg bg-red-50 px-3 py-1 text-[10px] font-bold text-red-600 hover:bg-red-100 transition-colors"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
