"use client";

import { useMemo, useState, useCallback } from "react";
import type { Position } from "@/geometry/geometryNormalizer";
import {
  parseGeoJsonToModel,
  type GeometryFeature,
} from "@/geometry/geojsonParser";
import type { GeoJsonInput } from "@/geometry/geometryNormalizer";
import { computeBoundsFromPositions } from "@/geometry/bounds";
import { createViewTransform, projectPosition, type ViewTransform } from "@/geometry/transform";
import { geometryFeatureToPath } from "@/geometry/pathBuilder";
import { useTpMapBundle } from "@/modules/plots/hooks/useTpMapBundle";
import type { TpMapBundle } from "@/services/tpMapService";
import { formatArea } from "@/lib/units";
import {
  getDesignationColor,
  computeScreenArea,
  getAdaptiveFontSize,
  computeRoadLabelPlacement,
  extractOuterRing,
  type RoadLabelPlacement,
} from "./tpMapPickerUtils";

// ── Types ───────────────────────────────────────────────────────────

type TpMapPickerProps = {
  tpScheme: string;
  city?: string;
  onPlotSelect?: (plotId: string) => void;
  selectedPlotId?: string;
  className?: string;
};

type PlotFeatureData = {
  plotId: string;
  name: string;
  fpLabel: string;
  areaSqm: number;
  roadWidthM: number | null;
  designation: string;
};

type FpLabelEntry = {
  plotId: string;
  fpLabel: string;
  svgX: number;
  svgY: number;
  fontSize: number;
  fontWeight: string;
};

type RoadLabelEntry = {
  key: string;
  text: string;
  placement: RoadLabelPlacement;
};

// ── Constants ───────────────────────────────────────────────────────

const SVG_WIDTH = 960;
const SVG_HEIGHT = 700;
const PADDING = 28;

// ── Tooltip ─────────────────────────────────────────────────────────

function PlotTooltip({
  plot,
  x,
  y,
}: {
  plot: PlotFeatureData;
  x: number;
  y: number;
}) {
  return (
    <div
      className="fixed z-50 min-w-[200px] max-w-[280px] rounded-lg border border-neutral-200 bg-white px-3 py-2.5 text-left shadow-lg pointer-events-none"
      style={{ left: x + 14, top: y + 10 }}
    >
      <div className="border-b border-neutral-100 pb-1.5 font-semibold text-sm text-neutral-900">
        {plot.name}
      </div>
      {plot.designation && (
        <div className="mt-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
          {plot.designation}
        </div>
      )}
      <dl className="mt-1.5 space-y-0.5 text-xs text-neutral-600">
        <div className="flex justify-between gap-4">
          <dt>Plot ID</dt>
          <dd className="font-mono text-neutral-800">{plot.plotId}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Area</dt>
          <dd>
            {formatArea(plot.areaSqm, "sqft")}
            <span className="ml-1 text-neutral-500">
              ({formatArea(plot.areaSqm, "sqm")})
            </span>
          </dd>
        </div>
        {plot.roadWidthM != null && (
          <div className="flex justify-between gap-4">
            <dt>Road</dt>
            <dd>{plot.roadWidthM} m</dd>
          </div>
        )}
      </dl>
      <div className="mt-2 text-[10px] text-center text-orange-500 font-semibold">
        Click to select
      </div>
    </div>
  );
}

// ── Data processing ─────────────────────────────────────────────────

type ProcessedMapData = {
  roadFeatures: GeometryFeature[];
  plotFeatures: GeometryFeature[];
  plotDataMap: Map<string, PlotFeatureData>;
  featureToPlotId: Map<string, string>;
  fpLabels: FpLabelEntry[];
  roadLabels: RoadLabelEntry[];
  transform: ViewTransform;
};

function processBundle(bundle: TpMapBundle): ProcessedMapData | null {
  const allPositions: Position[] = [];

  // ── Road polygons ──
  const roadFeatures: GeometryFeature[] = [];
  for (const feature of bundle.layers.roads.features) {
    if (!feature.geometry) continue;
    const model = parseGeoJsonToModel(feature.geometry as GeoJsonInput, "plotBoundary");
    for (const f of model.features) {
      const fid = `road-${feature.id ?? Math.random().toString(36).slice(2)}`;
      roadFeatures.push({ ...f, id: fid });
      const ring = extractOuterRing(f.geometry);
      if (ring) for (const p of ring) allPositions.push([Number(p[0]), Number(p[1])]);
    }
  }

  // ── Plot polygons ──
  const plotFeatures: GeometryFeature[] = [];
  const plotDataMap = new Map<string, PlotFeatureData>();
  const featureToPlotId = new Map<string, string>();
  const plotGeometryMap = new Map<string, unknown>();

  for (const feature of bundle.layers.fpPolygons.features) {
    if (!feature.geometry) continue;
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const plotId = String(props.plotId ?? "");
    if (!plotId) continue;

    const model = parseGeoJsonToModel(feature.geometry as GeoJsonInput, "plotBoundary");
    for (const f of model.features) {
      const fid = `plot-${plotId}-${f.id}`;
      plotFeatures.push({ ...f, id: fid });
      featureToPlotId.set(fid, plotId);
      const ring = extractOuterRing(f.geometry);
      if (ring) for (const p of ring) allPositions.push([Number(p[0]), Number(p[1])]);
    }

    const roadWidthRaw = props.roadWidthM;
    plotDataMap.set(plotId, {
      plotId,
      name: String(props.name ?? `FP ${plotId}`),
      fpLabel: String(props.fpLabel ?? ""),
      areaSqm: Number(props.areaSqm ?? 0),
      roadWidthM:
        typeof roadWidthRaw === "number" && Number.isFinite(roadWidthRaw)
          ? roadWidthRaw
          : null,
      designation: String(props.designation ?? ""),
    });
    plotGeometryMap.set(plotId, feature.geometry);
  }

  if (allPositions.length === 0) return null;

  // ── Compute transform ──
  const bounds = computeBoundsFromPositions(allPositions);
  if (!bounds) return null;
  const transform = createViewTransform(bounds, SVG_WIDTH, SVG_HEIGHT, PADDING, { flipY: true });

  // ── FP label points ──
  const fpLabels: FpLabelEntry[] = [];
  for (const feature of bundle.layers.fpLabelPoints.features) {
    if (!feature.geometry || (feature.geometry as { type?: string }).type !== "Point") continue;
    const coords = (feature.geometry as { coordinates?: unknown }).coordinates;
    if (!Array.isArray(coords) || coords.length < 2) continue;

    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const plotId = String(props.plotId ?? "");
    const fpLabel = String(props.fpLabel ?? "");
    if (!fpLabel) continue;

    const [svgX, svgY] = projectPosition([Number(coords[0]), Number(coords[1])], transform);

    let screenArea = 1000;
    const rawGeom = plotGeometryMap.get(plotId);
    if (rawGeom) {
      const ring = extractOuterRing(rawGeom);
      if (ring) screenArea = computeScreenArea(ring, transform);
    }

    const { fontSize, fontWeight } = getAdaptiveFontSize(screenArea);

    fpLabels.push({ plotId, fpLabel, svgX, svgY, fontSize, fontWeight });
  }

  // ── Road centerline labels ──
  const roadLabels: RoadLabelEntry[] = [];
  for (const feature of bundle.layers.roadCenterlines.features) {
    if (!feature.geometry) continue;
    const geom = feature.geometry as { type?: string; coordinates?: unknown };
    if (geom.type !== "LineString" || !Array.isArray(geom.coordinates)) continue;
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const widthM = props.widthM;
    if (typeof widthM !== "number" || !Number.isFinite(widthM)) continue;

    const placement = computeRoadLabelPlacement(
      geom.coordinates as Position[],
      transform,
    );
    if (!placement) continue;

    roadLabels.push({
      key: `road-label-${feature.id ?? Math.random().toString(36).slice(2)}`,
      text: `${Math.round(widthM)}m`,
      placement,
    });
  }

  return {
    roadFeatures,
    plotFeatures,
    plotDataMap,
    featureToPlotId,
    fpLabels,
    roadLabels,
    transform,
  };
}

// ── Main Component ──────────────────────────────────────────────────

export function TpMapPicker({
  tpScheme,
  city,
  onPlotSelect,
  selectedPlotId,
  className = "",
}: TpMapPickerProps) {
  const { data: bundle, isLoading, isError, refetch } = useTpMapBundle(tpScheme, city);
  const [hoveredPlotId, setHoveredPlotId] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const mapData = useMemo(() => {
    if (!bundle) return null;
    return processBundle(bundle);
  }, [bundle]);

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent<SVGElement>, plotId: string) => {
      setHoveredPlotId(plotId);
      setTooltipPos({ x: e.clientX, y: e.clientY });
    },
    [],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (hoveredPlotId) setTooltipPos({ x: e.clientX, y: e.clientY });
    },
    [hoveredPlotId],
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredPlotId(null);
  }, []);

  const handlePlotClick = useCallback(
    (plotId: string) => {
      onPlotSelect?.(plotId);
    },
    [onPlotSelect],
  );

  if (isLoading) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-neutral-200 bg-neutral-50 ${className}`}
        style={{ aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
      >
        <div className="flex flex-col items-center gap-3">
          <span className="h-8 w-8 animate-spin rounded-full border-4 border-neutral-200 border-t-orange-500" />
          <span className="text-sm text-neutral-500">Loading TP map...</span>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-red-200 bg-red-50 ${className}`}
        style={{ aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
      >
        <span className="text-sm text-red-600">Failed to load map.</span>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-md bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!mapData) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-dashed border-neutral-200 bg-neutral-50 text-sm text-neutral-500 ${className}`}
        style={{ aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
      >
        No geometry to show
      </div>
    );
  }

  const { transform, roadFeatures, plotFeatures, plotDataMap, featureToPlotId, fpLabels, roadLabels } = mapData;
  const hoveredPlot = hoveredPlotId ? plotDataMap.get(hoveredPlotId) ?? null : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className={`overflow-hidden rounded-lg border border-neutral-200 ${className}`}
        style={{ width: "100%", height: "auto", aspectRatio: `${SVG_WIDTH} / ${SVG_HEIGHT}` }}
        aria-label="TP scheme map — click a plot to select"
        onMouseLeave={handleMouseLeave}
        onMouseMove={handleMouseMove}
      >
        {/* Layer 1: Background */}
        <rect x="0" y="0" width={SVG_WIDTH} height={SVG_HEIGHT} fill="#f8fafc" />

        {/* Layer 2: Road polygons */}
        <g>
          {roadFeatures.map((f) => (
            <path
              key={f.id}
              d={geometryFeatureToPath(f, transform)}
              fill="rgba(251,191,114,0.6)"
              stroke="#b45309"
              strokeWidth={0.5}
            />
          ))}
        </g>

        {/* Layer 3: Plot polygons */}
        <g>
          {plotFeatures.map((f) => {
            const plotId = featureToPlotId.get(f.id);
            const plotData = plotId ? plotDataMap.get(plotId) : undefined;
            const isHovered = plotId === hoveredPlotId;
            const isSelected = plotId === selectedPlotId;
            const colors = getDesignationColor(plotData?.designation);

            let fill = colors.fill;
            let stroke = colors.stroke;
            let strokeWidth = 1;
            let strokeDasharray: string | undefined;

            if (isSelected) {
              stroke = "#059669";
              strokeWidth = 2.5;
              strokeDasharray = "6 3";
            }
            if (isHovered) {
              fill = "rgba(59,130,246,0.2)";
              stroke = "#2563eb";
              strokeWidth = 2.5;
              strokeDasharray = undefined;
            }

            return (
              <path
                key={f.id}
                d={geometryFeatureToPath(f, transform)}
                fill={fill}
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeDasharray={strokeDasharray}
                style={{ cursor: "pointer" }}
                onMouseEnter={(e) => plotId && handleMouseEnter(e, plotId)}
                onClick={() => plotId && handlePlotClick(plotId)}
              />
            );
          })}
        </g>

        {/* Layer 4: Road centerline labels */}
        <g aria-hidden="true">
          {roadLabels.map((rl) => (
            <text
              key={rl.key}
              x={rl.placement.x}
              y={rl.placement.y}
              textAnchor="middle"
              dominantBaseline="middle"
              transform={`rotate(${rl.placement.angle}, ${rl.placement.x}, ${rl.placement.y})`}
              fill="#ffffff"
              stroke="#1e293b"
              strokeWidth={3}
              paintOrder="stroke"
              style={{ fontSize: "7px", fontWeight: 700, fontFamily: "sans-serif" }}
              className="select-none"
            >
              {rl.text}
            </text>
          ))}
        </g>

        {/* Layer 5: FP number labels */}
        <g aria-hidden="true">
          {fpLabels.map((lbl) => (
            <text
              key={`fp-${lbl.plotId}`}
              x={lbl.svgX}
              y={lbl.svgY}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="#1e293b"
              stroke="#ffffff"
              strokeWidth={2.5}
              paintOrder="stroke"
              style={{
                fontSize: `${lbl.fontSize}px`,
                fontWeight: lbl.fontWeight,
                fontFamily: "sans-serif",
              }}
              className="select-none"
            >
              {lbl.fpLabel}
            </text>
          ))}
        </g>
      </svg>

      {hoveredPlot && (
        <PlotTooltip plot={hoveredPlot} x={tooltipPos.x} y={tooltipPos.y} />
      )}
    </div>
  );
}
