"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type RoadCorridorLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
};

export function RoadCorridorLayer({
  features,
  viewTransform,
  visible,
}: RoadCorridorLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="rgba(120,113,108,0.2)"
          stroke="#78716c"
          strokeWidth={1}
        />
      ))}
    </>
  );
}
