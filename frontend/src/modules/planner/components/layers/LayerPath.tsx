"use client";

import { useMemo } from "react";
import type { GeometryFeature } from "@/geometry/geojsonParser";
import type { ViewTransform } from "@/geometry/transform";
import { geometryFeatureToPath } from "@/geometry/pathBuilder";

type LayerPathProps = {
  feature: GeometryFeature;
  viewTransform: ViewTransform;
  fill: string;
  stroke: string;
  strokeWidth?: number;
  strokeDasharray?: string;
  className?: string;
  highlighted?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onClick?: () => void;
};

export function LayerPath({
  feature,
  viewTransform,
  fill,
  stroke,
  strokeWidth = 1,
  strokeDasharray,
  className,
  highlighted,
  onMouseEnter,
  onMouseLeave,
  onClick,
}: LayerPathProps) {
  const d = useMemo(
    () => geometryFeatureToPath(feature, viewTransform),
    [feature, viewTransform],
  );
  if (!d) return null;
  return (
    <path
      d={d}
      fill={fill}
      stroke={highlighted ? "#f59e0b" : stroke}
      strokeWidth={highlighted ? 2.5 : strokeWidth}
      strokeDasharray={strokeDasharray}
      className={className}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onClick={onClick}
      style={{ cursor: onClick ? "pointer" : undefined }}
    />
  );
}
