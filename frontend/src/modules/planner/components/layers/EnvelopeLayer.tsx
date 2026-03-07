"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type EnvelopeLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
  onFeatureHover?: (f: GeometryFeature | null) => void;
};

export function EnvelopeLayer({
  features,
  viewTransform,
  visible,
  onFeatureHover,
}: EnvelopeLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="rgba(251,243,219,0.55)"
          stroke="#d97706"
          strokeWidth={1.5}
          strokeDasharray="6 3"
          onMouseEnter={() => onFeatureHover?.(feature)}
          onMouseLeave={() => onFeatureHover?.(null)}
        />
      ))}
    </>
  );
}
