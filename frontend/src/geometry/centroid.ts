import type { Position } from "./geometryNormalizer";
import type { GeometryFeature } from "./geojsonParser";

function polygonCentroid(coords: Position[][]): Position | null {
  if (!Array.isArray(coords) || !coords.length) return null;
  const outer = coords[0] ?? [];
  if (!Array.isArray(outer) || !outer.length) return null;
  let sumX = 0;
  let sumY = 0;
  let count = 0;
  for (const pt of outer) {
    if (!Array.isArray(pt) || pt.length < 2) continue;
    const x = Number(pt[0]);
    const y = Number(pt[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    sumX += x;
    sumY += y;
    count += 1;
  }
  return count ? [sumX / count, sumY / count] : null;
}

function lineCentroid(coords: Position[]): Position | null {
  if (!Array.isArray(coords) || !coords.length) return null;
  const first = coords[0];
  if (!Array.isArray(first) || first.length < 2) return null;
  if (coords.length === 1) return [Number(first[0]), Number(first[1])];
  let sumX = 0;
  let sumY = 0;
  for (const pt of coords) {
    if (!Array.isArray(pt) || pt.length < 2) continue;
    sumX += Number(pt[0]);
    sumY += Number(pt[1]);
  }
  return [sumX / coords.length, sumY / coords.length];
}

/** Returns centroid of a feature's geometry in world coordinates, or null. */
export function getFeatureCentroid(feature: GeometryFeature): Position | null {
  const g = feature.geometry;
  if (g.type === "Polygon") return polygonCentroid(g.coordinates as Position[][]);
  if (g.type === "MultiPolygon") {
    const polys = g.coordinates as Position[][][];
    if (!polys?.length) return null;
    return polygonCentroid(polys[0]);
  }
  if (g.type === "LineString") return lineCentroid(g.coordinates as Position[]);
  if (g.type === "MultiLineString") {
    const lines = g.coordinates as Position[][];
    if (!lines?.length) return null;
    return lineCentroid(lines[0]);
  }
  return null;
}
