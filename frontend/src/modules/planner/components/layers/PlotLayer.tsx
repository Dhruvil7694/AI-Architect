"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type PlotLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
  onFeatureHover?: (f: GeometryFeature | null) => void;
  onFeatureClick?: (f: GeometryFeature) => void;
};

export function PlotLayer({
  features,
  viewTransform,
  visible,
  onFeatureHover,
  onFeatureClick,
}: PlotLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="rgba(248,246,242,0.6)"
          stroke="#1f2937"
          strokeWidth={2}
          onMouseEnter={() => onFeatureHover?.(feature)}
          onMouseLeave={() => onFeatureHover?.(null)}
          onClick={onFeatureClick ? () => onFeatureClick(feature) : undefined}
        />
      ))}
    </>
  );
}
