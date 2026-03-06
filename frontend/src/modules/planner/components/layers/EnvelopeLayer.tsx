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
          fill="rgba(59,130,246,0.08)"
          stroke="#3b82f6"
          strokeWidth={1}
          strokeDasharray="4 2"
          onMouseEnter={() => onFeatureHover?.(feature)}
          onMouseLeave={() => onFeatureHover?.(null)}
        />
      ))}
    </>
  );
}
