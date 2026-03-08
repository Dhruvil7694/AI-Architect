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
  // §13.12.2 — Lift count
  lift_required: boolean;
  lift_provided: number;
  lift_required_by_height: number;
  lift_required_by_units: number;
  lift_required_gdcr: number;
  lift_capped: boolean;
  lift_cap_reason: string | null;
  lift_ok: boolean;
  // §13.12.2 — Fire lift (> 25 m)
  fire_lift_required: boolean;
  fire_lift_provided: boolean;
  fire_lift_ok: boolean;
  // §13.12.3 — Lift landing (1.8 m × 2.0 m clear)
  lift_landing_d_m: number;
  lift_landing_w_m: number;
  lift_landing_ok: boolean;
  // Table 13.2 — Staircases
  stair_count: number;
  stair_width_m: number;
  stair_width_required_m: number;
  stair_width_ok: boolean;
  stair_tread_mm: number;
  stair_riser_mm: number;
  stair_geometry_ok: boolean;
  // Corridor
  corridor_width_m: number;
  corridor_width_ok: boolean;
  // §13.1.7 — Clearance heights
  storey_height_m: number;
  clearance_habitable_m: number;
  clearance_habitable_ok: boolean;
  clearance_service_m: number;
  clearance_service_ok: boolean;
  // FSI exemptions
  fsi_exemptions: string[];
}

export interface FloorPlanMetrics {
  footprintSqm: number;
  floorLengthM: number;
  floorWidthM: number;
  coreSqm: number;
  corridorSqm: number;
  fsiExemptSqm: number;
  circulationSqm: number;
  unitAreaPerFloorSqm: number;
  nUnitsPerFloor: number;
  nTotalUnits: number;
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

// ── Unit interior generation (Stage 3) ───────────────────────────────────────

export interface UnitInteriorRequest {
  unit_type: string;
  unit_width_m: number;
  unit_depth_m: number;
}

export interface UnitRoomProperties {
  name: string;
  room_type: string;
  area_sqm: number;
  width_m: number;
  depth_m: number;
  gdcr_ok: boolean;
  gdcr_min_area: number;
  gdcr_min_w: number;
  gdcr_ref: string;
}

export interface UnitRoomFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: UnitRoomProperties;
}

export interface UnitInteriorLayout {
  type: "FeatureCollection";
  features: UnitRoomFeature[];
}

export interface UnitGdcrSummary {
  all_ok: boolean;
  violations: Array<{ room: string; ref: string; issue: string }>;
}

export interface UnitInteriorResponse {
  status: "ok" | "error";
  unit_type: string;
  unit_width_m: number;
  unit_depth_m: number;
  layout: UnitInteriorLayout;
  rooms: Array<{
    name: string;
    type: string;
    area_sqm: number;
    width_m: number;
    depth_m: number;
    gdcr_ok: boolean;
    gdcr_ref: string;
  }>;
  gdcr_summary: UnitGdcrSummary;
}

export async function generateUnitInterior(
  payload: UnitInteriorRequest,
): Promise<UnitInteriorResponse> {
  return httpRequest<UnitInteriorResponse, UnitInteriorRequest>(
    "/api/development/unit-interior/",
    { method: "POST", body: payload },
  );
}

