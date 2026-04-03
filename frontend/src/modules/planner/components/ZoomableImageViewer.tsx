"use client";

import { useRef, useState, useCallback, useEffect } from "react";

type ZoomableImageViewerProps = {
  architecturalImage: string | null;
  svgFallback: string | null;
};

export function ZoomableImageViewer({
  architecturalImage,
  svgFallback,
}: ZoomableImageViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [dragging, setDragging] = useState(false);
  const lastPos = useRef({ x: 0, y: 0 });

  const showSvg = !architecturalImage && !!svgFallback;

  // Fit to view on content change
  useEffect(() => {
    setTransform({ x: 0, y: 0, scale: 1 });
  }, [architecturalImage, svgFallback]);

  const fitInView = useCallback(() => {
    setTransform({ x: 0, y: 0, scale: 1 });
  }, []);

  const zoomIn = useCallback(() => {
    setTransform((t) => ({ ...t, scale: Math.min(t.scale * 1.25, 10) }));
  }, []);

  const zoomOut = useCallback(() => {
    setTransform((t) => ({ ...t, scale: Math.max(t.scale / 1.25, 0.1) }));
  }, []);

  // Wheel zoom
  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const rect = containerRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    setTransform((prev) => {
      const newScale = Math.max(0.1, Math.min(10, prev.scale * factor));
      const r = newScale / prev.scale;
      return { scale: newScale, x: mx - r * (mx - prev.x), y: my - r * (my - prev.y) };
    });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  // Drag pan
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragging) return;
      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      lastPos.current = { x: e.clientX, y: e.clientY };
      setTransform((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
    },
    [dragging],
  );

  const stopDrag = useCallback(() => setDragging(false), []);

  return (
    <div className="flex h-full w-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-1.5">
        <span className="text-[11px] text-neutral-400">
          {showSvg ? "SVG Blueprint" : architecturalImage ? "Floor Plan" : "No image"}
        </span>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={zoomIn}
            className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            title="Zoom in"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
          <button
            type="button"
            onClick={zoomOut}
            className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            title="Zoom out"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12h-15" />
            </svg>
          </button>
          <button
            type="button"
            onClick={fitInView}
            className="rounded p-1.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
            title="Reset view"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9m11.25-5.25v4.5m0-4.5h-4.5m4.5 0L15 9m-11.25 11.25v-4.5m0 4.5h4.5m-4.5 0L9 15m11.25 5.25v-4.5m0 4.5h-4.5m4.5 0L15 15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden select-none bg-neutral-50"
        style={{ cursor: dragging ? "grabbing" : "grab" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
      >
        <div
          style={{
            transformOrigin: "0 0",
            transform: `translate(${transform.x}px,${transform.y}px) scale(${transform.scale})`,
            display: "inline-block",
            lineHeight: 0,
          }}
        >
          {architecturalImage ? (
            <img
              src={`data:image/png;base64,${architecturalImage}`}
              alt="Floor plan"
              draggable={false}
              className="max-w-none"
            />
          ) : svgFallback ? (
            <div dangerouslySetInnerHTML={{ __html: svgFallback }} />
          ) : (
            <div className="flex items-center justify-center p-12 text-sm text-neutral-400">
              No image available
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-end border-t border-neutral-100 px-3 py-1 text-[10px] text-neutral-400">
        <span>Scroll to zoom · Drag to pan</span>
      </div>
    </div>
  );
}
