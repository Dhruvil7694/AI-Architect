"use client";

import {
  useGeneratePlan,
  usePlanJobStatus,
} from "@/modules/planner/hooks/usePlannerData";
import { usePlannerStore } from "@/state/plannerStore";

export function PlanGenerationControls() {
  const mutation = useGeneratePlan();
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);
  const activeScenarioId = usePlannerStore((state) => state.activeScenarioId);
  const inputs = usePlannerStore((state) => state.inputs);
  const { data: jobStatus } = usePlanJobStatus(activeScenarioId);

  const hasUnitMix = inputs.unitMix && inputs.unitMix.length > 0;

  // Keep button in "generating" state while the background job is still running,
  // not just while the initial POST is in flight.
  const isJobActive =
    !!activeScenarioId &&
    (!jobStatus || jobStatus.status === "pending" || jobStatus.status === "running");
  const isGenerating = mutation.isPending || isJobActive;
  const disabled = !selectedPlotId || !hasUnitMix || isGenerating;

  return (
    <div className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-neutral-50 disabled:opacity-60"
      >
        {isGenerating && (
          <span className="h-3 w-3 animate-spin rounded-full border border-neutral-50 border-t-transparent" />
        )}
        {isGenerating ? "Generating…" : "Generate plan"}
      </button>
      {mutation.isError && (
        <span className="text-xs text-red-600">
          Unable to generate plan. Check inputs and try again.
        </span>
      )}
      {jobStatus?.status === "failed" && (
        <span className="text-xs text-red-600">
          Plan failed
          {jobStatus.errorMessage ? `: ${jobStatus.errorMessage}` : ""}
        </span>
      )}
    </div>
  );
}

export function PlanGenerationStatus() {
  const activeScenarioId = usePlannerStore(
    (state) => state.activeScenarioId,
  );
  const { data: status } = usePlanJobStatus(activeScenarioId);

  if (!activeScenarioId) return null;

  // While the first status poll is in flight (status not yet known), show "working".
  if (!status || status.status === "pending" || status.status === "running") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-neutral-500">
        <span className="h-2.5 w-2.5 animate-spin rounded-full border border-neutral-400 border-t-transparent" />
        Computing layout…
      </span>
    );
  }

  if (status.status === "completed") {
    return (
      <span className="text-xs text-emerald-600">Plan ready</span>
    );
  }

  if (status.status === "failed") {
    return (
      <span className="text-xs text-red-600">
        Plan failed{status.errorMessage ? `: ${status.errorMessage}` : ""}
      </span>
    );
  }

  return null;
}

