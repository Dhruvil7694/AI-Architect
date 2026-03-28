"use client";

import type { AIFloorPlanResponse } from "@/services/plannerService";
import { ZoomableImageViewer } from "./ZoomableImageViewer";

type DirectFloorPlanViewProps = {
  data: AIFloorPlanResponse | null;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  onRetry?: () => void;
};

export function DirectFloorPlanView({ data, isPending, isError, error, onRetry }: DirectFloorPlanViewProps) {
  // Loading state
  if (isPending) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-neutral-50/50">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-neutral-200 border-t-neutral-800" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="h-3 w-3 rounded-full bg-neutral-800 animate-pulse" />
            </div>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-neutral-700">Generating floor plan</p>
            <p className="mt-1 text-xs text-neutral-400">AI is designing your layout and rendering images — 15-30s</p>
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-red-200 bg-red-50/30">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
            <svg className="h-5 w-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-red-700">Floor plan generation failed</p>
          <p className="max-w-xs text-xs text-red-500">{error?.message ?? "Unknown error"}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-1 rounded-lg bg-red-100 px-4 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-200"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    );
  }

  // Empty state
  if (!data) {
    return (
      <div className="flex h-full w-full flex-1 items-center justify-center rounded-xl border border-dashed border-neutral-200 bg-neutral-50/50">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-100">
            <svg className="h-6 w-6 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 0h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-neutral-600">No floor plan yet</p>
          <p className="text-xs text-neutral-400">Select a plot and click Generate to create a floor plan</p>
        </div>
      </div>
    );
  }

  // Image viewer + metrics
  const m = data.metrics;

  return (
    <div className="flex h-full w-full flex-1 flex-col rounded-xl border border-neutral-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-neutral-100 px-4 py-2">
        <span className="text-xs font-semibold text-neutral-700">Floor Plan</span>
        {data.source === "ai" && (
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-600">
            AI Generated
          </span>
        )}
        {(data.architectural_image || data.presentation_image) && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
            DALL-E 3
          </span>
        )}
        {data.design_notes && (
          <span className="text-[10px] text-neutral-400 truncate max-w-[200px]">{data.design_notes}</span>
        )}
      </div>

      {/* Image viewer */}
      <div className="flex-1 min-h-0">
        <ZoomableImageViewer
          architecturalImage={data.architectural_image ?? null}
          presentationImage={data.presentation_image ?? null}
          svgFallback={data.svg_blueprint ?? null}
        />
      </div>

      {/* Metrics footer */}
      {m && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-neutral-100 px-4 py-2 text-[11px] text-neutral-600">
          <span><span className="font-medium text-neutral-800">{m.nUnitsPerFloor}</span> units/floor</span>
          <span><span className="font-medium text-neutral-800">{m.efficiencyPct}%</span> efficiency</span>
          <span><span className="font-medium text-neutral-800">{m.footprintSqm}</span> m² footprint</span>
          <span><span className="font-medium text-neutral-800">{m.nFloors}</span> floors</span>
          <span><span className="font-medium text-neutral-800">{m.nLifts}</span> lifts</span>
          <span><span className="font-medium text-neutral-800">{m.nStairs}</span> stairs</span>
        </div>
      )}
    </div>
  );
}
