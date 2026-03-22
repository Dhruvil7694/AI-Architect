import type { Position } from "@/geometry/geometryNormalizer";
import type { ViewTransform } from "@/geometry/transform";
import { projectPosition } from "@/geometry/transform";

// ── Designation colors ──────────────────────────────────────────────

export type DesignationStyle = { fill: string; stroke: string };

export function getDesignationColor(designation?: string | null): DesignationStyle {
  if (!designation) return { fill: "rgba(226,232,240,0.4)", stroke: "#475569" };
  const d = designation.toUpperCase();
  if (d.includes("RESIDENTIAL") || d.includes("SALE FOR RES"))
    return { fill: "rgba(254,202,202,0.5)", stroke: "#dc2626" };
  if (d.includes("COMMERCIAL") || d.includes("SALE FOR COM"))
    return { fill: "rgba(254,240,138,0.55)", stroke: "#ca8a04" };
  if (d.includes("PUBLIC PURPOSE") || d.includes("PUBLIC"))
    return { fill: "rgba(253,186,116,0.5)", stroke: "#c2410c" };
  if (d.includes("OPEN SPACE") || d.includes("GARDEN"))
    return { fill: "rgba(134,239,172,0.5)", stroke: "#16a34a" };
  if (d.includes("S.E.W") || d.includes("SEWAGE") || d.includes("E.W.S"))
    return { fill: "rgba(196,181,253,0.4)", stroke: "#7c3aed" };
  if (d.includes("ROAD") || d.includes("SCHEME ROAD"))
    return { fill: "rgba(251,191,114,0.6)", stroke: "#b45309" };
  return { fill: "rgba(226,232,240,0.4)", stroke: "#475569" };
}

// ── Screen-space polygon area (shoelace) ────────────────────────────

export function computeScreenArea(
  ring: Position[],
  transform: ViewTransform,
): number {
  if (ring.length < 3) return 0;
  let acc = 0;
  const projected = ring.map((p) => projectPosition([Number(p[0]), Number(p[1])], transform));
  for (let i = 0; i < projected.length; i++) {
    const [x1, y1] = projected[i];
    const [x2, y2] = projected[(i + 1) % projected.length];
    acc += x1 * y2 - x2 * y1;
  }
  return Math.abs(acc) / 2;
}

// ── Adaptive font size ──────────────────────────────────────────────

export function getAdaptiveFontSize(screenArea: number): {
  fontSize: number;
  fontWeight: string;
} {
  if (screenArea > 2000) return { fontSize: 11, fontWeight: "700" };
  if (screenArea > 500) return { fontSize: 8, fontWeight: "600" };
  return { fontSize: 6, fontWeight: "500" };
}

// ── Road centerline midpoint + angle ────────────────────────────────

export type RoadLabelPlacement = {
  x: number;
  y: number;
  angle: number;
};

export function computeRoadLabelPlacement(
  coords: Position[],
  transform: ViewTransform,
): RoadLabelPlacement | null {
  if (coords.length < 2) return null;

  const projected = coords.map((c) =>
    projectPosition([Number(c[0]), Number(c[1])], transform),
  );

  let totalLen = 0;
  const segLens: number[] = [];
  for (let i = 0; i < projected.length - 1; i++) {
    const dx = projected[i + 1][0] - projected[i][0];
    const dy = projected[i + 1][1] - projected[i][1];
    const len = Math.sqrt(dx * dx + dy * dy);
    segLens.push(len);
    totalLen += len;
  }
  if (totalLen === 0) return null;

  const half = totalLen / 2;
  let walked = 0;
  for (let i = 0; i < segLens.length; i++) {
    if (walked + segLens[i] >= half) {
      const t = (half - walked) / segLens[i];
      const x = projected[i][0] + t * (projected[i + 1][0] - projected[i][0]);
      const y = projected[i][1] + t * (projected[i + 1][1] - projected[i][1]);
      const dx = projected[i + 1][0] - projected[i][0];
      const dy = projected[i + 1][1] - projected[i][1];
      let angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
      if (angleDeg > 90) angleDeg -= 180;
      if (angleDeg < -90) angleDeg += 180;
      return { x, y, angle: angleDeg };
    }
    walked += segLens[i];
  }
  return null;
}

// ── Extract outer ring from GeoJSON geometry ────────────────────────

export function extractOuterRing(geometry: unknown): Position[] | null {
  const g = geometry as { type?: string; coordinates?: unknown };
  if (!g?.type || !g.coordinates) return null;
  if (g.type === "Polygon" && Array.isArray(g.coordinates) && Array.isArray(g.coordinates[0])) {
    return g.coordinates[0] as Position[];
  }
  if (
    g.type === "MultiPolygon" &&
    Array.isArray(g.coordinates) &&
    Array.isArray(g.coordinates[0]) &&
    Array.isArray(g.coordinates[0][0])
  ) {
    return g.coordinates[0][0] as Position[];
  }
  return null;
}
