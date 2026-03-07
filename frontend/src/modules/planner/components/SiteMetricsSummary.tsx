"use client";

import { usePlannerStore } from "@/state/plannerStore";
import { useSiteMetrics } from "@/modules/planner/hooks/usePlannerData";

/** One-line site metrics for the top bar. */
export function SiteMetricsSummary() {
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const { data, isLoading } = useSiteMetrics(selectedPlotId);

  if (!selectedPlotId) {
    return (
      <span className="text-xs text-neutral-400">Select a plot for metrics</span>
    );
  }
  if (isLoading) {
    return <span className="text-xs text-neutral-400">Loading…</span>;
  }
  if (!data) {
    return <span className="text-xs text-neutral-400">No metrics</span>;
  }

  const copPct =
    data.plotAreaSqm > 0
      ? Math.round((data.copAreaSqm / data.plotAreaSqm) * 100)
      : 0;

  return (
    <span className="text-xs text-neutral-600">
      {Math.round(data.plotAreaSqm)} m² · Max FSI {data.maxFSI.toFixed(1)} ·
      Max BUA {Math.round(data.maxBUA)} m² · COP {copPct}%
    </span>
  );
}
