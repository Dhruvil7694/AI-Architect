import { useQuery, useMutation } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import {
  getSiteMetrics,
  startPlanJob,
  getPlanJobStatus,
  getPlanJobResult,
  generateFloorPlan,
  generateFloorCore,
  generateUnitInterior,
  generateAIScenarios,
  generateAIFloorPlan,
  generateFloorPlanPreviewImage,
  getPlanCritique,
  getFeasibility,
  getPlotExploration,
  type ExplorationResponse,
  type SiteMetrics,
  type PlanGenerationRequest,
  type PlanJobStatus,
  type PlanResultDto,
  type FloorPlanRequest,
  type FloorPlanResponse,
  type FloorCoreRequest,
  type FloorCoreResponse,
  type UnitInteriorRequest,
  type UnitInteriorResponse,
  type AIFloorPlanRequest,
  type AIFloorPlanResponse,
  type FloorPlanPreviewImageRequest,
  type FloorPlanPreviewImageResponse,
  type AIPlannerResponseDto,
  type PlanCritiqueResponse,
  type FeasibilityResponse,
} from "@/services/plannerService";
import { HttpError } from "@/services/httpClient";
import { usePlannerStore } from "@/state/plannerStore";
import type { GeometryModel } from "@/geometry/geojsonParser";
import { mapPlanGeometryToModel } from "@/geometry/planGeometryMapper";

export function useFeasibility(plotId: string | null) {
  return useQuery<FeasibilityResponse | null>({
    queryKey: plotId
      ? queryKeys.planner.feasibility(plotId)
      : ["planner", "feasibility", "none"],
    queryFn: () => (plotId ? getFeasibility(plotId) : Promise.resolve(null)),
    enabled: Boolean(plotId),
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes — feasibility rarely changes
  });
}

export function usePlotExploration(plotId: string | null) {
  return useQuery<ExplorationResponse | null>({
    queryKey: plotId
      ? queryKeys.planner.exploration(plotId)
      : ["planner", "exploration", "none"],
    queryFn: () => (plotId ? getPlotExploration(plotId) : Promise.resolve(null)),
    enabled: Boolean(plotId),
    staleTime: 5 * 60 * 1000,
  });
}

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
      // Before the first response arrives (data is undefined), keep polling so the
      // status is fetched immediately and the interval is active from the start.
      if (!data) return 1500;
      return data.status === "pending" || data.status === "running" ? 1500 : false;
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

export function useAIScenarios(plotId: string | null, brief: string | null) {
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);
  const inputs = usePlannerStore((s) => s.inputs);

  return useQuery<AIPlannerResponseDto | null>({
    queryKey: plotId
      ? queryKeys.planner.aiScenarios(plotId)
      : ["planner", "ai-scenarios", "none"],
    queryFn: async () => {
      if (!plotId || !brief) return null;
      // Ensure store stays in sync with the requested plot.
      setSelectedPlotId(plotId);
      return generateAIScenarios({ brief, site_id: plotId, inputs });
    },
    enabled: Boolean(plotId && brief),
  });
}

export function usePlanCritique() {
  return useMutation<PlanCritiqueResponse, Error, { jobId: string; userNote?: string }>({
    mutationFn: ({ jobId, userNote }) => getPlanCritique(jobId, userNote),
  });
}

export function useFloorPlan() {
  return useMutation<FloorPlanResponse, Error, FloorPlanRequest>({
    mutationFn: (payload: FloorPlanRequest) => generateFloorPlan(payload),
  });
}

export function useUnitLayout() {
  return useMutation<UnitInteriorResponse, Error, UnitInteriorRequest>({
    mutationFn: (payload: UnitInteriorRequest) => generateUnitInterior(payload),
  });
}

export function useFloorCore() {
  return useMutation<FloorCoreResponse, Error, FloorCoreRequest>({
    mutationFn: (payload) => generateFloorCore(payload),
  });
}

export function useAIFloorPlan() {
  return useMutation<AIFloorPlanResponse, Error, AIFloorPlanRequest>({
    mutationFn: (payload) => generateAIFloorPlan(payload),
  });
}

export function useFloorPlanPreviewImage() {
  return useMutation<
    FloorPlanPreviewImageResponse,
    Error,
    FloorPlanPreviewImageRequest
  >({
    mutationFn: (payload) => generateFloorPlanPreviewImage(payload),
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
      const scenarioNumber = usePlannerStore.getState().scenarios.length + 1;
      addScenario({
        id: jobId,
        label: `Scenario ${scenarioNumber}`,
        plotId: selectedPlotIdCurrent,
        inputs,
        planResultSummary: { status: "pending" },
        createdAt: new Date().toISOString(),
      });
      // Set the new job as the active scenario so usePlanJobStatus tracks it.
      usePlannerStore.getState().setActiveScenarioId(jobId);
    },
  });
}

