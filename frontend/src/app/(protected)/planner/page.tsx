"use client";

import { Suspense, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { PlotDropdown } from "@/modules/planner/components/PlotDropdown";
import { SiteMetricsSummary } from "@/modules/planner/components/SiteMetricsSummary";
import { DevelopmentInputs } from "@/modules/planner/components/DevelopmentInputs";
import { DirectFloorPlanView } from "@/modules/planner/components/DirectFloorPlanView";
import { PlotExplorationView } from "@/modules/planner/components/PlotExplorationView";
import {
  PlanGenerationControls,
  PlanGenerationStatus,
} from "@/modules/planner/components/PlanGenerationControls";
import { WholeTpMap } from "@/modules/plots/components/WholeTpMap";
import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { usePlannerStore } from "@/state/plannerStore";
import { useAIFloorPlan, useFeasibility } from "@/modules/planner/hooks/usePlannerData";

function PlannerContent() {
  const searchParams = useSearchParams();
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);
  const isInputsPanelOpen = usePlannerStore((s) => s.isInputsPanelOpen);
  const toggleInputsPanel = usePlannerStore((s) => s.toggleInputsPanel);
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const planningStep = usePlannerStore((s) => s.planningStep);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const inputs = usePlannerStore((s) => s.inputs);
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const imageModel = usePlannerStore((s) => s.imageModel);
  const setImageModel = usePlannerStore((s) => s.setImageModel);

  const { data: plots = [], isLoading: plotsLoading } = usePlotsQuery({
    tpScheme: locationPreference.tpId,
    city: locationPreference.districtName,
  });
  const { data: feasibility } = useFeasibility(selectedPlotId);

  // AI floor plan mutation — called directly from Generate button
  const aiFloorPlan = useAIFloorPlan();

  // Resolve the selected plot object
  const selectedPlot = useMemo(
    () => plots.find((p) => p.id === selectedPlotId) ?? null,
    [plots, selectedPlotId],
  );

  // ── Generate handler: skip site plan, call AI floor plan directly ──────────
  const handleGenerate = useCallback(() => {
    if (!selectedPlot?.geometry || !selectedPlotId) return;

    const geo = selectedPlot.geometry as { type: string; coordinates: number[][][] };
    if (geo.type !== "Polygon") return;

    const nFloors = inputs.floors ?? feasibility?.maxFloors ?? 10;
    const storeyHeight = inputs.storeyHeightM ?? 3.0;

    aiFloorPlan.mutate({
      footprint: geo as { type: "Polygon"; coordinates: number[][][] },
      n_floors: nFloors,
      building_height_m: nFloors * storeyHeight,
      units_per_core: inputs.unitsPerCore ?? 4,
      building_type: inputs.buildingType,
      segment: inputs.segment ?? "mid",
      unit_mix: inputs.unitMix ?? ["2BHK", "3BHK"],
      storey_height_m: storeyHeight,
      plot_area_sqm: feasibility?.plotAreaSqm ?? selectedPlot.areaSqm ?? 0,
      image_model: imageModel,
    });

    // Switch directly to floor step
    setPlanningStep("floor");
  }, [selectedPlot, selectedPlotId, inputs, feasibility, aiFloorPlan, setPlanningStep, imageModel]);

  // Retry uses the same handler
  const handleRetry = handleGenerate;

  useEffect(() => {
    const plotId = searchParams.get("plotId");
    if (plotId) setSelectedPlotId(plotId);
  }, [searchParams, setSelectedPlotId]);

  const showFloorPlan = planningStep === "floor";

  return (
    <div className="-mx-6 -mb-6 -mt-6 flex min-h-[calc(100vh-7rem)] flex-col">
      {/* Top bar */}
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-neutral-200 bg-white px-4 py-2">
        <PlotDropdown />
        <SiteMetricsSummary />
        <div className="hidden sm:block h-4 w-px bg-neutral-200" aria-hidden />
        <div className="flex flex-1 flex-wrap items-center justify-end gap-3">
          <PlanGenerationStatus
            isGenerating={aiFloorPlan.isPending}
            isComplete={!!aiFloorPlan.data && !aiFloorPlan.isPending}
          />
          {/* Image model selector */}
          <div className="flex items-center gap-1.5">
            <span className="hidden sm:inline text-[10px] font-medium text-neutral-400 uppercase tracking-wide">Image</span>
            <select
              value={imageModel}
              onChange={(e) => setImageModel(e.target.value)}
              disabled={aiFloorPlan.isPending}
              className="rounded-md border border-neutral-200 bg-white px-2 py-1.5 text-xs font-medium text-neutral-700 focus:outline-none focus:ring-1 focus:ring-neutral-400 disabled:opacity-50"
              title="Image generation model"
            >
              <option value="dalle3">DALL-E 3</option>
              <option value="gemini">Nano Banana (Gemini)</option>
              <option value="recraft">Recraft</option>
              <option value="ideogram">Ideogram V2</option>
              <option value="flux">FLUX (fal.ai)</option>
              <option value="svg_only">SVG only</option>
            </select>
          </div>
          <PlanGenerationControls
            onGenerate={handleGenerate}
            isGenerating={aiFloorPlan.isPending}
            isError={aiFloorPlan.isError}
          />
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

      {/* Main content */}
      {!selectedPlotId ? (
        <section className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-auto p-6">
          <div className="w-full max-w-5xl">
            <h2 className="mb-4 text-center text-lg font-semibold text-neutral-700">
              Select a plot from the map or use the dropdown above
            </h2>
            {plotsLoading ? (
              <div className="flex items-center justify-center py-20">
                <span className="h-6 w-6 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
                <span className="ml-3 text-sm text-neutral-500">Loading map...</span>
              </div>
            ) : (
              <WholeTpMap plots={plots} width={1200} height={800} />
            )}
          </div>
        </section>
      ) : showFloorPlan ? (
        <section className="relative flex min-h-0 flex-1 overflow-hidden p-3">
          <div className="min-h-0 flex-1">
            <DirectFloorPlanView
              data={aiFloorPlan.data ?? null}
              isPending={aiFloorPlan.isPending}
              isError={aiFloorPlan.isError}
              error={aiFloorPlan.error}
              onRetry={handleRetry}
            />
          </div>
        </section>
      ) : (
        <section className="relative flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
          <div className="min-h-0 flex-1">
            <PlotExplorationView />
          </div>
        </section>
      )}

      {/* Inputs drawer */}
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
