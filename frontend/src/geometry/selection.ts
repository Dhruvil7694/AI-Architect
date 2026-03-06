/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Position } from "./geometryNormalizer";
import type { GeometryFeature, GeometryModel } from "./geojsonParser";

const HIT_TOLERANCE = 4; // px, can be tuned at call site with transforms

export type HitTestResult = {
  feature: GeometryFeature;
};

export function hitTestPointInModel(
  model: GeometryModel,
  point: Position,
  projectToWorld?: (pixel: Position) => Position,
): HitTestResult | null {
  const worldPoint = projectToWorld ? projectToWorld(point) : point;

  for (const feature of model.features) {
    if (feature.geometry.type === "Polygon") {
      if (pointInPolygon(worldPoint, feature.geometry.coordinates as Position[][])) {
        return { feature };
      }
    } else if (feature.geometry.type === "MultiPolygon") {
      const polygons: Position[][][] = feature.geometry
        .coordinates as Position[][][];
      for (const poly of polygons) {
        if (pointInPolygon(worldPoint, poly)) {
          return { feature };
        }
      }
    } else if (
      feature.geometry.type === "LineString" ||
      feature.geometry.type === "MultiLineString"
    ) {
      if (isPointNearLine(worldPoint, feature.geometry.coordinates as any)) {
        return { feature };
      }
    }
  }

  return null;
}

function pointInPolygon(point: Position, rings: Position[][]): boolean {
  // Ray casting on outer ring; ignores holes for simplicity here.
  const outerRing = rings[0];
  if (!outerRing || outerRing.length < 3) return false;

  const [x, y] = point;
  let inside = false;

  for (let i = 0, j = outerRing.length - 1; i < outerRing.length; j = i++) {
    const [xi, yi] = outerRing[i];
    const [xj, yj] = outerRing[j];

    const intersect =
      yi > y !== yj > y &&
      x <
        ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-9) +
          xi;

    if (intersect) inside = !inside;
  }

  return inside;
}

function isPointNearLine(
  point: Position,
  coordinates: Position[] | Position[][],
): boolean {
  const lines: Position[][] = Array.isArray(coordinates[0])
    ? (coordinates as Position[][])
    : [coordinates as Position[]];

  const [px, py] = point;

  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const [x1, y1] = line[i - 1];
      const [x2, y2] = line[i];
      const dist = distancePointToSegment(px, py, x1, y1, x2, y2);
      if (dist <= HIT_TOLERANCE) {
        return true;
      }
    }
  }

  return false;
}

function distancePointToSegment(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (dx === 0 && dy === 0) {
    return Math.hypot(px - x1, py - y1);
  }

  const t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy);
  const clampedT = Math.max(0, Math.min(1, t));
  const projX = x1 + clampedT * dx;
  const projY = y1 + clampedT * dy;

  return Math.hypot(px - projX, py - projY);
}

