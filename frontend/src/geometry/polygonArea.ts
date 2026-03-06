import type { Position } from "./geometryNormalizer";

/** Shoelace formula for polygon area (world units). For GeoJSON, coordinates are [lng, lat]; area is in squared units of the CRS. */
export function polygonAreaSq(coords: Position[][]): number {
  if (!Array.isArray(coords) || !coords.length) return 0;
  const outer = coords[0] ?? [];
  if (!Array.isArray(outer) || outer.length < 3) return 0;
  let area = 0;
  const n = outer.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const a = outer[i] as Position;
    const b = outer[j] as Position;
    area += (a[0] ?? 0) * (b[1] ?? 0);
    area -= (b[0] ?? 0) * (a[1] ?? 0);
  }
  return Math.abs(area) / 2;
}

export function getFeatureAreaM2(feature: { geometry: { type: string; coordinates: unknown } }): number | null {
  const g = feature.geometry;
  if (g.type === "Polygon") return polygonAreaSq(g.coordinates as Position[][]);
  if (g.type === "MultiPolygon") {
    const polys = g.coordinates as Position[][][];
    if (!polys?.length) return null;
    let sum = 0;
    for (const poly of polys) sum += polygonAreaSq(poly);
    return sum;
  }
  return null;
}
