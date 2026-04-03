"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import type { Position } from "@/geometry/geometryNormalizer";
import { getFeatureCentroid } from "@/geometry/centroid";
import { projectPosition } from "@/geometry/transform";

// ── Helpers ─────────────────────────────────────────────────────────────────────

/** Shoelace area in screen pixels² for a polygon feature. */
function screenArea(feature: GeometryFeature, vt: ViewTransform): number {
  const g = feature.geometry;
  if (g.type !== "Polygon") return 0;
  const outer = (g.coordinates as Position[][])[0] ?? [];
  const pts = outer.map((pt) => projectPosition(pt as Position, vt));
  let area = 0;
  for (let i = 0; i < pts.length; i++) {
    const j = (i + 1) % pts.length;
    area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1];
  }
  return Math.abs(area) / 2;
}

// ── Label pill component ────────────────────────────────────────────────────────

type PillProps = {
  x: number;
  y: number;
  lines: string[];
  color: string;
  bg: string;
  minPxArea?: number; // suppress if zone is rendered too small
  zonePxArea?: number;
};

function Pill({ x, y, lines, color, bg, minPxArea = 600, zonePxArea }: PillProps) {
  if (zonePxArea !== undefined && zonePxArea < minPxArea) return null;
  const lineH = 11;
  const padX = 7;
  const padY = 5;
  const widths = lines.map((l) => l.length * 5.6 + padX * 2);
  const w = Math.max(...widths, 40);
  const h = lines.length * lineH + padY * 2;
  return (
    <g style={{ pointerEvents: "none" }}>
      <rect
        x={x - w / 2}
        y={y - h / 2}
        width={w}
        height={h}
        rx={3}
        fill={bg}
        stroke={color}
        strokeWidth={0.75}
        opacity={0.93}
      />
      {lines.map((line, i) => (
        <text
          key={i}
          x={x}
          y={y - ((lines.length - 1) * lineH) / 2 + i * lineH}
          textAnchor="middle"
          dominantBaseline="middle"
          style={{
            fontSize: i === 0 ? 8 : 7,
            fill: color,
            fontWeight: i === 0 ? 700 : 400,
            fontFamily: "system-ui, sans-serif",
          }}
        >
          {line}
        </text>
      ))}
    </g>
  );
}

// ── Scale bar ──────────────────────────────────────────────────────────────────

type ScaleBarProps = {
  canvasWidth: number;
  canvasHeight: number;
  metersPerPx: number | null;
};

function ScaleBar({ canvasWidth, canvasHeight, metersPerPx }: ScaleBarProps) {
  if (!metersPerPx || metersPerPx <= 0) return null;
  // Target a bar ~80 px wide; round to a nice number of meters.
  const targetM = metersPerPx * 80;
  const niceM = (() => {
    const steps = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500];
    return steps.reduce((best, s) =>
      Math.abs(s - targetM) < Math.abs(best - targetM) ? s : best,
    );
  })();
  const barPx = niceM / metersPerPx;
  const bx = canvasWidth - barPx - 20;
  const by = canvasHeight - 28;
  return (
    <g style={{ pointerEvents: "none" }}>
      {/* bar */}
      <line x1={bx} y1={by} x2={bx + barPx} y2={by} stroke="#374151" strokeWidth={1.5} />
      {/* tick left */}
      <line x1={bx} y1={by - 4} x2={bx} y2={by + 4} stroke="#374151" strokeWidth={1.5} />
      {/* tick right */}
      <line
        x1={bx + barPx}
        y1={by - 4}
        x2={bx + barPx}
        y2={by + 4}
        stroke="#374151"
        strokeWidth={1.5}
      />
      <text
        x={bx + barPx / 2}
        y={by - 7}
        textAnchor="middle"
        style={{ fontSize: 8, fill: "#374151", fontFamily: "system-ui, sans-serif" }}
      >
        {niceM} m
      </text>
    </g>
  );
}

// ── North arrow ────────────────────────────────────────────────────────────────

function NorthArrow({ x, y }: { x: number; y: number }) {
  return (
    <g style={{ pointerEvents: "none" }} transform={`translate(${x},${y})`}>
      {/* filled north half */}
      <polygon points="0,-12 -5,0 0,-2" fill="#374151" />
      {/* outline south half */}
      <polygon points="0,-12 5,0 0,-2" fill="none" stroke="#374151" strokeWidth={1} />
      <polygon points="0,12 -5,0 0,2" fill="none" stroke="#374151" strokeWidth={1} />
      <polygon points="0,12 5,0 0,2" fill="#374151" />
      <text
        x={0}
        y={-16}
        textAnchor="middle"
        style={{ fontSize: 8, fill: "#374151", fontWeight: 700, fontFamily: "system-ui, sans-serif" }}
      >
        N
      </text>
    </g>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

type AnnotationLayerProps = {
  visible: boolean;
  viewTransform: ViewTransform;
  plotFeatures: GeometryFeature[];
  envelopeFeatures: GeometryFeature[];
  copFeatures: GeometryFeature[];
  towerZoneFeatures: GeometryFeature[];
  towerFeatures: GeometryFeature[];
  metrics: Record<string, unknown>;
};

export function AnnotationLayer({
  visible,
  viewTransform,
  plotFeatures,
  envelopeFeatures,
  copFeatures,
  towerZoneFeatures,
  towerFeatures,
  metrics,
}: AnnotationLayerProps) {
  if (!visible) return null;

  const vt = viewTransform;

  // ── Compute meters-per-pixel from known tower footprint area ──────────────────
  // totalFootprintSqm is the total tower footprint from the backend; dividing by
  // the corresponding screen-pixel area gives the scale factor.
  const totalFootprintSqm = Number(metrics.totalFootprintSqm) || 0;
  const towerScreenAreaPx = towerFeatures.reduce(
    (s, f) => s + screenArea(f, vt),
    0,
  );
  const metersPerPx =
    totalFootprintSqm > 0 && towerScreenAreaPx > 0
      ? Math.sqrt(totalFootprintSqm / towerScreenAreaPx)
      : null;

  // ── Helper: centroid → screen pos ─────────────────────────────────────────────
  const centroid = (f: GeometryFeature): [number, number] | null => {
    const wp = getFeatureCentroid(f);
    if (!wp) return null;
    const [sx, sy] = projectPosition(wp, vt);
    // Discard if out of viewport
    if (sx < 0 || sy < 0 || sx > vt.width || sy > vt.height) return null;
    return [sx, sy];
  };

  const SQFT_TO_SQM = 0.09290304;
  const plotAreaSqm = Number(metrics.plotAreaSqm) || 0;
  const envelopeAreaSqm =
    Number(metrics.envelopeAreaSqft) * SQFT_TO_SQM || 0;
  const copAreaSqm = Number(metrics.copAreaSqft) * SQFT_TO_SQM || 0;

  return (
    <>
      {/* ── Plot boundary label ─────────────────────────────────────────────── */}
      {plotFeatures.map((f) => {
        const pos = centroid(f);
        if (!pos) return null;
        const pxArea = screenArea(f, vt);
        const lines = [
          "Plot boundary",
          plotAreaSqm > 0 ? `${Math.round(plotAreaSqm).toLocaleString()} m²` : "",
        ].filter(Boolean);
        return (
          <Pill
            key={`plot-${f.id}`}
            x={pos[0]}
            y={pos[1]}
            lines={lines}
            color="#6b7280"
            bg="rgba(249,250,251,0.93)"
            minPxArea={4000}
            zonePxArea={pxArea}
          />
        );
      })}

      {/* ── Buildable envelope label ────────────────────────────────────────── */}
      {envelopeFeatures.map((f) => {
        const pos = centroid(f);
        if (!pos) return null;
        const pxArea = screenArea(f, vt);
        const lines = [
          "Buildable envelope",
          envelopeAreaSqm > 0
            ? `${Math.round(envelopeAreaSqm).toLocaleString()} m²`
            : "",
        ].filter(Boolean);
        return (
          <Pill
            key={`env-${f.id}`}
            x={pos[0]}
            y={pos[1]}
            lines={lines}
            color="#b45309"
            bg="rgba(255,251,235,0.93)"
            minPxArea={2000}
            zonePxArea={pxArea}
          />
        );
      })}

      {/* ── COP label ──────────────────────────────────────────────────────── */}
      {copFeatures.map((f) => {
        const pos = centroid(f);
        if (!pos) return null;
        const pxArea = screenArea(f, vt);
        const copReqSqm = Number(metrics.copRequiredSqm) || 0;
        const widthM = f.properties?.width_m as number | undefined;
        const depthM = f.properties?.depth_m as number | undefined;
        const featureAreaSqm = f.properties?.area_sqm as number | undefined;
        const displayArea = featureAreaSqm ?? (copAreaSqm > 0 ? copAreaSqm : null);
        const lines = [
          "COP",
          widthM && depthM ? `${widthM.toFixed(0)} m × ${depthM.toFixed(0)} m` : "",
          displayArea ? `Provided: ${Math.round(displayArea)} m²` : "",
          copReqSqm > 0 ? `Required: ${Math.round(copReqSqm)} m²` : "",
        ].filter(Boolean);
        return (
          <Pill
            key={`cop-${f.id}`}
            x={pos[0]}
            y={pos[1]}
            lines={lines}
            color="#047857"
            bg="rgba(240,253,244,0.93)"
            minPxArea={800}
            zonePxArea={pxArea}
          />
        );
      })}

      {/* ── Tower zone labels ───────────────────────────────────────────────── */}
      {towerZoneFeatures.map((f, i) => {
        const pos = centroid(f);
        if (!pos) return null;
        const pxArea = screenArea(f, vt);
        return (
          <Pill
            key={`tz-${f.id}-${i}`}
            x={pos[0]}
            y={pos[1]}
            lines={[`Zone ${i + 1}`]}
            color="#92400e"
            bg="rgba(255,247,237,0.88)"
            minPxArea={600}
            zonePxArea={pxArea}
          />
        );
      })}

      {/* ── Tower labels (detailed) ─────────────────────────────────────────── */}
      {towerFeatures.map((f, i) => {
        const pos = centroid(f);
        if (!pos) return null;
        const towerId =
          (f.properties?.towerId as string) ?? `T${i + 1}`;
        const floors = f.properties?.floors as number | undefined;
        const heightM = f.properties?.height as number | undefined;
        const pxArea = screenArea(f, vt);

        // Per-tower footprint area: distribute totalFootprintSqm by screen-area ratio
        let perTowerSqm: number | null = null;
        if (totalFootprintSqm > 0 && towerScreenAreaPx > 0) {
          const towerPxArea = screenArea(f, vt);
          perTowerSqm = Math.round(
            (towerPxArea / towerScreenAreaPx) * totalFootprintSqm,
          );
        }

        const lines = [
          towerId,
          floors != null && heightM != null
            ? `${floors}F · ${heightM.toFixed(0)} m`
            : floors != null
              ? `${floors} floors`
              : "",
          perTowerSqm != null ? `${perTowerSqm.toLocaleString()} m²` : "",
        ].filter(Boolean);

        return (
          <Pill
            key={`tower-ann-${f.id}`}
            x={pos[0]}
            y={pos[1]}
            lines={lines}
            color="#ffffff"
            bg="rgba(29,78,216,0.82)"
            minPxArea={300}
            zonePxArea={pxArea}
          />
        );
      })}

      {/* ── Scale bar ──────────────────────────────────────────────────────── */}
      <ScaleBar
        canvasWidth={vt.width}
        canvasHeight={vt.height}
        metersPerPx={metersPerPx}
      />

      {/* ── North arrow ─────────────────────────────────────────────────────── */}
      <NorthArrow x={vt.width - 24} y={vt.height - 72} />
    </>
  );
}
