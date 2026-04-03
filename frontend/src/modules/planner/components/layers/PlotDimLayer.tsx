"use client";

import { useMemo } from "react";
import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { projectPosition } from "@/geometry/transform";

// DXF coordinates are in feet (SRID=0)
const DXF_PER_METRE = 3.28084;
const FEET_TO_METRES = 0.3048;
const DIM_OFFSET_M = 4.5;   // metres outward from edge for dim line
const MIN_EDGE_M   = 2.0;   // skip degenerate edges shorter than this

type Pt = [number, number];
type Ring = Pt[];

function computeCentroid(ring: Ring): Pt {
  let cx = 0, cy = 0;
  const n = ring.length;
  for (const [x, y] of ring) { cx += x; cy += y; }
  return [cx / n, cy / n];
}

function edgeOutwardNormal(p1: Pt, p2: Pt, centroid: Pt): Pt {
  const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
  const len = Math.hypot(dx, dy) || 1;
  let nx = -dy / len, ny = dx / len;
  const mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
  if ((centroid[0] - mx) * nx + (centroid[1] - my) * ny > 0) { nx = -nx; ny = -ny; }
  return [nx, ny];
}

function extractRing(feature: GeometryFeature): Ring | null {
  const g = feature.geometry;
  if (!g) return null;
  if (g.type === "Polygon") {
    const c = g.coordinates as number[][][];
    return c?.[0]?.map(([x, y]) => [x, y] as Pt) ?? null;
  }
  if (g.type === "MultiPolygon") {
    const c = g.coordinates as number[][][][];
    return c?.[0]?.[0]?.map(([x, y]) => [x, y] as Pt) ?? null;
  }
  return null;
}

interface DimAnnotation {
  // screen coords
  edgeP1s: Pt; edgeP2s: Pt;
  dimP1s:  Pt; dimP2s:  Pt;
  textPos: Pt;
  lengthM: number;
  angleDeg: number;
  isShort: boolean;
}

function buildAnnotations(ring: Ring, vt: ViewTransform): DimAnnotation[] {
  const n = ring.length - 1; // last == first
  if (n < 3) return [];
  const centroid = computeCentroid(ring.slice(0, n));
  const dimOffsetDxf = DIM_OFFSET_M * DXF_PER_METRE;
  const anns: DimAnnotation[] = [];

  for (let i = 0; i < n; i++) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % n];
    const edgeLenDxf = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
    const edgeLenM = edgeLenDxf * FEET_TO_METRES;
    if (edgeLenM < MIN_EDGE_M) continue;

    const isShort = edgeLenM < 6;
    const [nx, ny] = edgeOutwardNormal(p1, p2, centroid);
    const mid: Pt = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2];

    // Dimension line endpoints (outward offset)
    const dimP1: Pt = [p1[0] + nx * dimOffsetDxf, p1[1] + ny * dimOffsetDxf];
    const dimP2: Pt = [p2[0] + nx * dimOffsetDxf, p2[1] + ny * dimOffsetDxf];

    // Text position — slightly further out for short edges
    const textOffset = isShort ? dimOffsetDxf * 1.4 : dimOffsetDxf;
    const textDxf: Pt = [mid[0] + nx * textOffset, mid[1] + ny * textOffset];

    const edgeP1s = projectPosition(p1, vt) as Pt;
    const edgeP2s = projectPosition(p2, vt) as Pt;
    const dimP1s  = projectPosition(dimP1, vt) as Pt;
    const dimP2s  = projectPosition(dimP2, vt) as Pt;
    const textPos = projectPosition(textDxf, vt) as Pt;

    // Screen angle — keep text upright
    const sdx = edgeP2s[0] - edgeP1s[0], sdy = edgeP2s[1] - edgeP1s[1];
    let angleDeg = (Math.atan2(sdy, sdx) * 180) / Math.PI % 180;
    if (angleDeg > 90)  angleDeg -= 180;
    if (angleDeg < -90) angleDeg += 180;

    anns.push({
      edgeP1s, edgeP2s, dimP1s, dimP2s, textPos,
      lengthM: edgeLenM,
      angleDeg,
      isShort,
    });
  }
  return anns;
}

interface PlotDimLayerProps {
  features: GeometryFeature[]; // plotBoundary features
  viewTransform: ViewTransform;
  visible: boolean;
}

export function PlotDimLayer({ features, viewTransform, visible }: PlotDimLayerProps) {
  const annotations = useMemo(() => {
    if (!features.length) return [];
    const ring = extractRing(features[0]);
    if (!ring) return [];
    return buildAnnotations(ring, viewTransform);
  }, [features, viewTransform]);

  if (!visible || !annotations.length) return null;

  const CLR = "#475569"; // slate-600

  return (
    <g style={{ pointerEvents: "none" }}>
      {annotations.map((ann, i) => {
        const { edgeP1s, edgeP2s, dimP1s, dimP2s, textPos, lengthM, angleDeg, isShort } = ann;
        // Pixel width of dim line (to size tick marks)
        const dimLenPx = Math.hypot(dimP2s[0] - dimP1s[0], dimP2s[1] - dimP1s[1]);
        const showDimLine = dimLenPx > 8;

        const label = `${lengthM.toFixed(1)} m`;
        const fontSize = isShort ? 7 : 8;
        const labelW = label.length * fontSize * 0.58 + 8;
        const labelH = fontSize + 4;

        return (
          <g key={i}>
            {!isShort && showDimLine && (
              <>
                {/* Witness lines from edge corner to dim line */}
                <line x1={edgeP1s[0]} y1={edgeP1s[1]} x2={dimP1s[0]} y2={dimP1s[1]}
                  stroke={CLR} strokeWidth={0.6} strokeDasharray="2 2" />
                <line x1={edgeP2s[0]} y1={edgeP2s[1]} x2={dimP2s[0]} y2={dimP2s[1]}
                  stroke={CLR} strokeWidth={0.6} strokeDasharray="2 2" />

                {/* Dimension line */}
                <line x1={dimP1s[0]} y1={dimP1s[1]} x2={dimP2s[0]} y2={dimP2s[1]}
                  stroke={CLR} strokeWidth={0.9} />

                {/* Tick marks at ends */}
                {(["p1", "p2"] as const).map((end) => {
                  const [px, py] = end === "p1" ? dimP1s : dimP2s;
                  const dx = dimP2s[0] - dimP1s[0], dy = dimP2s[1] - dimP1s[1];
                  const len = Math.hypot(dx, dy) || 1;
                  // Perpendicular direction
                  const tx = -dy / len * 4, ty = dx / len * 4;
                  return (
                    <line key={end}
                      x1={px - tx} y1={py - ty}
                      x2={px + tx} y2={py + ty}
                      stroke={CLR} strokeWidth={0.9}
                    />
                  );
                })}
              </>
            )}

            {/* Label pill */}
            <g transform={`translate(${textPos[0]}, ${textPos[1]}) rotate(${angleDeg})`}>
              <rect
                x={-labelW / 2} y={-labelH / 2}
                width={labelW} height={labelH}
                rx={labelH / 2}
                fill="rgba(241,245,249,0.93)"
                stroke={CLR}
                strokeWidth={0.5}
              />
              <text
                x={0} y={0}
                textAnchor="middle"
                dominantBaseline="middle"
                style={{
                  fontSize,
                  fontWeight: 600,
                  fill: "#1e293b",
                  fontFamily: "system-ui, sans-serif",
                }}
              >
                {label}
              </text>
            </g>
          </g>
        );
      })}
    </g>
  );
}
