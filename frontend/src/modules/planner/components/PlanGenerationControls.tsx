"use client";

import { usePlannerStore } from "@/state/plannerStore";
import { Zap, AlertCircle, Loader2 } from "lucide-react";

type PlanGenerationControlsProps = {
  onGenerate: () => void;
  isGenerating: boolean;
  isError: boolean;
};

export function PlanGenerationControls({ onGenerate, isGenerating, isError }: PlanGenerationControlsProps) {
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);
  const inputs = usePlannerStore((state) => state.inputs);

  const hasUnitMix = inputs.unitMix && inputs.unitMix.length > 0;
  const disabled = !selectedPlotId || !hasUnitMix || isGenerating;

  return (
    <div className="inline-flex items-center gap-3">
      {isError && (
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-red-500 bg-red-50 px-3 py-1 rounded-full border border-red-100">
          <AlertCircle className="h-3 w-3" />
          Error
        </span>
      )}

      <button
        type="button"
        onClick={onGenerate}
        disabled={disabled}
        className={`group relative overflow-hidden rounded-2xl px-6 py-2.5 text-sm font-bold tracking-tight transition-all duration-300 ${
          disabled
            ? "cursor-not-allowed bg-neutral-100 text-neutral-400"
            : "bg-neutral-900 text-white shadow-xl shadow-neutral-900/10 hover:shadow-orange-500/20 active:scale-95"
        }`}
      >
        <div className="relative z-10 flex items-center gap-2">
          {isGenerating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin text-orange-400" />
              <span className="font-heading">Generating...</span>
            </>
          ) : (
            <>
              <Zap className={`h-4 w-4 transition-colors ${disabled ? "text-neutral-400" : "text-orange-400 group-hover:text-orange-300"}`} fill="currentColor" />
              <span className="font-heading">Generate</span>
            </>
          )}
        </div>
        {!disabled && !isGenerating && (
          <div className="absolute inset-0 bg-gradient-to-r from-orange-600/0 via-orange-500/10 to-orange-600/0 opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
      </button>
    </div>
  );
}

export function PlanGenerationStatus({ isGenerating, isComplete }: { isGenerating: boolean; isComplete: boolean }) {
  if (isGenerating) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-orange-100 bg-orange-50/50 px-4 py-2">
        <div className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-orange-500" />
        </div>
        <span className="font-heading text-xs font-bold text-orange-700 uppercase tracking-wider">
          AI Computing
        </span>
      </div>
    );
  }

  if (isComplete) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-2 shadow-sm">
        <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="font-heading text-xs font-bold text-emerald-700 uppercase tracking-wider">
          Plan Ready
        </span>
      </div>
    );
  }

  return null;
}
