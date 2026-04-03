"use client";

import { useMemo } from "react";
import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { geometryFeatureToPath } from "@/geometry/pathBuilder";

const HATCH_PATTERN_ID = "cop-hatch-pattern";

type CopLayerProps = {
  features: GeometryFeature[];
  viewTransform: ViewTransform;
  visible: boolean;
  onFeatureHover?: (f: GeometryFeature | null) => void;
};

export function CopLayer({
  features,
  viewTransform,
  visible,
  onFeatureHover,
}: CopLayerProps) {
  const paths = useMemo(
    () => features.map((f) => ({ feature: f, d: geometryFeatureToPath(f, viewTransform) })),
    [features, viewTransform],
  );

  if (!visible || !features.length) return null;

  return (
    <>
      {/* Hatch pattern definition */}
      <defs>
        <pattern
          id={HATCH_PATTERN_ID}
          patternUnits="userSpaceOnUse"
          width={8}
          height={8}
        >
          <line
            x1={0} y1={8} x2={8} y2={0}
            stroke="#16a34a"
            strokeWidth={0.9}
            opacity={0.35}
          />
        </pattern>
      </defs>

      {paths.map(({ feature, d }) => {
        if (!d) return null;
        return (
          <g
            key={feature.id}
            onMouseEnter={() => onFeatureHover?.(feature)}
            onMouseLeave={() => onFeatureHover?.(null)}
          >
            {/* Solid green tint base */}
            <path
              d={d}
              fill="rgba(34,197,94,0.12)"
              stroke="#16a34a"
              strokeWidth={2}
            />
            {/* Diagonal hatch overlay */}
            <path
              d={d}
              fill={`url(#${HATCH_PATTERN_ID})`}
              stroke="none"
              style={{ pointerEvents: "none" }}
            />
          </g>
        );
      })}
    </>
  );
}
