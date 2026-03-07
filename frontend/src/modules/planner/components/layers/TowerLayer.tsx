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
      {features.map((feature, index) => {
        const isSelected = selectedTowerIndex === index;
        return (
          <LayerPath
            key={feature.id}
            feature={feature}
            viewTransform={viewTransform}
            fill={isSelected ? "rgba(29,78,216,0.88)" : "rgba(37,99,235,0.75)"}
            stroke={isSelected ? "#1d4ed8" : "#2563eb"}
            strokeWidth={isSelected ? 2 : 1}
            highlighted={isSelected}
            onMouseEnter={() => onFeatureHover?.(feature)}
            onMouseLeave={() => onFeatureHover?.(null)}
            onClick={
              onFeatureClick
                ? () => onFeatureClick(feature, index)
                : undefined
            }
          />
        );
      })}

      {features.map((feature, index) => {
        const worldPos = getFeatureCentroid(feature);
        if (!worldPos) return null;
        const [x, y] = projectPosition(worldPos, viewTransform);
        const towerId =
          (feature.properties?.towerId as string) ?? `T${index + 1}`;
        const floors = feature.properties?.floors as number | undefined;
        const labelLine1 = towerId;
        const labelLine2 = floors != null ? `${floors}F` : null;
        return (
          <g key={`${feature.id}-label`} style={{ pointerEvents: "none" }}>
            <text
              x={x}
              y={labelLine2 ? y - 5 : y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="select-none"
              style={{ fontSize: 10, fontWeight: 600, fill: "#ffffff" }}
            >
              {labelLine1}
            </text>
            {labelLine2 && (
              <text
                x={x}
                y={y + 7}
                textAnchor="middle"
                dominantBaseline="middle"
                className="select-none"
                style={{ fontSize: 8, fill: "rgba(255,255,255,0.8)" }}
              >
                {labelLine2}
              </text>
            )}
          </g>
        );
      })}
    </>
  );
}
