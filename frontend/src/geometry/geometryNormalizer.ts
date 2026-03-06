/* eslint-disable @typescript-eslint/no-explicit-any */

export type Position = [number, number];

export type GeoJsonGeometryType =
  | "Polygon"
  | "MultiPolygon"
  | "LineString"
  | "MultiLineString";

export type GeoJsonGeometry = {
  type: GeoJsonGeometryType;
  coordinates: any;
};

export type GeoJsonFeature = {
  type: "Feature";
  id?: string | number;
  geometry: GeoJsonGeometry | null;
  properties?: Record<string, unknown> | null;
};

export type GeoJsonFeatureCollection = {
  type: "FeatureCollection";
  features: GeoJsonFeature[];
};

/** Raw GeoJSON Geometry (backend plot list returns this, not a Feature) */
export type GeoJsonGeometryStandalone = {
  type: GeoJsonGeometryType;
  coordinates: unknown;
};

export type GeoJsonInput =
  | GeoJsonFeature
  | GeoJsonFeatureCollection
  | GeoJsonGeometryStandalone
  | null
  | undefined;

export function isFeatureCollection(
  input: GeoJsonInput,
): input is GeoJsonFeatureCollection {
  return Boolean(input && input.type === "FeatureCollection");
}

export function isFeature(input: GeoJsonInput): input is GeoJsonFeature {
  return Boolean(input && input.type === "Feature");
}

/** Backend often returns raw Geometry (e.g. Polygon); normalizer needs Feature/FeatureCollection */
function isStandaloneGeometry(
  input: GeoJsonInput,
): input is GeoJsonGeometryStandalone {
  return Boolean(
    input &&
      typeof input === "object" &&
      "type" in input &&
      "coordinates" in input &&
      (input.type === "Polygon" ||
        input.type === "MultiPolygon" ||
        input.type === "LineString" ||
        input.type === "MultiLineString"),
  );
}

/**
 * Normalize arbitrary GeoJSON input:
 * - Drop null geometry features.
 * - Flatten MultiPolygon into multiple Polygon features.
 * - Remove holes (inner rings) from polygons when requested.
 * - Ensure coordinates are arrays of [x, y].
 */
export function normalizeGeoJson(
  input: GeoJsonInput,
  options: { removeHoles?: boolean } = {},
): GeoJsonFeature[] {
  const features: GeoJsonFeature[] = [];

  if (!input) {
    return features;
  }

  const sourceFeatures: GeoJsonFeature[] = isFeatureCollection(input)
    ? input.features
    : isFeature(input)
      ? [input]
      : isStandaloneGeometry(input)
        ? [{ type: "Feature", geometry: input, properties: {} }]
        : [];

  for (const rawFeature of sourceFeatures) {
    if (!rawFeature.geometry) continue;

    const { type, coordinates } = rawFeature.geometry;

    if (type === "Polygon") {
      const outerRing = normalizePolygonCoordinates(
        coordinates,
        options.removeHoles,
      );
      if (!outerRing) continue;

      features.push({
        ...rawFeature,
        geometry: {
          type: "Polygon",
          coordinates: outerRing,
        },
      });
    } else if (type === "MultiPolygon") {
      const multiCoords: any[] = Array.isArray(coordinates)
        ? coordinates
        : [];

      multiCoords.forEach((polyCoords, index) => {
        const ring = normalizePolygonCoordinates(
          polyCoords,
          options.removeHoles,
        );
        if (!ring) return;
        features.push({
          ...rawFeature,
          id:
            rawFeature.id !== undefined
              ? `${rawFeature.id}:${index}`
              : undefined,
          geometry: {
            type: "Polygon",
            coordinates: ring,
          },
        });
      });
    } else if (type === "LineString" || type === "MultiLineString") {
      // For line-based geometry, just ensure coordinates are 2D positions.
      features.push({
        ...rawFeature,
        geometry: {
          type,
          coordinates: normalizeLineCoordinates(coordinates),
        },
      });
    }
  }

  return features;
}

function normalizePolygonCoordinates(
  coordinates: any,
  removeHoles?: boolean,
): Position[][] | null {
  if (!Array.isArray(coordinates) || coordinates.length === 0) return null;

  // Polygon coordinates: [ outerRing, hole1, hole2, ... ]
  const outerRing: any[] = coordinates[0] ?? [];
  if (!Array.isArray(outerRing) || outerRing.length === 0) return null;

  const normalizedOuter: Position[] = outerRing
    .map(normalizePosition)
    .filter(Boolean) as Position[];

  if (normalizedOuter.length === 0) return null;

  if (removeHoles) {
    return [normalizedOuter];
  }

  const rings: Position[][] = [normalizedOuter];
  const holes: any[] = coordinates.slice(1);

  holes.forEach((ring) => {
    if (!Array.isArray(ring)) return;
    const normalizedHole: Position[] = ring
      .map(normalizePosition)
      .filter(Boolean) as Position[];
    if (normalizedHole.length) {
      rings.push(normalizedHole);
    }
  });

  return rings;
}

function normalizeLineCoordinates(coordinates: any): Position[] | Position[][] {
  if (!Array.isArray(coordinates)) return [];

  if (coordinates.length > 0 && Array.isArray(coordinates[0][0])) {
    // MultiLineString: array of line arrays
    return coordinates.map((line: any[]) =>
      (line.map(normalizePosition).filter(Boolean) as Position[]),
    );
  }

  // LineString
  return coordinates
    .map(normalizePosition)
    .filter(Boolean) as Position[];
}

function normalizePosition(coord: any): Position | null {
  if (!Array.isArray(coord) || coord.length < 2) return null;
  const x = Number(coord[0]);
  const y = Number(coord[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
}

