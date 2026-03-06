"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type SpacingLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
};

export function SpacingLayer({
  features,
  viewTransform,
  visible,
}: SpacingLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="none"
          stroke="#9ca3af"
          strokeWidth={0.75}
          strokeDasharray="2 2"
        />
      ))}
    </>
  );
}
