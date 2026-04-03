"use client";

import { useState } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useAIScenarios, usePlanCritique } from "@/modules/planner/hooks/usePlannerData";

// ─── AI Critique Panel ────────────────────────────────────────────────────────
function PlanCritiquePanel({ jobId }: { jobId: string }) {
  const [userNote, setUserNote] = useState("");
  const { mutate, data, isPending, error, reset } = usePlanCritique();

  const handleAnalyze = () => {
    mutate({ jobId, userNote });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="space-y-1 border-b border-neutral-100 pb-2">
        <h3 className="text-sm font-semibold text-neutral-900 flex items-center gap-2">
          <svg className="h-4 w-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          AI Design Review
        </h3>
        <p className="text-xs text-neutral-500 leading-relaxed">
          Get expert architectural feedback on this site plan — open space, tower placement, FSI, and next steps.
        </p>
      </div>

      <textarea
        value={userNote}
        onChange={(e) => setUserNote(e.target.value)}
        placeholder="Optional: describe a concern or ask a specific question…"
        className="h-16 w-full resize-none rounded-xl border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-800 placeholder-neutral-400 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-blue-500/10 transition-all"
      />

      <button
        type="button"
        onClick={handleAnalyze}
        disabled={isPending}
        className={`flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold transition-all duration-300 ${
          isPending
            ? "cursor-not-allowed bg-neutral-100 text-neutral-400"
            : "bg-blue-600 text-white shadow-md shadow-blue-500/20 hover:-translate-y-0.5 hover:bg-blue-700 hover:shadow-lg hover:shadow-blue-500/30"
        }`}
      >
        {isPending ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            <span>Analysing plan…</span>
          </>
        ) : (
          <>
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Analyse This Plan
          </>
        )}
      </button>

      {error && (
        <p className="text-xs font-medium text-red-500 bg-red-50 p-2 rounded-lg text-center">
          Analysis failed. Please try again.
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-blue-800">AI Insights</p>
            <button
              onClick={() => { reset(); setUserNote(""); }}
              className="text-[10px] text-neutral-400 hover:text-neutral-600"
            >
              Clear
            </button>
          </div>
          <ul className="flex flex-col gap-2">
            {data.insights.map((insight, idx) => (
              <li key={idx}
                className="flex gap-2 rounded-lg bg-blue-50/60 border border-blue-100 p-2.5 text-xs text-blue-900 leading-relaxed"
              >
                <span className="mt-0.5 flex-shrink-0 h-4 w-4 rounded-full bg-blue-200 text-blue-700 flex items-center justify-center text-[10px] font-bold">
                  {idx + 1}
                </span>
                {insight}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── AI Scenarios Panel ───────────────────────────────────────────────────────
function AIScenariosPanel() {
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const [brief, setBrief] = useState("");
  const [submittedBrief, setSubmittedBrief] = useState<string | null>(null);

  const { data, isFetching, refetch, error } = useAIScenarios(
    selectedPlotId,
    submittedBrief,
  );

  const handleGenerate = () => {
    if (!selectedPlotId || !brief.trim()) return;
    setSubmittedBrief(brief.trim());
    refetch();
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="space-y-1 border-b border-neutral-100 pb-2">
        <h3 className="text-sm font-semibold text-neutral-900 flex items-center gap-2">
          <svg className="h-4 w-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          AI Planning Scenarios
        </h3>
        <p className="text-xs text-neutral-500 leading-relaxed">
          Describe your project intent. AI translates this into parameters and suggests three planning scenarios.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="e.g. Luxury 2BHK residential with large central green..."
          className="h-24 w-full resize-none rounded-xl border border-neutral-200 bg-neutral-50 p-3 text-sm text-neutral-800 placeholder-neutral-400 focus:border-orange-500 focus:bg-white focus:outline-none focus:ring-4 focus:ring-orange-500/10 transition-all"
        />
        <button
          type="button"
          onClick={handleGenerate}
          disabled={!selectedPlotId || !brief.trim() || isFetching}
          className={`flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold transition-all duration-300 ${
            !selectedPlotId || !brief.trim() || isFetching
              ? "cursor-not-allowed bg-neutral-100 text-neutral-400"
              : "bg-orange-500 text-white shadow-md shadow-orange-500/20 hover:-translate-y-0.5 hover:bg-orange-600 hover:shadow-lg hover:shadow-orange-500/30"
          }`}
        >
          {isFetching ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              <span>Generating scenarios...</span>
            </>
          ) : (
            "Generate AI Scenarios"
          )}
        </button>
        {!selectedPlotId && (
          <p className="text-xs font-medium text-red-500 bg-red-50 p-2 rounded-lg text-center">
            Select a plot before generating scenarios.
          </p>
        )}
        {error && (
          <p className="text-xs font-medium text-red-500 bg-red-50 p-2 rounded-lg text-center">
            Could not generate scenarios. Please try again.
          </p>
        )}
      </div>

      {data && (
        <div className="flex flex-col gap-3 border-t border-neutral-100 pt-3">
          <div className="rounded-lg bg-emerald-50/50 p-3 border border-emerald-100">
            <p className="text-xs font-semibold text-emerald-800 mb-1">
              Program Summary
            </p>
            <p className="text-xs text-emerald-700/80">
              Units: <span className="font-semibold text-emerald-900">{data.program_spec.target_units}</span>
              {" • "}
              Towers: <span className="font-semibold text-emerald-900">{data.program_spec.preferred_towers}</span>
              {" • "}
              Max Floors: <span className="font-semibold text-emerald-900">{data.program_spec.max_floors}</span>
            </p>
          </div>

          <div className="flex flex-col gap-2">
            {data.scenarios.map((scenario) => (
              <div
                key={scenario.label}
                className="flex flex-col gap-2 rounded-xl border border-neutral-200 bg-white p-3 shadow-sm transition-all hover:border-orange-200 hover:shadow-md"
              >
                <div className="flex items-baseline justify-between gap-2 border-b border-neutral-100 pb-1.5">
                  <h4 className="text-xs font-bold text-neutral-900">
                    {scenario.label}
                  </h4>
                  <div className="flex gap-2 text-[11px] font-medium">
                    <span className="text-neutral-500">
                      Towers: <span className="text-neutral-900">{scenario.tower_count}</span>
                    </span>
                    <span className="text-neutral-300">•</span>
                    <span className="text-neutral-500">
                      FSI: <span className="text-neutral-900">{scenario.fsi_target.toFixed(2)}</span>
                    </span>
                  </div>
                </div>
                <ul className="flex flex-col gap-1 pl-4 text-xs text-neutral-600 list-disc">
                  {scenario.design_insights.map((note, idx) => (
                    <li key={idx} className="leading-relaxed">{note}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Root panel — tab between Review & Scenarios ─────────────────────────────
export function PlannerAssistantPanel() {
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const scenarios = usePlannerStore((s) => s.scenarios);
  const [tab, setTab] = useState<"review" | "scenarios">("review");

  // Determine which job to critique: active scenario, or most recent
  const critiqueJobId =
    activeScenarioId ??
    (scenarios.length > 0 ? scenarios[scenarios.length - 1].id : null);

  return (
    <div className="flex flex-col gap-0 rounded-xl border border-neutral-200 bg-white shadow-sm font-sans overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-neutral-100">
        <button
          className={`flex-1 py-2.5 text-xs font-semibold transition-colors ${
            tab === "review"
              ? "border-b-2 border-blue-600 text-blue-700 bg-blue-50/50"
              : "text-neutral-500 hover:text-neutral-700"
          }`}
          onClick={() => setTab("review")}
        >
          AI Review
        </button>
        <button
          className={`flex-1 py-2.5 text-xs font-semibold transition-colors ${
            tab === "scenarios"
              ? "border-b-2 border-orange-500 text-orange-600 bg-orange-50/50"
              : "text-neutral-500 hover:text-neutral-700"
          }`}
          onClick={() => setTab("scenarios")}
        >
          AI Scenarios
        </button>
      </div>

      <div className="p-4">
        {tab === "review" ? (
          critiqueJobId ? (
            <PlanCritiquePanel key={critiqueJobId} jobId={critiqueJobId} />
          ) : (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <svg className="h-8 w-8 text-neutral-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-xs text-neutral-400 leading-relaxed max-w-[180px]">
                Generate a site plan first, then come back here for an AI design review.
              </p>
            </div>
          )
        ) : (
          <AIScenariosPanel />
        )}
      </div>
    </div>
  );
}
