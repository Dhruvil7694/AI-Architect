"use client";

import { useEffect } from "react";
import { useGeneratePlan, usePlanJobStatus } from "@/modules/planner/hooks/usePlannerData";
import { usePlannerStore } from "@/state/plannerStore";
import { useGenerationProgress } from "./useGenerationProgress";

/**
 * Plan job for the workspace: placement still runs to produce tower geometry, then UI goes
 * straight to floor design (no site canvas step).
 */
export function useSitePlanGeneration() {
  const setPlannerStage = usePlannerStore((s) => s.setPlannerStage);
  const setSelectedTowerIndex = usePlannerStore((s) => s.setSelectedTowerIndex);
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const mutation = useGeneratePlan();
  const { data: jobStatus } = usePlanJobStatus(activeScenarioId);
  const backendProgress =
    typeof jobStatus?.progress === "number" ? jobStatus.progress : null;
  const { displayProgress, stageLabel } = useGenerationProgress(
    backendProgress,
    jobStatus?.status
  );

  useEffect(() => {
    if (!jobStatus) return;
    if (jobStatus.status === "completed") {
      setPlannerStage("floor-design");
    } else if (jobStatus.status === "failed") {
      setPlannerStage("input");
    }
  }, [jobStatus?.status, setPlannerStage]);

  const generatePlan = () => {
    setSelectedTowerIndex(null);
    setPlannerStage("plan-generating");
    mutation.mutate();
  };

  return {
    generatePlan,
    isGenerating: mutation.isPending || jobStatus?.status === "pending" || jobStatus?.status === "running",
    progress: displayProgress,
    stageLabel,
    error: mutation.error,
    jobStatus,
  };
}
