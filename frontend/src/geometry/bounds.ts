import type { Position } from "./geometryNormalizer";
import type { GeometryModel } from "./geojsonParser";
import { collectAllPositions } from "./geojsonParser";

export type Bounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

export function computeBoundsFromPositions(
  positions: Position[],
): Bounds | null {
  if (!positions.length) return null;

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const [x, y] of positions) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }

  return { minX, minY, maxX, maxY };
}

export function computeBoundsForModel(
  model: GeometryModel,
): Bounds | null {
  const positions = collectAllPositions(model);
  return computeBoundsFromPositions(positions);
}

