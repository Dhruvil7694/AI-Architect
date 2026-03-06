"use client";

import { usePlannerStore } from "@/state/plannerStore";
import { useSiteMetrics } from "@/modules/planner/hooks/usePlannerData";

export function SiteMetricsPanel() {
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);
  const { data, isLoading } = useSiteMetrics(selectedPlotId);

  return (
    <div className="rounded-md border border-neutral-200 bg-white p-3 text-sm">
      <h3 className="font-medium text-neutral-900">Site metrics</h3>
      {!selectedPlotId && (
        <p className="mt-2 text-xs text-neutral-500">
          Select a plot to view metrics.
        </p>
      )}
      {selectedPlotId && isLoading && (
        <p className="mt-2 text-xs text-neutral-500">Loading metrics…</p>
      )}
      {selectedPlotId && !isLoading && !data && (
        <p className="mt-2 text-xs text-neutral-500">
          No metrics available for this plot.
        </p>
      )}
      {selectedPlotId && data && (
        <dl className="mt-2 space-y-1 text-xs text-neutral-700">
          <div className="flex justify-between">
            <dt className="text-neutral-500">Plot area</dt>
            <dd>{Math.round(data.plotAreaSqm)} m²</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-neutral-500">Base FSI</dt>
            <dd>{data.baseFSI.toFixed(2)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-neutral-500">Max FSI</dt>
            <dd>{data.maxFSI.toFixed(2)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-neutral-500">Max BUA</dt>
            <dd>{Math.round(data.maxBUA)} m²</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-neutral-500">COP area</dt>
            <dd>
              {Math.round(data.copAreaSqm)} m²{" "}
              <span className="text-neutral-400">
                (
                {data.plotAreaSqm
                  ? Math.round(
                      (data.copAreaSqm / data.plotAreaSqm) * 100,
                    )
                  : 0}
                %)
              </span>
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-neutral-500">COP strategy</dt>
            <dd className="uppercase">{data.copStrategy}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

