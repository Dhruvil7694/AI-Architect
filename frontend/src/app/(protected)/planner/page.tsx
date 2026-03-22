"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { PlotDropdown } from "@/modules/planner/components/PlotDropdown";
import { SiteMetricsSummary } from "@/modules/planner/components/SiteMetricsSummary";
import { DevelopmentInputs } from "@/modules/planner/components/DevelopmentInputs";
import { PlannerCanvas } from "@/modules/planner/components/PlannerCanvas";
import { FloorPlanningView } from "@/modules/planner/components/FloorPlanningView";
import { UnitInteriorView } from "@/modules/planner/components/UnitInteriorView";
import { Legend } from "@/modules/planner/components/Legend";
import { LayerControl } from "@/modules/planner/components/LayerControl";
import { PlanningMetricsPanel } from "@/modules/planner/components/PlanningMetricsPanel";
import { UnitInspectionPanel } from "@/modules/planner/components/UnitInspectionPanel";
import { StepNavigation } from "@/modules/planner/components/StepNavigation";
import { PlannerAssistantPanel } from "@/modules/planner/components/PlannerAssistantPanel";
import {
  PlanGenerationControls,
  PlanGenerationStatus,
} from "@/modules/planner/components/PlanGenerationControls";
import { ScenarioBar } from "@/modules/planner/components/ScenarioBar";
import { TpMapPicker } from "@/modules/plots/components/TpMapPicker";
import { PlotInfoSidebar } from "@/modules/planner/components/PlotInfoSidebar";
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
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const { data: geometryModel = null } = usePlanGeometry(activeScenarioId);
  const { data: jobStatus } = usePlanJobStatus(activeScenarioId);

  const isPlanLoading =
    !!activeScenarioId &&
    geometryModel === null &&
    jobStatus?.status !== "failed";
  const loadingProgress =
    typeof jobStatus?.progress === "number" ? jobStatus.progress : null;

  useEffect(() => {
    const plotId = searchParams.get("plotId");
    if (plotId) setSelectedPlotId(plotId);
  }, [searchParams, setSelectedPlotId]);

  return (
    <div className="flex min-h-[calc(100vh-64px)] flex-col bg-white font-sans">
      {/* Top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-neutral-200 bg-white/80 backdrop-blur-md px-6 py-3 shadow-sm">
        <div className="flex items-center gap-6">
          <PlotDropdown />
          {selectedPlotId && <StepNavigation />}
        </div>

        <div className="flex items-center gap-4">
          {selectedPlotId && <SiteMetricsSummary />}
          {selectedPlotId && <div className="hidden lg:block h-6 w-px bg-neutral-200" aria-hidden />}
          {selectedPlotId && <Legend />}
          {selectedPlotId && <PlanGenerationStatus />}
          {selectedPlotId && <PlanGenerationControls />}
          
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleDebugMode}
              className={`flex items-center justify-center rounded-full p-2 text-neutral-500 transition-colors ${
                debugMode ? "bg-amber-100 text-amber-600" : "hover:bg-neutral-100 hover:text-neutral-800"
              }`}
              title="Toggle debug layers"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </button>
            <button
              type="button"
              onClick={toggleInputsPanel}
              className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
                isInputsPanelOpen
                  ? "bg-orange-100 text-orange-700"
                  : "bg-white border border-neutral-200 text-neutral-700 hover:border-orange-200 hover:bg-orange-50 hover:text-orange-600 shadow-sm"
              }`}
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              <span>{isInputsPanelOpen ? "Close Inputs" : "Inputs"}</span>
            </button>
          </div>
        </div>
      </header>

      <section className="relative flex flex-1 p-6 gap-6 overflow-hidden">
        {selectedPlotId ? (
          <>
            {/* Left Sidebar — Plot info + layer controls */}
            <aside className="w-80 shrink-0 flex flex-col overflow-y-auto pb-4 scrollbar-hide border-r border-neutral-100">
              {/* Plot info sidebar (parameters, unit conversion) */}
              <div className="rounded-xl border border-neutral-200 bg-white shadow-sm overflow-hidden mb-4">
                <PlotInfoSidebar />
              </div>
              <div className="flex flex-col gap-4">
                <LayerControl />
                <PlanningMetricsPanel />
                {planningStep === "floor" && <UnitInspectionPanel />}
                <PlannerAssistantPanel />
              </div>
            </aside>

            {/* Canvas Area */}
            <div className="min-h-0 flex-1 rounded-[2rem] border border-neutral-100 bg-[#fbfbfb] shadow-inner overflow-hidden relative">
              {planningStep === "site" ? (
                <PlannerCanvas
                  geometryModel={geometryModel}
                  isLoading={isPlanLoading}
                  loadingProgress={loadingProgress}
                />
              ) : planningStep === "floor" ? (
                <FloorPlanningView geometryModel={geometryModel} />
              ) : (
                <UnitInteriorView />
              )}
            </div>
          </>
        ) : (
          /* No FP selected — show full TP map for selection */
          <div className="min-h-0 flex-1 rounded-[2rem] border border-neutral-100 bg-white shadow-inner overflow-hidden relative p-6">
            <TpMapPicker
              tpScheme={locationPreference.tpId ?? "TP14"}
              city={locationPreference.districtName}
              selectedPlotId={selectedPlotId ?? undefined}
              onPlotSelect={(id) => setSelectedPlotId(id)}
            />
          </div>
        )}
      </section>

      {/* Scenario Bar Footer — only when a plot is selected */}
      {selectedPlotId && (
        <footer className="shrink-0 border-t border-neutral-200 bg-white shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] z-20">
          <ScenarioBar />
        </footer>
      )}

      {/* Right Sidebar - Inputs */}
      {isInputsPanelOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-neutral-900/20 backdrop-blur-sm transition-opacity"
            aria-hidden
            onClick={toggleInputsPanel}
          />
          <aside
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-sm flex-col bg-white shadow-2xl transition-transform transform translate-x-0 border-l border-neutral-200"
            aria-label="Development inputs"
          >
            <div className="flex items-center justify-between border-b border-neutral-100 px-6 py-4">
              <h2 className="text-lg font-bold text-neutral-900 tracking-tight">
                Development Parameters
              </h2>
              <button
                type="button"
                onClick={toggleInputsPanel}
                className="rounded-full p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-800 transition-colors"
                aria-label="Close inputs"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4 scrollbar-hide">
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
        <div className="flex h-[calc(100vh-64px)] items-center justify-center bg-[#F9FAFB]">
          <div className="flex flex-col items-center gap-4">
            <span className="h-8 w-8 animate-spin rounded-full border-4 border-orange-200 border-t-orange-500" />
            <span className="text-sm font-medium text-neutral-500">Loading planner workspace...</span>
          </div>
        </div>
      }
    >
      <PlannerContent />
    </Suspense>
  );
}
