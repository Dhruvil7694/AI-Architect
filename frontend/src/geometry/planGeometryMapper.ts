import type { PlanGeometryDto, PlanResultDto } from "@/services/plannerService";
import type { GeometryLayerType, GeometryModel } from "./geojsonParser";
import { parseGeoJsonToModel } from "./geojsonParser";
import type { GeoJsonInput } from "./geometryNormalizer";

function pushFromInput(
  features: GeometryModel["features"],
  input: GeoJsonInput | GeoJsonInput[] | undefined,
  layer: GeometryLayerType,
): void {
  if (input == null) return;
  const items = Array.isArray(input) ? input : [input];
  for (const item of items) {
    if (item == null) continue;
    const model = parseGeoJsonToModel(item, layer);
    features.push(...model.features);
  }
}

// Map PlanGeometryDto from the backend into a combined GeometryModel
export function mapPlanGeometryToModel(
  geometry: PlanGeometryDto,
  result?: PlanResultDto,
): GeometryModel {
  const features: GeometryModel["features"] = [];

  pushFromInput(features, geometry.plotBoundary, "plotBoundary");
  pushFromInput(features, geometry.envelope, "envelope");
  pushFromInput(features, geometry.cop, "cop");
  pushFromInput(features, geometry.copMargin, "copMargin");
  pushFromInput(features, geometry.internalRoads, "internalRoads");
  pushFromInput(features, geometry.roadCorridors, "roadCorridors");
  pushFromInput(features, geometry.towerZones, "towerZones");
  pushFromInput(features, geometry.towerFootprints, "towerFootprints");
  pushFromInput(features, geometry.spacingLines, "spacingLines");
  pushFromInput(features, geometry.labels, "labels");

  if (result?.debug) {
    pushFromInput(features, result.debug.buildableEnvelope, "buildableEnvelope");
    pushFromInput(features, result.debug.copCandidateZones, "copCandidateZones");
    pushFromInput(features, result.debug.roadNetwork, "roadNetwork");
  }

  return { features };
}

