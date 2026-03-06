"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type TowerZoneLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
};

export function TowerZoneLayer({
  features,
  viewTransform,
  visible,
}: TowerZoneLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="rgba(234,179,8,0.15)"
          stroke="#ca8a04"
          strokeWidth={1}
          strokeDasharray="3 2"
        />
      ))}
    </>
  );
}
