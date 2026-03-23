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

export interface SellableSummary {
  plotAreaSqYards: number;
  achievedFsi: number;
  sellablePerYard: number;
  totalSellableSqft: number;
  avgFlatTotalSqft: number;
  estimatedRcaPerFlatSqft: number;
  efficiencyRatio: number;
  segment: string;
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
  // Sellable area summary
  sellableSummary?: SellableSummary;
}

export interface PlanResultDto {
  planId?: string;
  jobId?: string;
  plotId: string;
  geometry: PlanGeometryDto;
  metrics: PlanResultMetrics & SiteMetrics;
  debug?: { buildableEnvelope?: GeoJsonInput; copCandidateZones?: GeoJsonInput[]; roadNetwork?: GeoJsonInput[]; towerZones?: GeoJsonInput[] };
}

// ── AI planner scenarios ────────────────────────────────────────────────────────

export interface ProgramSpecDto {
  unit_mix: {
    "1bhk_compact": number;
    "2bhk_compact": number;
    "2bhk_luxury": number;
    "3bhk_luxury": number;
  };
  target_units: number;
  preferred_towers: number;
  max_floors: number;
  open_space_priority: "low" | "medium" | "high";
  density_priority: "low" | "medium" | "high";
}

export interface AIPlannerScenarioDto {
  label: string;
  tower_count: number;
  fsi_target: number;
  plan: PlanResultDto;
  design_insights: string[];
}

export interface AIPlannerResponseDto {
  program_spec: ProgramSpecDto;
  scenarios: AIPlannerScenarioDto[];
}

export async function generateAIScenarios(payload: {
  brief: string;
  site_id: string;
  inputs?: PlannerInputs;
}): Promise<AIPlannerResponseDto> {
  return httpRequest<AIPlannerResponseDto, {
    brief: string;
    site_id: string;
    inputs?: PlannerInputs;
  }>("/api/planner/ai_scenarios", {
    method: "POST",
    body: payload,
  });
}

export interface PlanCritiqueResponse {
  insights: string[];
}

export async function getPlanCritique(
  jobId: string,
  userNote?: string,
): Promise<PlanCritiqueResponse> {
  return httpRequest<PlanCritiqueResponse, { user_note: string }>(
    `/api/development/plan-jobs/${jobId}/critique/`,
    {
      method: "POST",
      body: { user_note: userNote ?? "" },
    },
  );
}

// ── Feasibility analysis ────────────────────────────────────────────────────

export interface FloorPlanCompat {
  canFit1bhk: boolean;
  canFit2bhk: boolean;
  canFit3bhk: boolean;
  canFit4bhk: boolean;
  canFit5bhk: boolean;
  estimatedUnitsPerFloor: number;
  footprintWidthM: number;
  footprintDepthM: number;
  coreType: string;
  notes: string[];
}

export interface TowerOption {
  nTowers: number;
  isFeasible: boolean;
  minFloors: number;
  maxFloors: number;
  estimatedFootprintSqm: number;
  estimatedFsiAtMax: number;
  heightBand: string;
  footprintWidthM: number;
  footprintDepthM: number;
  floorPlanNotes: string[];
  floorPlanCompat?: FloorPlanCompat;
  reason: string;
}

export interface BuildingTypeOption {
  id: number;
  label: string;
  effectiveMaxFloors: number;
  maxHeightM: number;
  liftRequired: boolean;
  fireStairRequired: boolean;
  copRequired: boolean;
  typicalEfficiency: number;
}

export interface CoreConfigOption {
  unitsPerCore: number;
  segment: string;
  label: string;
  preferredPattern: string;
}

export interface SellableEstimate {
  achievedFsi: number;
  sellablePerYard: number;
  totalSellableSqft: number;
  efficiencyRatio: number;
}

export interface FeasibilityResponse {
  plotId: string;
  plotAreaSqm: number;
  maxHeightM: number;
  maxFloors: number;
  maxFSI: number;
  maxGCPct: number;
  roadWidthM: number;
  maxFeasibleTowers: number;
  recommendedTowers: number;
  recommendedFloors: number;
  recommendationReason: string;
  suggestions: string[];
  towerOptions: TowerOption[];
  floorPlanCompat?: FloorPlanCompat;
  permissibleBuildingTypes?: BuildingTypeOption[];
  coreConfigs?: CoreConfigOption[];
  sellableEstimate?: SellableEstimate;
}

export interface FeasibilityValidation {
  isValid: boolean;
  warnings: string[];
  errors: string[];
  suggestions: string[];
  feasibility: FeasibilityResponse;
}

export async function getFeasibility(
  plotId: string,
): Promise<FeasibilityResponse> {
  return httpRequest<FeasibilityResponse>(
    `/api/development/feasibility/${encodeURIComponent(plotId)}/`,
    { method: "GET" },
  );
}

export async function validateFeasibility(
  plotId: string,
  payload: {
    towerCount: number | "auto";
    minFloors?: number;
    maxFloors?: number;
    unitMix?: string[];
    storeyHeightM?: number;
  },
): Promise<FeasibilityValidation> {
  return httpRequest<FeasibilityValidation, typeof payload>(
    `/api/development/feasibility/${encodeURIComponent(plotId)}/validate/`,
    { method: "POST", body: payload },
  );
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
  const raw = await httpRequest<PlanJobStatus>(
    `/api/development/plan-jobs/${jobId}/status/`,
    { method: "GET" },
  );
  // Backend returns UPPERCASE status ("PENDING", "RUNNING", etc.) — normalise to lowercase.
  return { ...raw, status: raw.status?.toLowerCase() as PlanJobStatusValue };
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

// ── Placement debug types ─────────────────────────────────────────────────────

/** Scalar quality metrics emitted by the placement engine instrumentation. */
export interface PlacementDebugMetrics {
  // The 8 required metrics
  envelope_area_sqft: number;
  footprint_area_sqft: number;
  leftover_area_sqft: number;
  leftover_compactness_score: number;
  road_frontage_length_m: number;
  tower_orientation_angles_deg: number[];
  cop_area_sqft: number;
  cop_min_dimension_m: number;
  // Derived ratios
  footprint_utilization_pct: number;
  leftover_utilization_pct: number;
  n_towers_placed: number;
  // Dominant open-space heuristic
  open_space_consolidation?: number;
  largest_open_area_sqft?: number;
  edge_alignment_ratio?: number;
}

export interface PlacementDebugFeatureProperties {
  layer:
    | "buildable_envelope"
    | "spacing_buffer"
    | "leftover_polygon"
    | "selected_footprint"
    | "cop_area";
  label?: string;
  area_sqft?: number;
  tower_index?: number;
  spacing_required_m?: number;
  min_dimension_m?: number;
  cop_strategy?: string | null;
  compactness_score?: number;
  width_m?: number;
  depth_m?: number;
  orientation_angle_deg?: number;
  orientation_label?: string;
  aspect_ratio?: number;
}

export interface PlacementDebugFeature {
  type: "Feature";
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
  properties: PlacementDebugFeatureProperties;
}

export interface PlacementDebugGeoJson {
  type: "FeatureCollection";
  features: PlacementDebugFeature[];
  metadata?: {
    n_towers_placed: number;
    building_height_m: number;
    spacing_required_m: number;
    packing_mode: string | null;
    coordinate_system: string;
    layer_order: string[];
  };
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
  layer: "footprint_bg" | "corridor" | "core" | "stair" | "lobby" | "lift" | "unit" | "balcony" | "room" | "wall" | "door" | "window";
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
  // Balcony (§13.1.12)
  fsi_exempt?: boolean;
  has_balcony?: boolean;
  balcony_sqm?: number;
  // Ventilation (§13.1.11)
  ventilation_ok?: boolean;
  required_window_sqm?: number;
  available_window_sqm?: number;
  // Room subdivision
  room_type?: string;
  // Wall lines
  wall_type?: "external" | "party" | "internal" | "entry";
  thickness_m?: number;
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
  // §13.1.11 — Ventilation
  ventilation_units_total?: number;
  ventilation_units_fail?: number;
  ventilation_ok?: boolean;
  // §13.1.12 — Balconies
  balcony_provided?: boolean;
  balcony_count?: number;
  balcony_depth_m?: number;
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
  balconySqmPerFloor?: number;
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
  /** Populated when the backend runs through the full development pipeline. */
  placement_debug_metrics?: PlacementDebugMetrics;
  placement_debug_geojson?: PlacementDebugGeoJson;
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

// ── Floor core (circulation core) generation ──────────────────────────────────

export interface FloorCoreRequest {
  footprint: { type: "Polygon"; coordinates: number[][][] };
  n_floors: number;
  building_height_m: number;
  target_units_per_floor?: number;
  orientation_deg?: number | null;
  tower_type?: string;
}

export interface FloorCoreGraphNode {
  id: string;
  type: string;
  centroid: [number, number];
  degree: number;
}

export interface FloorCoreGraphEdge {
  from: string;
  to: string;
  distance_m: number;
}

export interface FloorCoreMetrics {
  core_type: string;
  n_lifts: number;
  n_stairs: number;
  core_area_sqm: number;
  corridor_area_sqm: number;
  circulation_pct: number;
  footprint_area_sqm: number;
  max_travel_distance_m: number;
  stair_separation_m: number;
}

export interface FloorCoreCapacity {
  people_per_lift: number;
  stair_capacity_persons_per_min: number;
  corridor_density_persons_per_m: number;
}

export interface FloorCoreCompliance {
  corridor_width_ok: boolean;
  travel_distance_ok: boolean;
  travel_distance_max_m: number;
  dead_end_ok: boolean;
  dead_end_max_m: number;
  dead_end_count: number;
  stair_separation_ok: boolean;
  stair_separation_m: number;
  stair_separation_required_m: number;
  violations: string[];
  warnings: string[];
}

export interface FloorCoreResponse {
  status: "ok" | "error";
  core_type: string;
  layout: FloorPlanLayout;
  graph: { nodes: FloorCoreGraphNode[]; edges: FloorCoreGraphEdge[] };
  metrics: FloorCoreMetrics;
  capacity: FloorCoreCapacity | null;
  compliance: FloorCoreCompliance;
  corridor_centerline?: { type: "LineString"; coordinates: number[][] } | null;
  error?: string;
}

export async function generateFloorCore(
  payload: FloorCoreRequest,
): Promise<FloorCoreResponse> {
  return httpRequest<FloorCoreResponse, FloorCoreRequest>(
    "/api/development/floor-core/",
    { method: "POST", body: payload },
  );
}

// ── Unit interior generation (Stage 3) ───────────────────────────────────────

export interface UnitInteriorRequest {
  unit_type: string;
  unit_width_m: number;
  unit_depth_m: number;
  design_brief?: string;
}

export interface UnitFurnitureItem {
  type: string;
  x: number; y: number; w: number; h: number;
}

export interface UnitRoomData {
  name: string;
  type: string;
  x: number; y: number; w: number; h: number;
  area_sqm: number;
  width_m: number;
  depth_m: number;
  gdcr_ok: boolean;
  gdcr_ref: string;
  gdcr_min_area: number;
  gdcr_min_w: number;
  door_wall: "north" | "south" | "east" | "west";
  door_offset: number;
  door_width: number;
  window_walls: string[];
  window_offset: number | null;
  window_width: number;
  furniture: UnitFurnitureItem[];
}

export interface UnitGdcrSummary {
  all_ok: boolean;
  violations: Array<{ room: string; ref: string; issue: string }>;
}

export interface UnitInteriorResponse {
  status: "ok" | "error";
  source: "llm" | "template";
  unit_type: string;
  unit_width_m: number;
  unit_depth_m: number;
  design_notes: string;
  rooms: UnitRoomData[];
  gdcr_summary: UnitGdcrSummary;
  warnings: string[];
}

// Keep old types for backward compatibility
export type UnitRoomProperties = UnitRoomData;
export interface UnitRoomFeature {
  type: "Feature"; id: string;
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: UnitRoomProperties;
}
export interface UnitInteriorLayout {
  type: "FeatureCollection"; features: UnitRoomFeature[];
}

export async function generateUnitInterior(
  payload: UnitInteriorRequest,
): Promise<UnitInteriorResponse> {
  return httpRequest<UnitInteriorResponse, UnitInteriorRequest>(
    "/api/development/unit-interior/",
    { method: "POST", body: payload },
  );
}

