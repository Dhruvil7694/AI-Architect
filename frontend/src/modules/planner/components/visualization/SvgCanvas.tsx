"use client";

import type { ReactNode } from "react";
import { useImperativeHandle, useMemo, useRef, useState } from "react";
import { computeBoundsForModel } from "@/geometry/bounds";
import type { GeometryModel } from "@/geometry/geojsonParser";
import { createViewTransform } from "@/geometry/transform";
import type { ViewTransform } from "@/geometry/transform";
// d3-zoom and d3-selection do not ship TypeScript types by default.
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-expect-error
import { select } from "d3-selection";

export type SvgCanvasHandle = {
  fitInView: () => void;
  resetView: () => void;
};

type SvgCanvasProps = {
  geometryModel: GeometryModel;
  width?: number;
  height?: number;
  canvasRef?: React.Ref<SvgCanvasHandle | null>;
  children: (ctx: {
    viewTransform: ViewTransform;
  }) => ReactNode;
};

export function SvgCanvas({
  geometryModel,
  width = 800,
  height = 600,
  canvasRef,
  children,
}: SvgCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const zoomBehaviorRef = useRef<ReturnType<typeof zoom<SVGSVGElement, unknown>> | null>(null);
  const [zoomTransform, setZoomTransform] = useState<ZoomTransform>(
    zoomIdentity,
  );

  const bounds = useMemo(
    () => computeBoundsForModel(geometryModel),
    [geometryModel],
  );

  const baseViewTransform: ViewTransform | null = useMemo(() => {
    if (!bounds) return null;
    return createViewTransform(bounds, width, height, 24);
  }, [bounds, width, height]);

  const viewTransformWithZoom: ViewTransform | null = useMemo(() => {
    if (!baseViewTransform) return null;
    return {
      ...baseViewTransform,
      translateX:
        baseViewTransform.translateX * zoomTransform.k +
        zoomTransform.x,
      translateY:
        baseViewTransform.translateY * zoomTransform.k +
        zoomTransform.y,
      scale: baseViewTransform.scale * zoomTransform.k,
    };
  }, [baseViewTransform, zoomTransform]);

  useImperativeHandle(
    canvasRef,
    () => ({
      fitInView: () => setZoomTransform(zoomIdentity),
      resetView: () => setZoomTransform(zoomIdentity),
    }),
    [],
  );

  function handleSvgRef(node: SVGSVGElement | null) {
    if (!node) return;
    svgRef.current = node;

    const zoomBehavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 20])
      .on("zoom", (event: { transform: ZoomTransform }) => {
        setZoomTransform(event.transform);
      });
    zoomBehaviorRef.current = zoomBehavior;
    select(node).call(zoomBehavior);
  }

  if (!bounds || !baseViewTransform || !viewTransformWithZoom) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-neutral-500">
        No geometry to display.
      </div>
    );
  }

  return (
    <svg
      ref={handleSvgRef}
      viewBox={`0 0 ${width} ${height}`}
      className="h-full w-full touch-pan-y bg-white"
    >
      <g>
        {children({
          viewTransform: viewTransformWithZoom,
        })}
      </g>
    </svg>
  );
}

