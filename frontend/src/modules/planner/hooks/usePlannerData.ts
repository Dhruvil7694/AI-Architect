import { useQuery, useMutation } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import {
  getSiteMetrics,
  startPlanJob,
  getPlanJobStatus,
  getPlanJobResult,
  type SiteMetrics,
  type PlanGenerationRequest,
  type PlanJobStatus,
  type PlanResultDto,
} from "@/services/plannerService";
import { HttpError } from "@/services/httpClient";
import { usePlannerStore } from "@/state/plannerStore";
import type { GeometryModel } from "@/geometry/geojsonParser";
import { mapPlanGeometryToModel } from "@/geometry/planGeometryMapper";

export function useSiteMetrics(plotId: string | null) {
  return useQuery<SiteMetrics | null>({
    queryKey: plotId
      ? queryKeys.planner.metrics(plotId)
      : ["planner", "metrics", "none"],
    queryFn: () => (plotId ? getSiteMetrics(plotId) : Promise.resolve(null)),
    enabled: Boolean(plotId),
  });
}

export function usePlanJobStatus(jobId: string | null) {
  return useQuery<PlanJobStatus | null>({
    queryKey: jobId
      ? ["planner", "plan-job-status", jobId]
      : ["planner", "plan-job-status", "none"],
    queryFn: () => (jobId ? getPlanJobStatus(jobId) : Promise.resolve(null)),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && (data.status === "pending" || data.status === "running")
        ? 1500
        : false;
    },
  });
}

export function usePlanGeometry(jobId: string | null) {
  const updateScenario = usePlannerStore((s) => s.updateScenario);

  return useQuery<GeometryModel | null>({
    queryKey: jobId
      ? queryKeys.planner.plan("any", jobId)
      : ["planner", "plan", "none"],
    queryFn: async () => {
      if (!jobId) return null;
      try {
        const result: PlanResultDto = await getPlanJobResult(jobId);
        // Persist metrics into the active scenario for labelling.
        updateScenario(jobId, {
          planResultSummary: {
            ...(result as any).planResultSummary,
            metrics: result.metrics,
          },
        });
        return mapPlanGeometryToModel(result.geometry, result);
      } catch (err) {
        if (err instanceof HttpError && err.status === 409) {
          // Result not ready yet; let query keep polling.
          return null;
        }
        throw err;
      }
    },
    enabled: Boolean(jobId),
    refetchInterval: 1500,
  });
}

export function useGeneratePlan() {
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);
  const inputs = usePlannerStore((state) => state.inputs);
  const addScenario = usePlannerStore((state) => state.addScenario);

  return useMutation({
    mutationFn: async () => {
      if (!selectedPlotId) {
        throw new Error("No plot selected");
      }
      if (!inputs.unitMix || inputs.unitMix.length === 0) {
        throw new Error("Select at least one unit type");
      }
      const payload: PlanGenerationRequest = {
        plotId: selectedPlotId,
        inputs,
      };
      return startPlanJob(payload);
    },
    onSuccess: (response) => {
      const selectedPlotIdCurrent = selectedPlotId;
      if (!selectedPlotIdCurrent) return;

      const jobId = response.jobId;
      addScenario({
        id: jobId,
        label: `Scenario ${jobId}`,
        plotId: selectedPlotIdCurrent,
        inputs,
        planResultSummary: { status: "pending" },
        createdAt: new Date().toISOString(),
      });
    },
  });
}

