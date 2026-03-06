"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type CopLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
  onFeatureHover?: (f: GeometryFeature | null) => void;
};

export function CopLayer({
  features,
  viewTransform,
  visible,
  onFeatureHover,
}: CopLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="rgba(16,185,129,0.06)"
          stroke="#10b981"
          strokeWidth={1}
          onMouseEnter={() => onFeatureHover?.(feature)}
          onMouseLeave={() => onFeatureHover?.(null)}
        />
      ))}
    </>
  );
}
