"use client";

import { useQuery } from "@tanstack/react-query";
import { getPlotById, type PlotDetail } from "@/services/plotsService";
import { queryKeys } from "@/lib/queryKeys";
import { type GeoJsonInput } from "@/geometry/geometryNormalizer";
import {
  parseGeoJsonToModel,
  type GeometryModel,
} from "@/geometry/geojsonParser";
import { computeBoundsForModel } from "@/geometry/bounds";
import { createViewTransform } from "@/geometry/transform";
import { geometryFeatureToPath } from "@/geometry/pathBuilder";

type MiniPlotPreviewProps =
  | {
      plotId: string;
      geometry?: undefined;
    }
  | {
      plotId?: undefined;
      geometry: GeoJsonInput;
    };

export function MiniPlotPreview(props: MiniPlotPreviewProps) {
  const { plotId } = props;

  const geometryInput: GeoJsonInput | undefined =
    "geometry" in props ? props.geometry : undefined;

  const { data } = useQuery<PlotDetail | null>({
    queryKey:
      geometryInput || !plotId
        ? ["plots", "detail", "inline-geometry"]
        : queryKeys.plots.detail(plotId),
    queryFn: () =>
      geometryInput || !plotId
        ? Promise.resolve(null)
        : getPlotById(plotId),
    enabled: Boolean(plotId) && !geometryInput,
  });

  const geoSource: GeoJsonInput =
    geometryInput ?? (data?.geometry as GeoJsonInput);

  if (!geoSource) {
    return (
      <div className="flex h-20 w-32 items-center justify-center rounded border border-dashed border-neutral-200 bg-neutral-50 text-[10px] text-neutral-400">
        No geometry
      </div>
    );
  }

  const model: GeometryModel = parseGeoJsonToModel(
    geoSource,
    "plotBoundary",
  );

  if (!model.features.length) {
    return (
      <div className="flex h-20 w-32 items-center justify-center rounded border border-dashed border-neutral-200 bg-neutral-50 text-[10px] text-neutral-400">
        No geometry
      </div>
    );
  }

  const bounds = computeBoundsForModel(model);
  if (!bounds) {
    return (
      <div className="flex h-20 w-32 items-center justify-center rounded border border-dashed border-neutral-200 bg-neutral-50 text-[10px] text-neutral-400">
        No geometry
      </div>
    );
  }

  const width = 128;
  const height = 80;
  const transform = createViewTransform(bounds, width, height, 4);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-20 w-32 overflow-hidden rounded border border-neutral-200 bg-white"
    >
      <g>
        {model.features.map((feature) => (
          <path
            key={feature.id}
            d={geometryFeatureToPath(feature, transform)}
            fill="rgba(15,23,42,0.06)"
            stroke="#111827"
            strokeWidth={1}
          />
        ))}
      </g>
    </svg>
  );
}

