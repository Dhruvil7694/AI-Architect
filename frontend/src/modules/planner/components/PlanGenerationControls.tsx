"use client";

import {
  useGeneratePlan,
  usePlanJobStatus,
} from "@/modules/planner/hooks/usePlannerData";
import { usePlannerStore } from "@/state/plannerStore";

export function PlanGenerationControls() {
  const mutation = useGeneratePlan();
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);
  const inputs = usePlannerStore((state) => state.inputs);
  const hasUnitMix = inputs.unitMix && inputs.unitMix.length > 0;

  const disabled = !selectedPlotId || !hasUnitMix || mutation.isPending;

  return (
    <div className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={disabled}
        className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-neutral-50 disabled:opacity-60"
      >
        {mutation.isPending ? "Generating…" : "Generate plan"}
      </button>
      {mutation.isError && (
        <span className="text-xs text-red-600">
          Unable to generate plan. Check inputs and try again.
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

  if (!activeScenarioId || !status) {
    return (
      <span className="text-xs text-neutral-400">
        No plan generation in progress.
      </span>
    );
  }

  if (status.status === "pending" || status.status === "running") {
    const progressText =
      typeof status.progress === "number"
        ? ` (${Math.round(status.progress)}%)`
        : "";
    return (
      <span className="text-xs text-neutral-500">
        Generating plan…{progressText}
      </span>
    );
  }

  if (status.status === "completed") {
    return (
      <span className="text-xs text-emerald-600">
        Plan generation completed.
      </span>
    );
  }

  if (status.status === "failed") {
    return (
      <span className="text-xs text-red-600">
        Plan generation failed
        {status.errorMessage ? `: ${status.errorMessage}` : ""}
      </span>
    );
  }

  return null;
}

