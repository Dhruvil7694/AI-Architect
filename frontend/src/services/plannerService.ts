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

// ── Floor plan generation ─────────────────────────────────────────────────────

export interface FloorPlanRequest {
  footprint: { type: "Polygon"; coordinates: number[][][] };
  n_floors: number;
  building_height_m: number;
  unit_mix: string[];
  storey_height_m?: number;
  plot_area_sqm?: number;
}

export interface FloorPlanFeatureProperties {
  layer: "footprint_bg" | "corridor" | "core" | "stair" | "lobby" | "lift" | "unit";
  label?: string;
  area_sqm?: number;
  unit_id?: string;
  unit_type?: string;
  carpet_area_sqm?: number;
  rera_carpet_sqm?: number;
  index?: number;
  width_m?: number;
  depth_m?: number;
  side?: string;
  n_lifts?: number;
  n_stairs?: number;
  tread_mm?: number;
  riser_mm?: number;
  compliant_width?: boolean;
}

export interface FloorPlanFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: FloorPlanFeatureProperties;
}

export interface FloorPlanLayout {
  type: "FeatureCollection";
  features: FloorPlanFeature[];
}

export interface FloorPlanGdcr {
  lift_required: boolean;
  lift_provided: number;
  lift_ok: boolean;
  stair_count: number;
  stair_width_m: number;
  stair_width_ok: boolean;
  corridor_width_m: number;
  corridor_width_ok: boolean;
  storey_height_m: number;
  clearance_habitable_ok: boolean;
}

export interface FloorPlanMetrics {
  footprintSqm: number;
  floorLengthM: number;
  floorWidthM: number;
  coreSqm: number;
  corridorSqm: number;
  circulationSqm: number;
  unitAreaPerFloorSqm: number;
  nUnitsPerFloor: number;
  unitTypeCounts: Record<string, number>;
  nFloors: number;
  buildingHeightM: number;
  storeyHeightM: number;
  netBuaSqm: number;
  grossBuaSqm: number;
  achievedFSINet: number;
  achievedFSIGross: number;
  efficiencyPct: number;
  gdcr: FloorPlanGdcr;
}

export interface FloorPlanResponse {
  status: "ok" | "error";
  layout: FloorPlanLayout;
  metrics: FloorPlanMetrics;
  error?: string;
}

export async function generateFloorPlan(
  payload: FloorPlanRequest,
): Promise<FloorPlanResponse> {
  return httpRequest<FloorPlanResponse, FloorPlanRequest>(
    "/api/development/floor-plan/",
    { method: "POST", body: payload },
  );
}

