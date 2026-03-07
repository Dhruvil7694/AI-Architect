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
          fill="rgba(254,243,199,0.45)"
          stroke="#f59e0b"
          strokeWidth={1}
          strokeDasharray="4 2"
        />
      ))}
    </>
  );
}
