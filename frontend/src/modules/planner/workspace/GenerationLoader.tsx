"use client";

type GenerationLoaderProps = {
  progress: number | null;
  stageLabel?: string;
  stageDescription?: string;
  /** When true, renders a small floating pill instead of the full-screen loader. */
  compact?: boolean;
};

export function GenerationLoader({
  progress,
  stageLabel = "Generating floor plan layout…",
  stageDescription,
  compact = false,
}: GenerationLoaderProps) {
  const hasProgress = typeof progress === "number" && progress >= 0;
  const value = hasProgress ? Math.min(100, Math.max(0, progress)) : 0;
  const displayPct = Math.round(value);

  if (compact) {
    return (
      <div className="flex items-center gap-2 rounded-full border border-neutral-200 bg-white/95 px-3 py-1.5 shadow-md backdrop-blur-sm">
        <div
          className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-neutral-200 border-t-orange-500 animate-spin"
          aria-hidden
        />
        <span className="text-xs font-medium text-neutral-600">
          {stageLabel}
        </span>
        <span className="tabular-nums text-xs font-semibold text-orange-600">
          {hasProgress ? `${displayPct}%` : "…"}
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-1 flex-col items-center justify-center rounded-md border border-dashed border-neutral-300 bg-neutral-50/80 px-6">
      <div className="w-full max-w-sm flex flex-col items-center gap-6">
        {/* Spinner */}
        <div
          className="h-10 w-10 shrink-0 rounded-full border-2 border-neutral-200 border-t-orange-500 animate-spin"
          aria-hidden
        />
        {/* Title */}
        <p className="text-sm font-medium text-neutral-700">
          {stageDescription ?? "Generating floor plan layout…"}
        </p>
        {/* Progress bar */}
        <div className="w-full space-y-2">
          <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200">
            <div
              className="h-full rounded-full bg-gradient-to-r from-orange-500 to-amber-500 transition-[width] duration-500 ease-out"
              style={{ width: `${value}%` }}
              role="progressbar"
              aria-valuenow={displayPct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Generation progress"
            />
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-neutral-500">{stageLabel}</span>
            <span className="font-medium tabular-nums text-neutral-600">
              {hasProgress ? `${displayPct}%` : "…"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
