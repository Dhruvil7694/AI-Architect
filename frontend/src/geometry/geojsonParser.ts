/* eslint-disable @typescript-eslint/no-explicit-any */

import type {
  GeoJsonFeature,
  GeoJsonInput,
  GeoJsonGeometry,
  Position,
} from "./geometryNormalizer";
import { normalizeGeoJson } from "./geometryNormalizer";

export type GeometryLayerType =
  | "plotBoundary"
  | "envelope"
  | "cop"
  | "copMargin"
  | "internalRoads"
  | "roadCorridors"
  | "towerZones"
  | "towerFootprints"
  | "spacingLines"
  | "labels"
  | "buildableEnvelope"
  | "copCandidateZones"
  | "roadNetwork";

export type GeometryKind =
  | "polygon"
  | "polyline";

export interface GeometryFeature {
  id: string;
  layer: GeometryLayerType;
  kind: GeometryKind;
  geometry: GeoJsonGeometry;
  properties: Record<string, unknown>;
}

export interface GeometryModel {
  features: GeometryFeature[];
}

export function parseGeoJsonToModel(
  input: GeoJsonInput,
  layer: GeometryLayerType,
): GeometryModel {
  const normalized = normalizeGeoJson(input, { removeHoles: false });

  const features: GeometryFeature[] = normalized
    .filter((feature) => feature.geometry !== null)
    .map((feature) => toGeometryFeature(feature, layer))
    .filter(Boolean) as GeometryFeature[];

  return { features };
}

function toGeometryFeature(
  feature: GeoJsonFeature,
  layer: GeometryLayerType,
): GeometryFeature | null {
  if (!feature.geometry) return null;

  const { type } = feature.geometry;

  const kind: GeometryKind =
    type === "Polygon" || type === "MultiPolygon" ? "polygon" : "polyline";

  const id =
    typeof feature.id === "string" || typeof feature.id === "number"
      ? String(feature.id)
      : createRandomId(layer);

  return {
    id,
    layer,
    kind,
    geometry: feature.geometry,
    properties: feature.properties ?? {},
  };
}

function createRandomId(layer: GeometryLayerType): string {
  return `${layer}-${Math.random().toString(36).slice(2, 10)}`;
}

export function collectAllPositions(
  model: GeometryModel,
): Position[] {
  const positions: Position[] = [];

  for (const feature of model.features) {
    const geom = feature.geometry;
    if (geom.type === "Polygon") {
      const rings: any[] = Array.isArray(geom.coordinates)
        ? geom.coordinates
        : [];
      rings.forEach((ring) => {
        if (!Array.isArray(ring)) return;
        ring.forEach((coord) => {
          if (Array.isArray(coord) && coord.length >= 2) {
            positions.push([Number(coord[0]), Number(coord[1])]);
          }
        });
      });
    } else if (geom.type === "MultiPolygon") {
      const polys: any[] = Array.isArray(geom.coordinates)
        ? geom.coordinates
        : [];
      polys.forEach((poly) => {
        const rings: any[] = Array.isArray(poly) ? poly : [];
        rings.forEach((ring) => {
          if (!Array.isArray(ring)) return;
          ring.forEach((coord) => {
            if (Array.isArray(coord) && coord.length >= 2) {
              positions.push([Number(coord[0]), Number(coord[1])]);
            }
          });
        });
      });
    } else if (geom.type === "LineString") {
      const coords: any[] = Array.isArray(geom.coordinates)
        ? geom.coordinates
        : [];
      coords.forEach((coord) => {
        if (Array.isArray(coord) && coord.length >= 2) {
          positions.push([Number(coord[0]), Number(coord[1])]);
        }
      });
    } else if (geom.type === "MultiLineString") {
      const lines: any[] = Array.isArray(geom.coordinates)
        ? geom.coordinates
        : [];
      lines.forEach((line) => {
        if (!Array.isArray(line)) return;
        line.forEach((coord) => {
          if (Array.isArray(coord) && coord.length >= 2) {
            positions.push([Number(coord[0]), Number(coord[1])]);
          }
        });
      });
    }
  }

  return positions;
}

