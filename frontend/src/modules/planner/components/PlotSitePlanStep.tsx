"use client";

import { useMemo, useRef } from "react";
import { SvgCanvas } from "@/modules/planner/components/visualization/SvgCanvas";
import type { SvgCanvasHandle } from "@/modules/planner/components/visualization/SvgCanvas";
import { projectPosition } from "@/geometry/transform";
import type { ViewTransform } from "@/geometry/transform";
import type { GeometryModel } from "@/geometry/geojsonParser";
import { NorthArrow } from "@/modules/planner/components/NorthArrow";
import { ScaleBar } from "@/modules/planner/components/ScaleBar";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DXF_PER_METRE = 3.28084;
const FEET_TO_METRES = 0.3048;
const DIM_OFFSET_M = 5;        // metres — dim line offset from edge
const SIDE_STRIP_M = 7;        // context strip width on non-road edges
const MAX_ROAD_DISPLAY_M = 20; // cap road visual width so it doesn't dominate
const MIN_DIM_EDGE_M = 5;      // skip full dim annotation for edges shorter than this

// ---------------------------------------------------------------------------
// GDCR setback lookup (client-side, Table 6.24 + 6.26)
// ---------------------------------------------------------------------------
/** Front setback from road width — full GDCR Table 6.24 (8 tiers) */
function getFrontSetback(rwM: number): number {
  if (rwM <= 9.0)  return 2.5;
  if (rwM <= 15.0) return 3.0;
  if (rwM <= 18.0) return 4.5;
  if (rwM <= 30.0) return 6.0;
  if (rwM <= 45.0) return 7.5;
  return 9.0; // > 45 m road
}
/**
 * Side/rear setback derived from road width using max allowed building height
 * (GDCR height cap from road width → Table 6.26 margin).
 * Used during Step 1 before actual building height is known.
 */
function getSideRearSetback(rwM: number): number {
  // Height caps: ≤12m road→16.5m height; ≤18m→30m; ≤36m→45m; else→70m
  // Side/rear from height (Table 6.26): ≤16.5m→3.0; ≤25m→4.0; ≤45m→6.0; >45m→8.0
  if (rwM <= 12) return 3.0;
  if (rwM <= 18) return 4.0;
  return 6.0; // road > 18m → max height ≥ 45m → 6.0m (conservative)
}

// ---------------------------------------------------------------------------
// Light theme palette
// ---------------------------------------------------------------------------
const CLR = {
  bg:          "#eeeae2", // warm paper background
  roadFill:    "#dbd7ce", // road surface (asphalt grey)
  roadStroke:  "#c4bfb6", // road outer boundary
  laneLines:   "#c8c4bb", // lane markings inside road
  sideFill:    "#e5e1d9", // context strips (adjacent plots)
  sideStroke:  "#d0cbc2",
  plotFill:    "#fafaf8", // plot interior (bright white-cream)
  plotStroke:  "#1e2a3a", // plot boundary
  curbStroke:  "#1e2a3a", // bold curb line (road-facing edge)
  dimLine:     "#64748b", // dimension lines
  dimText:     "#1e2a3a", // dimension text
  dimTextBg:   "rgba(238,234,226,0.92)", // dim text background (matches bg)
  pillBg:      "rgba(30,42,58,0.82)",   // plot label pill
  pillText:    "#ffffff",
  pillSub:     "rgba(255,255,255,0.65)",
  roadLabelBg: "rgba(219,215,206,0.92)",
  roadLabelTx: "#3d3a34",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Pt = [number, number];
type Ring = Pt[];

interface GeoJsonPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface PlotSitePlanStepProps {
  plotGeometry: unknown;
  areaSqm: number;
  roadWidthM?: number;
  plotName?: string;
}

// ---------------------------------------------------------------------------
// Pure geometry helpers
// ---------------------------------------------------------------------------

function isGeoJsonPolygon(g: unknown): g is GeoJsonPolygon {
  return (
    typeof g === "object" &&
    g !== null &&
    (g as GeoJsonPolygon).type === "Polygon" &&
    Array.isArray((g as GeoJsonPolygon).coordinates) &&
    (g as GeoJsonPolygon).coordinates.length > 0
  );
}

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

/** Longest edge = road-facing edge (mirrors backend heuristic). */
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

function buildStripRing(p1: Pt, p2: Pt, normal: Pt, widthDxf: number): Ring {
  const [nx, ny] = normal;
  return [
    p1,
    p2,
    [p2[0] + nx * widthDxf, p2[1] + ny * widthDxf],
    [p1[0] + nx * widthDxf, p1[1] + ny * widthDxf],
    p1,
  ];
}

function projectRing(ring: Ring, vt: ViewTransform): Pt[] {
  return ring.map(p => projectPosition(p, vt) as Pt);
}

function ringToPoints(pts: Pt[]): string {
  return pts.map(([x, y]) => `${x},${y}`).join(" ");
}

// ---------------------------------------------------------------------------
// Dimension annotations
// ---------------------------------------------------------------------------
interface DimAnnotation {
  edgeP1s: Pt;
  edgeP2s: Pt;
  dimP1s:  Pt;
  dimP2s:  Pt;
  textPos: Pt;
  lengthM: number;
  textAngle: number;
  isShort: boolean; // true = edge < MIN_DIM_EDGE_M → compact inline label only
}

function computeDimAnnotations(
  ring: Ring,
  roadEdgeIndex: number,
  vt: ViewTransform,
): DimAnnotation[] {
  const n = ring.length - 1;
  const centroid = computeCentroid(ring);
  const dimOffsetDxf = DIM_OFFSET_M * DXF_PER_METRE;
  const annotations: DimAnnotation[] = [];

  for (let i = 0; i < n; i++) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % n];
    const dx = p2[0] - p1[0], dy = p2[1] - p1[1];
    const edgeLenDxf = Math.hypot(dx, dy);
    if (edgeLenDxf < 0.5) continue; // skip degenerate

    const edgeLenM = edgeLenDxf * FEET_TO_METRES;
    const isShort = edgeLenM < MIN_DIM_EDGE_M;

    // Always place dim lines OUTWARD from the plot edge.
    // Road edge → into road strip; other edges → into context strips.
    const [nx, ny] = edgeOutwardNormal(p1, p2, centroid);

    const mid: Pt = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2];

    let dimP1: Pt, dimP2: Pt, textDxf: Pt;

    if (isShort) {
      // Compact: label midpoint with no witness lines, just floating text near edge
      // Place text just outside the edge midpoint
      const smallOffset = 2.5 * DXF_PER_METRE;
      textDxf = [mid[0] + nx * smallOffset, mid[1] + ny * smallOffset];
      dimP1 = [p1[0] + nx * dimOffsetDxf, p1[1] + ny * dimOffsetDxf];
      dimP2 = [p2[0] + nx * dimOffsetDxf, p2[1] + ny * dimOffsetDxf];
    } else {
      dimP1 = [p1[0] + nx * dimOffsetDxf, p1[1] + ny * dimOffsetDxf];
      dimP2 = [p2[0] + nx * dimOffsetDxf, p2[1] + ny * dimOffsetDxf];
      textDxf = [mid[0] + nx * dimOffsetDxf, mid[1] + ny * dimOffsetDxf];
    }

    const edgeP1s = projectPosition(p1, vt) as Pt;
    const edgeP2s = projectPosition(p2, vt) as Pt;
    const dimP1s  = projectPosition(dimP1, vt) as Pt;
    const dimP2s  = projectPosition(dimP2, vt) as Pt;
    const textPos = projectPosition(textDxf, vt) as Pt;

    // Screen angle, clamped so text is never upside-down
    const sdx = edgeP2s[0] - edgeP1s[0], sdy = edgeP2s[1] - edgeP1s[1];
    let angleDeg = (Math.atan2(sdy, sdx) * 180) / Math.PI % 180;
    if (angleDeg > 90) angleDeg -= 180;
    if (angleDeg < -90) angleDeg += 180;

    // For short edges: also check if the label angle is nearly horizontal — prefer horizontal
    const finalAngle = isShort && Math.abs(angleDeg) < 20 ? 0 : angleDeg;

    annotations.push({
      edgeP1s, edgeP2s, dimP1s, dimP2s, textPos,
      lengthM: edgeLenM,
      textAngle: finalAngle,
      isShort,
    });
  }
  return annotations;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function PlotSitePlanStep({
  plotGeometry,
  areaSqm,
  roadWidthM = 12,
  plotName,
}: PlotSitePlanStepProps) {
  const canvasRef = useRef<SvgCanvasHandle>(null);

  const plotRing: Ring | null = useMemo(() => {
    if (!isGeoJsonPolygon(plotGeometry)) return null;
    const outer = plotGeometry.coordinates[0];
    if (!outer || outer.length < 3) return null;
    return outer.map(c => [c[0], c[1]] as Pt);
  }, [plotGeometry]);

  const roadEdgeIndex = useMemo(
    () => (plotRing ? detectRoadEdgeIndex(plotRing) : 0),
    [plotRing],
  );

  // Cap displayed road width so it doesn't dominate the canvas
  const roadDisplayWidthDxf = Math.min(roadWidthM, MAX_ROAD_DISPLAY_M) * DXF_PER_METRE;
  const sideStripDxf = SIDE_STRIP_M * DXF_PER_METRE;

  const { roadStripRing, sideStripRings, roadEdgeP1, roadEdgeP2, roadNormal } = useMemo(() => {
    if (!plotRing) return { roadStripRing: null, sideStripRings: [], roadEdgeP1: null, roadEdgeP2: null, roadNormal: null };
    const n = plotRing.length - 1;
    const centroid = computeCentroid(plotRing);
    const sideStrips: Ring[] = [];
    let roadStrip: Ring | null = null;
    let rp1: Pt | null = null, rp2: Pt | null = null, rNorm: Pt | null = null;

    for (let i = 0; i < n; i++) {
      const p1 = plotRing[i];
      const p2 = plotRing[(i + 1) % n];
      const normal = edgeOutwardNormal(p1, p2, centroid);
      if (i === roadEdgeIndex) {
        roadStrip = buildStripRing(p1, p2, normal, roadDisplayWidthDxf);
        rp1 = p1; rp2 = p2; rNorm = normal;
      } else {
        sideStrips.push(buildStripRing(p1, p2, normal, sideStripDxf));
      }
    }
    return { roadStripRing: roadStrip, sideStripRings: sideStrips, roadEdgeP1: rp1, roadEdgeP2: rp2, roadNormal: rNorm };
  }, [plotRing, roadEdgeIndex, roadDisplayWidthDxf, sideStripDxf]);

  // GDCR margin bands — inward strips inside the plot boundary
  const marginBands = useMemo(() => {
    if (!plotRing) return [];
    const n = plotRing.length - 1;
    const centroid = computeCentroid(plotRing);
    const frontM  = getFrontSetback(roadWidthM);
    const sideM   = getSideRearSetback(roadWidthM);

    // Rear edge = edge whose outward normal is most anti-parallel to the road edge normal
    const [rnx, rny] = edgeOutwardNormal(
      plotRing[roadEdgeIndex], plotRing[(roadEdgeIndex + 1) % n], centroid,
    );
    let rearIdx = -1, minDot = Infinity;
    for (let i = 0; i < n; i++) {
      if (i === roadEdgeIndex) continue;
      const p1 = plotRing[i], p2 = plotRing[(i + 1) % n];
      if (Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * FEET_TO_METRES < 2) continue;
      const [nx, ny] = edgeOutwardNormal(p1, p2, centroid);
      const dot = nx * rnx + ny * rny;
      if (dot < minDot) { minDot = dot; rearIdx = i; }
    }

    const bands: {
      quad: [Pt, Pt, Pt, Pt];
      edgeType: "front" | "rear" | "side";
      labelM: number;
      midDxf: Pt;
    }[] = [];

    for (let i = 0; i < n; i++) {
      const p1 = plotRing[i];
      const p2 = plotRing[(i + 1) % n];
      const edgeLenM = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * FEET_TO_METRES;
      if (edgeLenM < 2) continue; // skip tiny chamfer edges

      const edgeType: "front" | "rear" | "side" =
        i === roadEdgeIndex ? "front" : i === rearIdx ? "rear" : "side";
      const marginM   = edgeType === "front" ? frontM : sideM;
      const marginDxf = marginM * DXF_PER_METRE;

      // Inward normal (toward plot centroid)
      const [ox, oy] = edgeOutwardNormal(p1, p2, centroid);
      const inx = -ox, iny = -oy;

      const p1i: Pt = [p1[0] + inx * marginDxf, p1[1] + iny * marginDxf];
      const p2i: Pt = [p2[0] + inx * marginDxf, p2[1] + iny * marginDxf];

      // Label anchor — midpoint of edge, half-way into the band
      const mx = (p1[0] + p2[0]) / 2 + inx * marginDxf * 0.5;
      const my = (p1[1] + p2[1]) / 2 + iny * marginDxf * 0.5;

      bands.push({ quad: [p1, p2, p2i, p1i], edgeType, labelM: marginM, midDxf: [mx, my] });
    }
    return bands;
  }, [plotRing, roadEdgeIndex, roadWidthM]);

  // Geometry model for SvgCanvas bounds — use capped road width
  const geometryModel: GeometryModel = useMemo(() => {
    if (!plotRing) return { features: [] };
    const features: GeometryModel["features"] = [
      {
        id: "plot",
        layer: "plotBoundary",
        kind: "polygon",
        geometry: { type: "Polygon", coordinates: [plotRing.map(([x, y]) => [x, y, 0])] },
        properties: {},
      },
    ];
    if (roadStripRing) {
      features.push({
        id: "road-strip",
        layer: "roadNetwork",
        kind: "polygon",
        geometry: { type: "Polygon", coordinates: [roadStripRing.map(([x, y]) => [x, y, 0])] },
        properties: {},
      });
    }
    sideStripRings.forEach((r, i) => {
      features.push({
        id: `side-${i}`,
        layer: "roadNetwork",
        kind: "polygon",
        geometry: { type: "Polygon", coordinates: [r.map(([x, y]) => [x, y, 0])] },
        properties: {},
      });
    });
    return { features };
  }, [plotRing, roadStripRing, sideStripRings]);

  if (!plotRing) {
    return (
      <div className="flex h-full w-full items-center justify-center" style={{ background: CLR.bg }}>
        <p className="text-sm text-neutral-400">Loading plot geometry…</p>
      </div>
    );
  }

  return (
    <div className="relative flex h-full w-full" style={{ background: CLR.bg }}>
      <SvgCanvas geometryModel={geometryModel} canvasRef={canvasRef}>
        {({ viewTransform }) => {
          const W = viewTransform.width;
          const H = viewTransform.height;
          const centroid = computeCentroid(plotRing);

          const plotScreen  = projectRing(plotRing, viewTransform);
          const roadScreen  = roadStripRing ? projectRing(roadStripRing, viewTransform) : [];
          const sideScreens = sideStripRings.map(r => projectRing(r, viewTransform));

          const [centSx, centSy] = projectPosition(centroid, viewTransform);
          const dimAnnotations = computeDimAnnotations(plotRing, roadEdgeIndex, viewTransform);

          // Road-facing edge screen points (for bold curb line)
          const n = plotRing.length - 1;
          const curbP1s = projectPosition(plotRing[roadEdgeIndex], viewTransform) as Pt;
          const curbP2s = projectPosition(plotRing[(roadEdgeIndex + 1) % n], viewTransform) as Pt;

          // Road interior elements (centerline, lane lines, label, arrows)
          const roadElements = (() => {
            if (!roadEdgeP1 || !roadEdgeP2 || !roadNormal) return null;
            const [nx, ny] = roadNormal;
            const displayW = roadDisplayWidthDxf;

            // Centerline (at 50% of displayed width)
            const cl1: Pt = [roadEdgeP1[0] + nx * displayW * 0.5, roadEdgeP1[1] + ny * displayW * 0.5];
            const cl2: Pt = [roadEdgeP2[0] + nx * displayW * 0.5, roadEdgeP2[1] + ny * displayW * 0.5];

            // Lane lines (at 25% and 75% of displayed width — one per direction)
            const ll1a: Pt = [roadEdgeP1[0] + nx * displayW * 0.25, roadEdgeP1[1] + ny * displayW * 0.25];
            const ll1b: Pt = [roadEdgeP2[0] + nx * displayW * 0.25, roadEdgeP2[1] + ny * displayW * 0.25];
            const ll2a: Pt = [roadEdgeP1[0] + nx * displayW * 0.75, roadEdgeP1[1] + ny * displayW * 0.75];
            const ll2b: Pt = [roadEdgeP2[0] + nx * displayW * 0.75, roadEdgeP2[1] + ny * displayW * 0.75];

            // Road label — centered at 55% of displayed width
            const labelMidDxf: Pt = [
              (roadEdgeP1[0] + roadEdgeP2[0]) / 2 + nx * displayW * 0.55,
              (roadEdgeP1[1] + roadEdgeP2[1]) / 2 + ny * displayW * 0.55,
            ];

            // Screen-space edge angle for label rotation
            const [s1x, s1y] = projectPosition(roadEdgeP1, viewTransform);
            const [s2x, s2y] = projectPosition(roadEdgeP2, viewTransform);
            let roadAngle = (Math.atan2(s2y - s1y, s2x - s1x) * 180) / Math.PI % 180;
            if (roadAngle > 90) roadAngle -= 180;
            if (roadAngle < -90) roadAngle += 180;

            // Direction arrows along centerline
            const edgeLenDxf = Math.hypot(roadEdgeP2[0] - roadEdgeP1[0], roadEdgeP2[1] - roadEdgeP1[1]);
            const nArrows = Math.max(1, Math.floor(edgeLenDxf / (20 * DXF_PER_METRE)));
            const arrowAngle = (Math.atan2(s2y - s1y, s2x - s1x) * 180) / Math.PI;
            const arrows = Array.from({ length: nArrows }, (_, i) => {
              const t = (i + 1) / (nArrows + 1);
              const ax = cl1[0] + (cl2[0] - cl1[0]) * t;
              const ay = cl1[1] + (cl2[1] - cl1[1]) * t;
              return projectPosition([ax, ay], viewTransform) as Pt;
            });

            const roadLabelText = roadWidthM > MAX_ROAD_DISPLAY_M
              ? `${roadWidthM.toFixed(0)} m Road`
              : `${roadWidthM.toFixed(0)} m Road`;
            const roadLabelW = roadLabelText.length * 7.2 + 16;

            return {
              cl1s:      projectPosition(cl1, viewTransform) as Pt,
              cl2s:      projectPosition(cl2, viewTransform) as Pt,
              ll1as:     projectPosition(ll1a, viewTransform) as Pt,
              ll1bs:     projectPosition(ll1b, viewTransform) as Pt,
              ll2as:     projectPosition(ll2a, viewTransform) as Pt,
              ll2bs:     projectPosition(ll2b, viewTransform) as Pt,
              labelPos:  projectPosition(labelMidDxf, viewTransform) as Pt,
              roadLabelText,
              roadLabelW,
              roadAngle,
              arrowAngle,
              arrows,
            };
          })();

          // Pill auto-sizing
          const areaText   = `${Math.round(areaSqm).toLocaleString()} m²`;
          const pillWidth  = Math.max(
            72,
            areaText.length * 8.5 + 24,
            (plotName?.length ?? 0) * 7.5 + 24,
          );
          const pillHeight = plotName ? 36 : 22;
          const pillX      = centSx - pillWidth / 2;
          const pillY      = centSy - pillHeight / 2;

          return (
            <>
              {/* ── Background ── */}
              <rect x={0} y={0} width={W} height={H} fill={CLR.bg} />

              {/* ── Side context strips (adjacent plots) ── */}
              {sideScreens.map((pts, i) => (
                <polygon
                  key={i}
                  points={ringToPoints(pts)}
                  fill={CLR.sideFill}
                  stroke={CLR.sideStroke}
                  strokeWidth={0.75}
                />
              ))}

              {/* ── Road strip ── */}
              {roadScreen.length > 0 && (
                <polygon
                  points={ringToPoints(roadScreen)}
                  fill={CLR.roadFill}
                  stroke={CLR.roadStroke}
                  strokeWidth={1}
                />
              )}

              {/* ── Road lane lines (solid, thin, one per direction) ── */}
              {roadElements && (
                <>
                  <line
                    x1={roadElements.ll1as[0]} y1={roadElements.ll1as[1]}
                    x2={roadElements.ll1bs[0]} y2={roadElements.ll1bs[1]}
                    stroke={CLR.laneLines} strokeWidth={0.75}
                  />
                  <line
                    x1={roadElements.ll2as[0]} y1={roadElements.ll2as[1]}
                    x2={roadElements.ll2bs[0]} y2={roadElements.ll2bs[1]}
                    stroke={CLR.laneLines} strokeWidth={0.75}
                  />
                </>
              )}

              {/* ── Road centerline (dashed) ── */}
              {roadElements && (
                <line
                  x1={roadElements.cl1s[0]} y1={roadElements.cl1s[1]}
                  x2={roadElements.cl2s[0]} y2={roadElements.cl2s[1]}
                  stroke="#aaa69e"
                  strokeWidth={1}
                  strokeDasharray="12 7"
                />
              )}

              {/* ── Road direction arrows ── */}
              {roadElements?.arrows.map(([ax, ay], i) => (
                <g key={i} transform={`translate(${ax},${ay}) rotate(${roadElements.arrowAngle})`}>
                  <polyline
                    points="-7,5 0,0 7,5"
                    fill="none"
                    stroke="#9e9a93"
                    strokeWidth={1.2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </g>
              ))}

              {/* ── Road name label ── */}
              {roadElements && (
                <g transform={`rotate(${roadElements.roadAngle},${roadElements.labelPos[0]},${roadElements.labelPos[1]})`}>
                  <rect
                    x={roadElements.labelPos[0] - roadElements.roadLabelW / 2}
                    y={roadElements.labelPos[1] - 9}
                    width={roadElements.roadLabelW}
                    height={18}
                    rx={4}
                    fill={CLR.roadLabelBg}
                    stroke={CLR.roadStroke}
                    strokeWidth={0.5}
                  />
                  <text
                    x={roadElements.labelPos[0]}
                    y={roadElements.labelPos[1]}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={10}
                    fontWeight={500}
                    fill={CLR.roadLabelTx}
                    fontFamily="system-ui, sans-serif"
                  >
                    {roadElements.roadLabelText}
                  </text>
                </g>
              )}

              {/* ── Drop shadow filter for plot ── */}
              <defs>
                <filter id="ssp-shadow" x="-8%" y="-8%" width="116%" height="116%">
                  <feDropShadow dx="0" dy="3" stdDeviation="5" floodColor="rgba(0,0,0,0.10)" />
                </filter>
                <marker
                  id="ssp-dim-arr"
                  markerWidth={10} markerHeight={10}
                  refX={5} refY={5}
                  orient="auto-start-reverse"
                  markerUnits="userSpaceOnUse"
                >
                  <path
                    d="M2,3.5 L5,5 L2,6.5"
                    fill="none"
                    stroke={CLR.dimLine}
                    strokeWidth={1.2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </marker>
              </defs>

              {/* ── Plot fill with shadow ── */}
              <polygon
                points={ringToPoints(plotScreen)}
                fill={CLR.plotFill}
                stroke="none"
                filter="url(#ssp-shadow)"
              />

              {/* ── GDCR margin bands (inside plot) ── */}
              <g style={{ pointerEvents: "none" }}>
                {marginBands.map((band, i) => {
                  const [s1, s2, s3, s4] = band.quad.map(
                    pt => projectPosition(pt, viewTransform) as Pt,
                  );
                  const pts = `${s1[0]},${s1[1]} ${s2[0]},${s2[1]} ${s3[0]},${s3[1]} ${s4[0]},${s4[1]}`;
                  const [lx, ly] = projectPosition(band.midDxf, viewTransform) as Pt;

                  // Band pixel height (inward depth) — for label sizing
                  const bandPxH = Math.hypot(s4[0] - s1[0], s4[1] - s1[1]);
                  const showLabel = bandPxH > 16;

                  // Edge angle for label rotation (screen-space)
                  const [es1x, es1y] = projectPosition(band.quad[0], viewTransform) as Pt;
                  const [es2x, es2y] = projectPosition(band.quad[1], viewTransform) as Pt;
                  let angleDeg = (Math.atan2(es2y - es1y, es2x - es1x) * 180) / Math.PI % 180;
                  if (angleDeg > 90) angleDeg -= 180;
                  if (angleDeg < -90) angleDeg += 180;

                  const isFront = band.edgeType === "front";
                  const fillColor   = isFront ? "rgba(251,191,36,0.20)"  : "rgba(148,163,184,0.20)";
                  const strokeColor = isFront ? "#fbbf24" : "#94a3b8";
                  const labelBg    = isFront ? "#fef9ec" : "#f1f5f9";
                  const labelTx    = isFront ? "#92400e" : "#334155";
                  const edgeLabel  = band.edgeType === "front" ? "Front"
                    : band.edgeType === "rear" ? "Rear" : "Side";
                  const labelText  = `${edgeLabel}  ${band.labelM.toFixed(1)} m`;
                  const fontSize   = Math.max(7, Math.min(9.5, bandPxH * 0.48));
                  const pillW      = labelText.length * fontSize * 0.58 + 8;
                  const pillH      = fontSize + 5;

                  return (
                    <g key={i}>
                      <polygon
                        points={pts}
                        fill={fillColor}
                        stroke={strokeColor}
                        strokeWidth={0.75}
                        strokeDasharray="4 3"
                      />
                      {showLabel && (
                        <g transform={`translate(${lx},${ly}) rotate(${angleDeg})`}>
                          <rect
                            x={-pillW / 2} y={-pillH / 2}
                            width={pillW} height={pillH}
                            rx={pillH / 2}
                            fill={labelBg} fillOpacity={0.93}
                            stroke={strokeColor} strokeWidth={0.5}
                          />
                          <text
                            x={0} y={0}
                            textAnchor="middle" dominantBaseline="middle"
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

              {/* ── Plot boundary stroke ── */}
              <polygon
                points={ringToPoints(plotScreen)}
                fill="none"
                stroke={CLR.plotStroke}
                strokeWidth={1.75}
                strokeLinejoin="miter"
              />

              {/* ── Bold curb line on road-facing edge ── */}
              <line
                x1={curbP1s[0]} y1={curbP1s[1]}
                x2={curbP2s[0]} y2={curbP2s[1]}
                stroke={CLR.curbStroke}
                strokeWidth={3.5}
                strokeLinecap="square"
              />

              {/* ── Dimension annotations ── */}
              <g style={{ pointerEvents: "none" }}>
                {dimAnnotations.map((ann, i) => {
                  const labelStr = ann.lengthM.toFixed(1) + " m";
                  // Estimate rect width from text length
                  const rectW = Math.max(34, labelStr.length * 6.8 + 10);
                  const rectH = 13;

                  if (ann.isShort) {
                    // Compact: small pill directly on edge, no witness lines
                    return (
                      <g key={i}>
                        <rect
                          x={ann.textPos[0] - rectW / 2}
                          y={ann.textPos[1] - rectH / 2}
                          width={rectW}
                          height={rectH}
                          rx={3}
                          fill="rgba(255,255,255,0.88)"
                          stroke={CLR.dimLine}
                          strokeWidth={0.5}
                          transform={`rotate(${ann.textAngle},${ann.textPos[0]},${ann.textPos[1]})`}
                        />
                        <text
                          x={ann.textPos[0]}
                          y={ann.textPos[1]}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fontSize={7}
                          fill={CLR.dimText}
                          fontFamily="system-ui, sans-serif"
                          fontWeight={500}
                          transform={`rotate(${ann.textAngle},${ann.textPos[0]},${ann.textPos[1]})`}
                        >
                          {labelStr}
                        </text>
                      </g>
                    );
                  }

                  return (
                    <g key={i}>
                      {/* Witness lines — from edge endpoints to dim line */}
                      <line
                        x1={ann.edgeP1s[0]} y1={ann.edgeP1s[1]}
                        x2={ann.dimP1s[0]}  y2={ann.dimP1s[1]}
                        stroke={CLR.dimLine} strokeWidth={0.7} opacity={0.7}
                      />
                      <line
                        x1={ann.edgeP2s[0]} y1={ann.edgeP2s[1]}
                        x2={ann.dimP2s[0]}  y2={ann.dimP2s[1]}
                        stroke={CLR.dimLine} strokeWidth={0.7} opacity={0.7}
                      />
                      {/* Dimension line with arrowheads */}
                      <line
                        x1={ann.dimP1s[0]} y1={ann.dimP1s[1]}
                        x2={ann.dimP2s[0]} y2={ann.dimP2s[1]}
                        stroke={CLR.dimLine} strokeWidth={1}
                        markerStart="url(#ssp-dim-arr)"
                        markerEnd="url(#ssp-dim-arr)"
                      />
                      {/* Text background — properly centered & rotated */}
                      <rect
                        x={ann.textPos[0] - rectW / 2}
                        y={ann.textPos[1] - rectH / 2}
                        width={rectW}
                        height={rectH}
                        rx={2}
                        fill={CLR.dimTextBg}
                        transform={`rotate(${ann.textAngle},${ann.textPos[0]},${ann.textPos[1]})`}
                      />
                      {/* Length label */}
                      <text
                        x={ann.textPos[0]}
                        y={ann.textPos[1]}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        fontSize={8}
                        fill={CLR.dimText}
                        fontFamily="system-ui, sans-serif"
                        fontWeight={500}
                        transform={`rotate(${ann.textAngle},${ann.textPos[0]},${ann.textPos[1]})`}
                      >
                        {labelStr}
                      </text>
                    </g>
                  );
                })}
              </g>

              {/* ── Plot identity pill (auto-sized) ── */}
              <g style={{ pointerEvents: "none" }}>
                <rect
                  x={pillX} y={pillY}
                  width={pillWidth} height={pillHeight}
                  rx={5}
                  fill={CLR.pillBg}
                />
                {plotName && (
                  <>
                    {/* Subtle divider */}
                    <line
                      x1={pillX + 10} y1={pillY + pillHeight / 2}
                      x2={pillX + pillWidth - 10} y2={pillY + pillHeight / 2}
                      stroke="rgba(255,255,255,0.15)" strokeWidth={0.75}
                    />
                    <text
                      x={centSx} y={pillY + pillHeight * 0.3}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={8} fill={CLR.pillSub}
                      fontFamily="system-ui, sans-serif"
                      fontWeight={400} letterSpacing={0.6}
                    >
                      {plotName.toUpperCase()}
                    </text>
                    <text
                      x={centSx} y={pillY + pillHeight * 0.72}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={11} fill={CLR.pillText}
                      fontFamily="system-ui, sans-serif" fontWeight={700}
                    >
                      {areaText}
                    </text>
                  </>
                )}
                {!plotName && (
                  <text
                    x={centSx} y={centSy}
                    textAnchor="middle" dominantBaseline="middle"
                    fontSize={11} fill={CLR.pillText}
                    fontFamily="system-ui, sans-serif" fontWeight={700}
                  >
                    {areaText}
                  </text>
                )}
              </g>

              {/* ── Fixed UI elements ── */}
              <NorthArrow />
              <ScaleBar viewTransform={viewTransform} />
            </>
          );
        }}
      </SvgCanvas>
    </div>
  );
}
