import type { GeometryLayerType, GeometryFeature, GeometryModel } from "./geojsonParser";

export function filterFeaturesByLayer(
  model: GeometryModel,
  layer: GeometryLayerType,
): GeometryFeature[] {
  return model.features.filter((feature) => feature.layer === layer);
}

export function groupFeaturesByLayer(
  model: GeometryModel,
): Record<GeometryLayerType, GeometryFeature[]> {
  const groups = {} as Record<GeometryLayerType, GeometryFeature[]>;

  for (const feature of model.features) {
    if (!groups[feature.layer]) {
      groups[feature.layer] = [];
    }
    groups[feature.layer].push(feature);
  }

  return groups;
}

