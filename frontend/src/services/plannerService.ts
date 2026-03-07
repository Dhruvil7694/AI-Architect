import { httpRequest } from "./httpClient";
import type { GeoJsonInput } from "@/geometry/geometryNormalizer";
import type { PlannerInputs } from "@/types/plannerInputs";

export interface SiteMetrics {
  plotId: string;
  plotAreaSqm: number;
  baseFSI: number;
  maxFSI: number;
  maxBUA: number;
  copAreaSqm: number;
  copStrategy: string;
}

export interface PlanGenerationRequest {
  plotId: string;
  inputs: PlannerInputs;
}

// Async job model
export interface PlanJobStartResponse {
  jobId: string;
}

export type PlanJobStatusValue =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface PlanJobStatus {
  jobId: string;
  status: PlanJobStatusValue;
  progress?: number;
  errorMessage?: string;
}

// Geometry DTO from backend – GeoJSON per layer (single or array)
export interface PlanGeometryDto {
  plotBoundary?: GeoJsonInput;
  envelope?: GeoJsonInput;
  cop?: GeoJsonInput;
  copMargin?: GeoJsonInput;
  internalRoads?: GeoJsonInput | GeoJsonInput[];
  roadCorridors?: GeoJsonInput | GeoJsonInput[];
  towerZones?: GeoJsonInput | GeoJsonInput[];
  towerFootprints?: GeoJsonInput | GeoJsonInput[];
  spacingLines?: GeoJsonInput | GeoJsonInput[];
  labels?: GeoJsonInput;
}

export interface PlanResultMetrics {
  // Plot / regulatory limits (echoed from backend)
  plotAreaSqm?: number;
  roadWidthM?: number;
  maxFSI?: number;
  maxBUA?: number;
  gdcrMaxHeightM?: number;
  // Achieved development
  nTowersRequested?: number;
  nTowersPlaced?: number;
  floorCount?: number;
  buildingHeightM?: number;
  totalFootprintSqm?: number;
  achievedBUA?: number;
  achievedFSI?: number;
  achievedGCPct?: number;
  // Legacy / other
  envelopeAreaSqft?: number;
  groundCoveragePct?: number;
  copAreaSqft?: number;
  copStatus?: string;
  spacingRequiredM?: number;
}

export interface PlanResultDto {
  planId?: string;
  jobId?: string;
  plotId: string;
  geometry: PlanGeometryDto;
  metrics: PlanResultMetrics & SiteMetrics;
  debug?: { buildableEnvelope?: GeoJsonInput; copCandidateZones?: GeoJsonInput[]; roadNetwork?: GeoJsonInput[]; towerZones?: GeoJsonInput[] };
}

export async function getSiteMetrics(
  plotId: string,
): Promise<SiteMetrics> {
  return httpRequest<SiteMetrics>(
    `/api/development/site-metrics/${encodeURIComponent(plotId)}/`,
    {
    method: "GET",
    },
  );
}

// Start a long-running plan generation job
export async function startPlanJob(
  payload: PlanGenerationRequest,
): Promise<PlanJobStartResponse> {
  return httpRequest<PlanJobStartResponse, PlanGenerationRequest>(
    "/api/development/plan/",
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function getPlanJobStatus(
  jobId: string,
): Promise<PlanJobStatus> {
  return httpRequest<PlanJobStatus>(
    `/api/development/plan-jobs/${jobId}/status/`,
    {
      method: "GET",
    },
  );
}

export async function getPlanJobResult(
  jobId: string,
): Promise<PlanResultDto> {
  return httpRequest<PlanResultDto>(
    `/api/development/plan-jobs/${jobId}/result/`,
    {
      method: "GET",
    },
  );
}

