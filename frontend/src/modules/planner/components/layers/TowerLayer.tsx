"use client";

import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { projectPosition } from "@/geometry/transform";
import { getFeatureCentroid } from "@/geometry/centroid";
import { LayerPath } from "./LayerPath";

type TowerLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
  selectedTowerIndex: number | null;
  onFeatureHover?: (f: GeometryFeature | null) => void;
  onFeatureClick?: (feature: GeometryFeature, index: number) => void;
};

export function TowerLayer({
  features,
  viewTransform,
  visible,
  selectedTowerIndex,
  onFeatureHover,
  onFeatureClick,
}: TowerLayerProps) {
  if (!visible || !features.length) return null;
  return (
    <>
      {features.map((feature, index) => (
        <LayerPath
          key={feature.id}
          feature={feature}
          viewTransform={viewTransform}
          fill="#111827"
          stroke="#111827"
          strokeWidth={1}
          highlighted={selectedTowerIndex === index}
          onMouseEnter={() => onFeatureHover?.(feature)}
          onMouseLeave={() => onFeatureHover?.(null)}
          onClick={
            onFeatureClick
              ? () => onFeatureClick(feature, index)
              : undefined
          }
        />
      ))}

      {features.map((feature, index) => {
        const worldPos = getFeatureCentroid(feature);
        if (!worldPos) return null;
        const [x, y] = projectPosition(worldPos, viewTransform);
        const label =
          (feature.properties?.towerId as string) ?? `T${index + 1}`;
        return (
          <text
            key={`${feature.id}-label`}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="select-none"
            style={{
              fontSize: 10,
              fill: "#ffffff",
            }}
          >
            {label}
          </text>
        );
      })}
    </>
  );
}
