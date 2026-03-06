"use client";

import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { usePlannerStore } from "@/state/plannerStore";

export function PlotSelector() {
  const { data, isLoading, isError } = usePlotsQuery();
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);
  const setSelectedPlotId = usePlannerStore(
    (state) => state.setSelectedPlotId,
  );

  return (
    <div className="rounded-md border border-neutral-200 bg-white p-3 text-sm">
      <h3 className="font-medium text-neutral-900">Plots</h3>
      {isLoading && (
        <p className="mt-2 text-xs text-neutral-500">Loading plots…</p>
      )}
      {isError && (
        <p className="mt-2 text-xs text-red-600">
          Unable to load plots. Please try again.
        </p>
      )}
      {!isLoading && !isError && (
        <ul className="mt-2 space-y-1 text-xs">
          {data?.map((plot) => {
            const isActive = plot.id === selectedPlotId;
            return (
              <li key={plot.id}>
                <button
                  type="button"
                  onClick={() =>
                    setSelectedPlotId(
                      isActive ? null : String(plot.id),
                    )
                  }
                  className={`flex w-full items-center justify-between rounded-md px-2 py-1 ${
                    isActive
                      ? "bg-neutral-900 text-neutral-50"
                      : "hover:bg-neutral-100 text-neutral-800"
                  }`}
                >
                  <span className="truncate">{plot.name}</span>
                  <span className="ml-2 text-[10px] text-neutral-400">
                    {Math.round(plot.areaSqm)} m²
                  </span>
                </button>
              </li>
            );
          })}
          {!data?.length && (
            <li className="text-neutral-400">No plots available.</li>
          )}
        </ul>
      )}
    </div>
  );
}

