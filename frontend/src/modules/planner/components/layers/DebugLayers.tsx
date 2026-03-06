"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { LayerPath } from "./LayerPath";

type DebugLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
  fill: string;
  stroke: string;
  strokeDasharray?: string;
};

export function BuildableEnvelopeLayer({
  features,
  viewTransform,
  visible,
  fill = "rgba(147,51,234,0.08)",
  stroke = "#7c3aed",
  strokeDasharray = "2 2",
}: DebugLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill={fill}
          stroke={stroke}
          strokeDasharray={strokeDasharray}
        />
      ))}
    </>
  );
}

export function CopCandidateZonesLayer({
  features,
  viewTransform,
  visible,
  fill = "rgba(236,72,153,0.1)",
  stroke = "#db2777",
  strokeDasharray = "2 2",
}: DebugLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill={fill}
          stroke={stroke}
          strokeDasharray={strokeDasharray}
        />
      ))}
    </>
  );
}

export function RoadNetworkLayer({
  features,
  viewTransform,
  visible,
  fill = "none",
  stroke = "#dc2626",
  strokeWidth = 1,
  strokeDasharray = "2 2",
}: DebugLayerProps & { strokeWidth?: number }) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeDasharray={strokeDasharray}
        />
      ))}
    </>
  );
}
