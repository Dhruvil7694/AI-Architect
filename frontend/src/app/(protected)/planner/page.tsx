"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { PlotDropdown } from "@/modules/planner/components/PlotDropdown";
import { SiteMetricsSummary } from "@/modules/planner/components/SiteMetricsSummary";
import { DevelopmentInputs } from "@/modules/planner/components/DevelopmentInputs";
import { PlannerCanvas } from "@/modules/planner/components/PlannerCanvas";
import { FloorPlanningView } from "@/modules/planner/components/FloorPlanningView";
import { Legend } from "@/modules/planner/components/Legend";
import { LayerControl } from "@/modules/planner/components/LayerControl";
import { PlanningMetricsPanel } from "@/modules/planner/components/PlanningMetricsPanel";
import { UnitInspectionPanel } from "@/modules/planner/components/UnitInspectionPanel";
import { StepNavigation } from "@/modules/planner/components/StepNavigation";
import {
  PlanGenerationControls,
  PlanGenerationStatus,
} from "@/modules/planner/components/PlanGenerationControls";
import { ScenarioBar } from "@/modules/planner/components/ScenarioBar";
import { usePlannerStore } from "@/state/plannerStore";
import { usePlanGeometry, usePlanJobStatus } from "@/modules/planner/hooks/usePlannerData";

function PlannerContent() {
  const searchParams = useSearchParams();
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);
  const isInputsPanelOpen = usePlannerStore((s) => s.isInputsPanelOpen);
  const toggleInputsPanel = usePlannerStore((s) => s.toggleInputsPanel);
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const planningStep = usePlannerStore((s) => s.planningStep);
  const debugMode = usePlannerStore((s) => s.debugMode);
  const toggleDebugMode = usePlannerStore((s) => s.toggleDebugMode);
  const { data: geometryModel = null } = usePlanGeometry(activeScenarioId);
  const { data: jobStatus } = usePlanJobStatus(activeScenarioId);

  // Show loading as soon as a job is active, before the first status poll returns.
  // Without this, the canvas flashes "No geometry loaded" for ~1.5 s after submit.
  const isPlanLoading =
    !!activeScenarioId &&
    geometryModel === null &&
    (!jobStatus || jobStatus.status === "pending" || jobStatus.status === "running");
  const loadingProgress =
    typeof jobStatus?.progress === "number" ? jobStatus.progress : null;

  useEffect(() => {
    const plotId = searchParams.get("plotId");
    if (plotId) setSelectedPlotId(plotId);
  }, [searchParams, setSelectedPlotId]);

  return (
    <div className="-mx-6 -mb-6 -mt-6 flex min-h-[calc(100vh-7rem)] flex-col">
      {/* Top bar: plot + step nav + metrics + actions */}
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-neutral-200 bg-white px-4 py-2">
        <PlotDropdown />
        <StepNavigation />
        <SiteMetricsSummary />
        <div className="hidden sm:block h-4 w-px bg-neutral-200" aria-hidden />
        <div className="flex flex-1 flex-wrap items-center justify-end gap-3">
          <Legend />
          <PlanGenerationStatus />
          <PlanGenerationControls />
          <button
            type="button"
            onClick={toggleDebugMode}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              debugMode ? "bg-amber-200 text-amber-900" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
            }`}
            title="Toggle debug layers"
          >
            Debug
          </button>
          <button
            type="button"
            onClick={toggleInputsPanel}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              isInputsPanelOpen
                ? "bg-neutral-200 text-neutral-800"
                : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200 hover:text-neutral-800"
            }`}
          >
            {isInputsPanelOpen ? "Hide inputs" : "Inputs"}
          </button>
        </div>
      </header>

      {/* Main: sidebar (layers + metrics) + canvas */}
      <section className="relative flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
        <aside className="flex w-56 shrink-0 flex-col gap-3 overflow-auto">
          <LayerControl />
          <PlanningMetricsPanel />
          {planningStep === "floor" && <UnitInspectionPanel />}
        </aside>
        <div className="min-h-0 flex-1">
          {planningStep === "site" ? (
            <PlannerCanvas
              geometryModel={geometryModel}
              isLoading={isPlanLoading}
              loadingProgress={loadingProgress}
            />
          ) : (
            <FloorPlanningView geometryModel={geometryModel} />
          )}
        </div>
      </section>

      {/* Slim scenario bar */}
      <footer className="shrink-0 border-t border-neutral-200 bg-white px-4 py-2">
        <ScenarioBar />
      </footer>

      {/* Inputs as overlay drawer (slides in from right) */}
      {isInputsPanelOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20"
            aria-hidden
            onClick={toggleInputsPanel}
          />
          <aside
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col border-l border-neutral-200 bg-white shadow-xl"
            aria-label="Development inputs"
          >
            <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
              <h2 className="text-sm font-semibold text-neutral-900">
                Development inputs
              </h2>
              <button
                type="button"
                onClick={toggleInputsPanel}
                className="rounded p-1 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800"
                aria-label="Close inputs"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <DevelopmentInputs key={selectedPlotId ?? "none"} />
            </div>
          </aside>
        </>
      )}
    </div>
  );
}

export default function PlannerPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center p-8 text-sm text-neutral-500">
          Loading planner…
        </div>
      }
    >
      <PlannerContent />
    </Suspense>
  );
}
