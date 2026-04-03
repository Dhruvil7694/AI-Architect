import type { Position } from "./geometryNormalizer";
import type { Bounds } from "./bounds";

export type ViewTransform = {
  scale: number;
  translateX: number;
  translateY: number;
  width: number;
  height: number;
  padding: number;
  flipY?: boolean;
};

export function createViewTransform(
  bounds: Bounds,
  canvasWidth: number,
  canvasHeight: number,
  padding = 16,
  options?: { flipY?: boolean },
): ViewTransform {
  const width = bounds.maxX - bounds.minX || 1;
  const height = bounds.maxY - bounds.minY || 1;

  const paddedWidth = canvasWidth - padding * 2;
  const paddedHeight = canvasHeight - padding * 2;

  const scaleX = paddedWidth / width;
  const scaleY = paddedHeight / height;
  const scale = Math.min(scaleX, scaleY);

  const translateX =
    -bounds.minX * scale +
    padding +
    (paddedWidth - width * scale) / 2;
  const translateY =
    -bounds.minY * scale +
    padding +
    (paddedHeight - height * scale) / 2;

  return {
    scale,
    translateX,
    translateY,
    width: canvasWidth,
    height: canvasHeight,
    padding,
    flipY: options?.flipY ?? false,
  };
}

export function projectPosition(
  position: Position,
  transform: ViewTransform,
): Position {
  const [x, y] = position;
  const px = x * transform.scale + transform.translateX;
  const pyRaw = y * transform.scale + transform.translateY;
  const py = transform.flipY ? transform.height - pyRaw : pyRaw;
  return [px, py];
}

export function createViewTransformForSelection(
  selectionBounds: Bounds,
  canvasWidth: number,
  canvasHeight: number,
  padding = 32,
): ViewTransform {
  return createViewTransform(
    selectionBounds,
    canvasWidth,
    canvasHeight,
    padding,
  );
}

