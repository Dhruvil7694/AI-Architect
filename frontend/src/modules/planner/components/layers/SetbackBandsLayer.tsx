"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { projectPosition } from "@/geometry/transform";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DXF_PER_METRE = 3.28084;

// ---------------------------------------------------------------------------
// GDCR lookup tables (client-side)
// ---------------------------------------------------------------------------

/** Front setback — GDCR Table 6.24 (8-tier) + H/5 formula */
function getFrontSetback(roadWidthM: number, buildingHeightM: number): number {
  const tableVal = (() => {
    if (roadWidthM <= 9.0)  return 2.5;
    if (roadWidthM <= 15.0) return 3.0;
    if (roadWidthM <= 18.0) return 4.5;
    if (roadWidthM <= 30.0) return 6.0;
    if (roadWidthM <= 45.0) return 7.5;
    return 9.0; // > 45 m road
  })();
  return Math.max(tableVal, buildingHeightM / 5.0);
}

/** Side/rear setback from building height — GDCR Table 6.26 (4-tier) */
function getSideRearSetback(heightM: number): number {
  if (heightM <= 16.5) return 3.0;
  if (heightM <= 25.0) return 4.0;
  if (heightM <= 45.0) return 6.0;
  return 8.0; // > 45 m
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

type Pt = [number, number];
type Ring = Pt[];

function computeCentroid(ring: Ring): Pt {
  let cx = 0, cy = 0;
  for (const [x, y] of ring) { cx += x; cy += y; }
  return [cx / ring.length, cy / ring.length];
}

function edgeOutwardNormal(p1: Pt, p2: Pt, centroid: Pt): Pt {
  const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
  const len = Math.hypot(dx, dy) || 1;
  let nx = -dy / len, ny = dx / len;
  const mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
  if ((centroid[0] - mx) * nx + (centroid[1] - my) * ny > 0) { nx = -nx; ny = -ny; }
  return [nx, ny];
}

function detectRoadEdgeIndex(ring: Ring): number {
  const n = ring.length - 1;
  let best = -1, bestI = 0;
  for (let i = 0; i < n; i++) {
    const len = Math.hypot(
      ring[(i + 1) % n][0] - ring[i][0],
      ring[(i + 1) % n][1] - ring[i][1],
    );
    if (len > best) { best = len; bestI = i; }
  }
  return bestI;
}

function extractRing(feature: GeometryFeature): Ring | null {
  const geom = feature.geometry;
  if (!geom) return null;
  if (geom.type === "Polygon") {
    const coords = geom.coordinates as number[][][];
    if (!coords?.[0]?.length) return null;
    return coords[0].map(([x, y]) => [x, y] as Pt);
  }
  if (geom.type === "MultiPolygon") {
    const coords = geom.coordinates as number[][][][];
    if (!coords?.[0]?.[0]?.length) return null;
    return coords[0][0].map(([x, y]) => [x, y] as Pt);
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface SetbackBandsLayerProps {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  roadWidthM: number;
  buildingHeightM: number;
  visible: boolean;
}

interface BandInfo {
  key: string;
  quad: [Pt, Pt, Pt, Pt]; // world-space quad
  edgeType: "front" | "rear" | "side";
  labelM: number;
  midPt: Pt;
  edgeAngleDeg: number;
}

interface RoadLabelInfo {
  midPt: Pt;
  edgeAngleDeg: number;
}

function buildBands(
  ring: Ring,
  roadWidthM: number,
  buildingHeightM: number,
): { bands: BandInfo[]; roadLabel: RoadLabelInfo | null } {
  const n = ring.length - 1; // last point == first
  if (n < 3) return { bands: [], roadLabel: null };

  const centroid = computeCentroid(ring.slice(0, n));
  const roadIdx = detectRoadEdgeIndex(ring);
  const frontSetM = getFrontSetback(roadWidthM, buildingHeightM);
  const sideRearSetM = getSideRearSetback(buildingHeightM);

  // Detect rear edge: most anti-parallel to road edge normal
  const [rnx, rny] = edgeOutwardNormal(ring[roadIdx], ring[(roadIdx + 1) % n], centroid);
  let rearIdx = -1, minDot = Infinity;
  for (let i = 0; i < n; i++) {
    if (i === roadIdx) continue;
    const [nx, ny] = edgeOutwardNormal(ring[i], ring[(i + 1) % n], centroid);
    const dot = nx * rnx + ny * rny;
    if (dot < minDot) { minDot = dot; rearIdx = i; }
  }

  // Road label: positioned OUTWARD from the front edge by frontSetM + 6m
  const rp1 = ring[roadIdx], rp2 = ring[(roadIdx + 1) % n];
  const [rnxOut, rnyOut] = edgeOutwardNormal(rp1, rp2, centroid);
  const roadLabelOffsetDxf = (frontSetM + 6) * DXF_PER_METRE;
  const roadMidX = (rp1[0] + rp2[0]) / 2 + rnxOut * roadLabelOffsetDxf;
  const roadMidY = (rp1[1] + rp2[1]) / 2 + rnyOut * roadLabelOffsetDxf;
  const rdx = rp2[0] - rp1[0], rdy = rp2[1] - rp1[1];
  let roadAngleDeg = (Math.atan2(rdy, rdx) * 180) / Math.PI;
  if (roadAngleDeg > 90 || roadAngleDeg < -90) roadAngleDeg += 180;
  const roadLabel: RoadLabelInfo = {
    midPt: [roadMidX, roadMidY],
    edgeAngleDeg: roadAngleDeg,
  };

  const bands: BandInfo[] = [];

  for (let i = 0; i < n; i++) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % n];
    const edgeLenDxf = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
    const edgeLenM = edgeLenDxf / DXF_PER_METRE;

    // Skip very short edges (corner artifacts / chamfers < 2m)
    if (edgeLenM < 2) continue;

    const edgeType: "front" | "rear" | "side" =
      i === roadIdx ? "front" : i === rearIdx ? "rear" : "side";
    const marginM = edgeType === "front" ? frontSetM : sideRearSetM;
    const marginDxf = marginM * DXF_PER_METRE;

    const [nx, ny] = edgeOutwardNormal(p1, p2, centroid);
    // Inward direction (toward plot interior)
    const inx = -nx, iny = -ny;

    // Offset p1, p2 inward by marginDxf
    const p1i: Pt = [p1[0] + inx * marginDxf, p1[1] + iny * marginDxf];
    const p2i: Pt = [p2[0] + inx * marginDxf, p2[1] + iny * marginDxf];

    // Quad: outer edge p1→p2, then p2i←p1i (wound consistently)
    const quad: [Pt, Pt, Pt, Pt] = [p1, p2, p2i, p1i];

    // Midpoint of edge (label position) — halfway into the band
    const mx = (p1[0] + p2[0]) / 2 + inx * (marginDxf * 0.5);
    const my = (p1[1] + p2[1]) / 2 + iny * (marginDxf * 0.5);

    // Edge angle for label rotation
    const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
    let angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
    // Keep text upright
    if (angleDeg > 90 || angleDeg < -90) angleDeg += 180;

    bands.push({
      key: `band-${i}`,
      quad,
      edgeType,
      labelM: marginM,
      midPt: [mx, my],
      edgeAngleDeg: angleDeg,
    });
  }

  return { bands, roadLabel };
}

export function SetbackBandsLayer({
  features,
  viewTransform,
  roadWidthM,
  buildingHeightM,
  visible,
}: SetbackBandsLayerProps) {
  if (!visible || !features.length) return null;

  return (
    <>
      {features.map((feature) => {
        const ring = extractRing(feature);
        if (!ring) return null;

        const { bands, roadLabel } = buildBands(ring, roadWidthM, buildingHeightM);

        return (
          <g key={feature.id} style={{ pointerEvents: "none" }}>
            {/* Road label — outside the front setback band */}
            {roadLabel && (() => {
              const [rlx, rly] = projectPosition(roadLabel.midPt, viewTransform);
              const roadText = `${roadWidthM % 1 === 0 ? roadWidthM.toFixed(0) : roadWidthM.toFixed(1)} m Road`;
              const fontSize = 9;
              const pillW = roadText.length * fontSize * 0.60 + 10;
              const pillH = fontSize + 6;
              return (
                <g transform={`translate(${rlx}, ${rly}) rotate(${roadLabel.edgeAngleDeg})`} style={{ pointerEvents: "none" }}>
                  <rect
                    x={-pillW / 2} y={-pillH / 2}
                    width={pillW} height={pillH}
                    rx={3}
                    fill="rgba(219,234,254,0.92)"
                    stroke="#3b82f6"
                    strokeWidth={0.6}
                  />
                  <text
                    x={0} y={0}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ fontSize, fontWeight: 700, fill: "#1d4ed8", fontFamily: "system-ui, sans-serif" }}
                  >
                    {roadText}
                  </text>
                </g>
              );
            })()}
            {bands.map((band) => {
              const [s1, s2, s3, s4] = band.quad.map((pt) =>
                projectPosition(pt, viewTransform),
              );
              const pts = `${s1[0]},${s1[1]} ${s2[0]},${s2[1]} ${s3[0]},${s3[1]} ${s4[0]},${s4[1]}`;
              const [lx, ly] = projectPosition(band.midPt, viewTransform);

              // Band width in screen pixels (for label font sizing)
              const bandPxH = Math.hypot(s4[0] - s1[0], s4[1] - s1[1]);
              const showLabel = bandPxH > 14;

              const isFront = band.edgeType === "front";
              const fillColor = isFront
                ? "rgba(251,191,36,0.18)"  // amber tint
                : "rgba(148,163,184,0.18)"; // slate tint
              const strokeColor = isFront ? "#fbbf24" : "#94a3b8";
              const labelBg = isFront ? "#fef3c7" : "#f1f5f9";
              const labelTx = isFront ? "#92400e" : "#334155";
              const edgeLabel = band.edgeType === "front" ? "Front"
                : band.edgeType === "rear" ? "Rear" : "Side";
              const labelText = `${edgeLabel}  ${band.labelM.toFixed(1)}m`;

              // Estimate label pill width
              const fontSize = Math.max(8, Math.min(10, bandPxH * 0.55));
              const pillW = labelText.length * fontSize * 0.58 + 8;
              const pillH = fontSize + 4;

              return (
                <g key={band.key}>
                  {/* Filled margin band */}
                  <polygon
                    points={pts}
                    fill={fillColor}
                    stroke={strokeColor}
                    strokeWidth={0.75}
                    strokeDasharray="4 3"
                  />

                  {/* Label */}
                  {showLabel && (
                    <g transform={`translate(${lx}, ${ly}) rotate(${band.edgeAngleDeg})`}>
                      <rect
                        x={-pillW / 2}
                        y={-pillH / 2}
                        width={pillW}
                        height={pillH}
                        rx={pillH / 2}
                        fill={labelBg}
                        fillOpacity={0.92}
                        stroke={strokeColor}
                        strokeWidth={0.5}
                      />
                      <text
                        x={0}
                        y={0}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        style={{
                          fontSize,
                          fontWeight: 600,
                          fill: labelTx,
                          fontFamily: "system-ui, sans-serif",
                        }}
                      >
                        {labelText}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>
        );
      })}
    </>
  );
}
