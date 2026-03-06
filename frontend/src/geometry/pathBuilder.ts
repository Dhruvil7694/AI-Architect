import type { Position } from "./geometryNormalizer";
import type { GeometryFeature } from "./geojsonParser";
import type { ViewTransform } from "./transform";
import { projectPosition } from "./transform";

export function geometryFeatureToPath(
  feature: GeometryFeature,
  transform: ViewTransform,
): string {
  const { geometry } = feature;

  if (geometry.type === "Polygon") {
    return polygonToPath(geometry.coordinates, transform);
  }

  if (geometry.type === "MultiPolygon") {
    return multiPolygonToPath(geometry.coordinates, transform);
  }

  if (geometry.type === "LineString") {
    return lineToPath(geometry.coordinates, transform);
  }

  if (geometry.type === "MultiLineString") {
    return multiLineToPath(geometry.coordinates, transform);
  }

  return "";
}

function polygonToPath(
  coordinates: Position[][],
  transform: ViewTransform,
): string {
  if (!Array.isArray(coordinates) || !coordinates.length) return "";

  const commands: string[] = [];

  coordinates.forEach((ring, index) => {
    if (!Array.isArray(ring) || !ring.length) return;
    const [first, ...rest] = ring;
    const [x0, y0] = projectPosition(
      [Number(first[0]), Number(first[1])],
      transform,
    );
    const moveCmd = index === 0 ? "M" : "M";
    commands.push(`${moveCmd}${x0},${y0}`);
    rest.forEach((point) => {
      const [x, y] = projectPosition(
        [Number(point[0]), Number(point[1])],
        transform,
      );
      commands.push(`L${x},${y}`);
    });
    commands.push("Z");
  });

  return commands.join(" ");
}

function multiPolygonToPath(
  coordinates: Position[][][],
  transform: ViewTransform,
): string {
  if (!Array.isArray(coordinates) || !coordinates.length) return "";
  return coordinates
    .map((poly) => polygonToPath(poly, transform))
    .filter(Boolean)
    .join(" ");
}

function lineToPath(
  coordinates: Position[],
  transform: ViewTransform,
): string {
  if (!Array.isArray(coordinates) || !coordinates.length) return "";

  const commands: string[] = [];
  const [first, ...rest] = coordinates;
  const [x0, y0] = projectPosition(
    [Number(first[0]), Number(first[1])],
    transform,
  );
  commands.push(`M${x0},${y0}`);

  rest.forEach((point) => {
    const [x, y] = projectPosition(
      [Number(point[0]), Number(point[1])],
      transform,
    );
    commands.push(`L${x},${y}`);
  });

  return commands.join(" ");
}

function multiLineToPath(
  coordinates: Position[][],
  transform: ViewTransform,
): string {
  if (!Array.isArray(coordinates) || !coordinates.length) return "";
  return coordinates
    .map((line) => lineToPath(line, transform))
    .filter(Boolean)
    .join(" ");
}

