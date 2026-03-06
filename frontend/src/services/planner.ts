import { startPlanJob, type PlanGenerationRequest } from "./plannerService";

export async function generatePlan(data: PlanGenerationRequest) {
  return startPlanJob(data);
}

