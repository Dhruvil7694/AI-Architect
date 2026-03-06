"use client";

import { useMemo, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import type { GeoJsonInput } from "@/geometry/geometryNormalizer";
import type { Position } from "@/geometry/geometryNormalizer";
import {
  parseGeoJsonToModel,
  type GeometryModel,
  type GeometryFeature,
} from "@/geometry/geojsonParser";
import { computeBoundsForModel } from "@/geometry/bounds";
import { createViewTransform, projectPosition } from "@/geometry/transform";
import { geometryFeatureToPath } from "@/geometry/pathBuilder";
import { usePlannerStore } from "@/state/plannerStore";
import { getSiteMetrics, type SiteMetrics } from "@/services/plannerService";

export type PlotWithGeometry = {
  id: string;
  name: string;
  areaSqm: number;
  areaSqft?: number;
  roadWidthM?: number;
  /** Land-use tag (e.g. SALE FOR RESIDENTIAL, S.E.W.S.H., PUBLIC PURPOSE) */
  designation?: string | null;
  geometry?: unknown;
};

type WholeTpMapProps = {
  plots: PlotWithGeometry[];
  width?: number;
  height?: number;
  className?: string;
};

/** Compute polygon center in world coords (for label placement) */
function getFeatureCenter(feature: GeometryFeature): Position | null {
  const { geometry } = feature;
  let coords: Position[] = [];

  if (geometry.type === "Polygon" && Array.isArray(geometry.coordinates)?.[0]) {
    coords = geometry.coordinates[0] as Position[];
  } else if (
    geometry.type === "MultiPolygon" &&
    Array.isArray(geometry.coordinates)?.[0]?.[0]
  ) {
    coords = geometry.coordinates[0][0] as Position[];
  }
  if (coords.length === 0) return null;

  let sumX = 0;
  let sumY = 0;
  for (const [x, y] of coords) {
    sumX += Number(x);
    sumY += Number(y);
  }
  return [sumX / coords.length, sumY / coords.length];
}

function PlotTooltip({
  plot,
  x,
  y,
}: {
  plot: PlotWithGeometry;
  x: number;
  y: number;
}) {
  const plotId = plot.id;
  const { data } = useQuery<SiteMetrics | null>({
    queryKey: ["site-metrics", plotId],
    queryFn: () => getSiteMetrics(plotId),
  });

  const maxFsi = data?.maxFSI;
  const copPct =
    data && data.plotAreaSqm
      ? (data.copAreaSqm / data.plotAreaSqm) * 100
      : undefined;

  return (
    <div
      className="fixed z-50 min-w-[220px] max-w-[300px] rounded-lg border border-neutral-200 bg-white px-3 py-2.5 text-left shadow-lg"
      style={{ left: x + 12, top: y + 8 }}
    >
      <div className="border-b border-neutral-100 pb-1.5 font-medium text-neutral-900">
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
          <dd className="font-mono text-neutral-800">{plot.id}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Area</dt>
          <dd>
            {Math.round(plot.areaSqm)} m²
            {plot.areaSqft != null && (
              <span className="ml-1 text-neutral-500">
                ({Math.round(plot.areaSqft)} sq.ft)
              </span>
            )}
          </dd>
        </div>
        {plot.roadWidthM != null && (
          <div className="flex justify-between gap-4">
            <dt>Road</dt>
            <dd>{plot.roadWidthM} m (MT)</dd>
          </div>
        )}
      </dl>
      <div className="mt-2 border-t border-neutral-100 pt-2 text-[10px] text-neutral-500">
        <p className="font-medium text-neutral-600">Calculated (run planner)</p>
        <div className="mt-0.5 grid grid-cols-2 gap-x-4 gap-y-0.5">
          <span>Buildable tower</span>
          <span>—</span>
          <span>COP</span>
          <span>
            {copPct !== undefined ? `${copPct.toFixed(1)}%` : "—"}
          </span>
          <span>Margins</span>
          <span>—</span>
          <span>Max FSI</span>
          <span>{maxFsi !== undefined ? maxFsi.toFixed(2) : "—"}</span>
          <span>Height</span>
          <span>—</span>
        </div>
      </div>
      <Link
        href={`/planner?plotId=${encodeURIComponent(plot.id)}`}
        className="mt-2 flex w-full items-center justify-center rounded-md bg-neutral-900 px-2 py-1.5 text-xs font-medium text-white hover:bg-neutral-700"
      >
        Open in planner →
      </Link>
    </div>
  );
}

export function WholeTpMap({
  plots,
  width = 800,
  height = 480,
  className = "",
}: WholeTpMapProps) {
  const router = useRouter();
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);
  const [hoveredPlot, setHoveredPlot] = useState<PlotWithGeometry | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const openInPlanner = useCallback(
    (plotId: string) => {
      setSelectedPlotId(plotId);
      router.push(`/planner?plotId=${encodeURIComponent(plotId)}`);
    },
    [router, setSelectedPlotId],
  );

  const { model, bounds, transform, featureToPlot, labelPositions } =
    useMemo(() => {
      const features: GeometryFeature[] = [];
      const featureToPlotMap = new Map<string, PlotWithGeometry>();
      const labelPositionsMap = new Map<string, [number, number]>();

      for (const plot of plots) {
        if (!plot.geometry) continue;
        const single = parseGeoJsonToModel(
          plot.geometry as GeoJsonInput,
          "plotBoundary",
        );
        for (const f of single.features) {
          const fid = `${plot.id}-${f.id}`;
          features.push({ ...f, id: fid });
          featureToPlotMap.set(fid, plot);
        }
      }

      const model: GeometryModel = { features };
      const bounds = computeBoundsForModel(model);
      const transform =
        bounds && features.length > 0
          ? createViewTransform(bounds, width, height, 24)
          : null;

      if (transform) {
        for (const f of features) {
          const center = getFeatureCenter(f);
          if (center) {
            const projected = projectPosition(center, transform);
            labelPositionsMap.set(f.id, projected);
          }
        }
      }

      return {
        model,
        bounds,
        transform,
        featureToPlot: featureToPlotMap,
        labelPositions: labelPositionsMap,
      };
    }, [plots, width, height]);

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent<SVGElement>, featureId: string) => {
      const plot = featureToPlot.get(featureId);
      if (plot) {
        setHoveredPlot(plot);
        setTooltipPos({ x: e.clientX, y: e.clientY });
      }
    },
    [featureToPlot],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (hoveredPlot) setTooltipPos({ x: e.clientX, y: e.clientY });
    },
    [hoveredPlot],
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredPlot(null);
  }, []);

  if (!transform || model.features.length === 0) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-dashed border-neutral-200 bg-neutral-50 text-sm text-neutral-500 ${className}`}
        style={{ width, height }}
      >
        No geometry to show for whole TP
      </div>
    );
  }

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={`overflow-hidden rounded-lg border border-neutral-200 bg-white ${className}`}
        style={{
          width: "100%",
          height: "auto",
          aspectRatio: `${width} / ${height}`,
        }}
        aria-label="Whole TP scheme overview"
        onMouseLeave={handleMouseLeave}
        onMouseMove={handleMouseMove}
      >
        <g>
          {model.features.map((feature) => (
            <path
              key={feature.id}
              d={geometryFeatureToPath(feature, transform)}
              fill={
                hoveredPlot && featureToPlot.get(feature.id)?.id === hoveredPlot.id
                  ? "rgba(59, 130, 246, 0.2)"
                  : "rgba(15,23,42,0.08)"
              }
              stroke={
                hoveredPlot && featureToPlot.get(feature.id)?.id === hoveredPlot.id
                  ? "#2563eb"
                  : "#334155"
              }
              strokeWidth={
                hoveredPlot && featureToPlot.get(feature.id)?.id === hoveredPlot.id
                  ? 2
                  : 1
              }
              onMouseEnter={(e) => handleMouseEnter(e, feature.id)}
              onClick={() => {
                const plot = featureToPlot.get(feature.id);
                if (plot) openInPlanner(plot.id);
              }}
              style={{ cursor: "pointer" }}
            />
          ))}
        </g>
        <g aria-hidden="true">
          {model.features.map((feature) => {
            const pos = labelPositions.get(feature.id);
            if (!pos) return null;
            const plot = featureToPlot.get(feature.id);
            const name = plot?.name ?? feature.id;
            const hasTag = plot?.designation || (plot?.roadWidthM != null);
            return (
              <g key={`label-${feature.id}`}>
                <text
                  x={pos[0]}
                  y={pos[1]}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="select-none fill-neutral-800 text-[10px] font-semibold"
                >
                  {name}
                </text>
                {plot?.designation && (
                  <text
                    x={pos[0]}
                    y={pos[1] + 12}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="select-none fill-amber-800 text-[8px] font-medium"
                  >
                    {plot.designation}
                  </text>
                )}
                {plot?.roadWidthM != null && (
                  <text
                    x={pos[0]}
                    y={pos[1] + (plot?.designation ? 22 : 12)}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="select-none fill-slate-600 text-[8px]"
                  >
                    {plot.roadWidthM.toFixed(2)} MT
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
      {hoveredPlot && (
        <PlotTooltip
          plot={hoveredPlot}
          x={tooltipPos.x}
          y={tooltipPos.y}
        />
      )}
    </div>
  );
}
