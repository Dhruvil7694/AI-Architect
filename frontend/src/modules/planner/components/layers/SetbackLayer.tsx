"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type SetbackLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
};

export function SetbackLayer({
  features,
  viewTransform,
  visible,
}: SetbackLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="none"
          stroke="#6ee7b7"
          strokeWidth={1}
          strokeDasharray="2 2"
        />
      ))}
    </>
  );
}
