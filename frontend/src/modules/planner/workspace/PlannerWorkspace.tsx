"use client";

import { useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import type { PlannerProfile } from "../config/plannerProfiles";
import { groupFeaturesByLayer } from "@/geometry/layerManager";
import { usePlannerStore } from "@/state/plannerStore";
import { usePlanGeometry } from "../hooks/usePlannerData";
import { useSitePlanGeneration } from "../generation/useSitePlanGeneration";
import { PlannerTopBar } from "./PlannerTopBar";
import { PlannerTpMap } from "../components/PlannerTpMap";
import { PlotInfoSidebar } from "../components/PlotInfoSidebar";
import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";

const FloorCanvas = dynamic(
  () => import("../canvas/FloorCanvas").then((m) => ({ default: m.FloorCanvas })),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-sm text-neutral-500">Loading floor design…</div> },
);

const HIGH_RISE_MODE = "high-rise";

type Props = {
  profile: PlannerProfile;
};

export default function PlannerWorkspace({ profile }: Props) {
  const plannerStage = usePlannerStore((s) => s.plannerStage);
  const setPlannerStage = usePlannerStore((s) => s.setPlannerStage);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const setSelectedTowerIndex = usePlannerStore((s) => s.setSelectedTowerIndex);
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const imageModel = usePlannerStore((s) => s.imageModel);
  const setImageModel = usePlannerStore((s) => s.setImageModel);

  const { data: plots = [] } = usePlotsQuery({
    tpScheme: locationPreference.tpId,
    city: locationPreference.districtName,
  });
  const { data: geometryModel = null } = usePlanGeometry(activeScenarioId);

  const {
    generatePlan,
    isGenerating,
    progress,
    stageLabel,
  } = useSitePlanGeneration();

  // If job completes before the status effect runs, still move to floor design once geometry exists.
  useEffect(() => {
    if (
      plannerStage === "plan-generating" &&
      geometryModel != null &&
      (geometryModel.features?.length ?? 0) > 0
    ) {
      setPlannerStage("floor-design");
    }
  }, [geometryModel, plannerStage, setPlannerStage]);

  // First tower selected by default so floor-plan AI can run without a site canvas step.
  useEffect(() => {
    if (plannerStage !== "floor-design") return;
    if (selectedTowerIndex !== null) return;
    if (!geometryModel?.features?.length) return;
    const towers = groupFeaturesByLayer(geometryModel).towerFootprints ?? [];
    if (towers.length > 0) {
      setSelectedTowerIndex(0);
    }
  }, [geometryModel, plannerStage, selectedTowerIndex, setSelectedTowerIndex]);

  const isHighRise = profile.mode === HIGH_RISE_MODE;
  const showComingSoon = !isHighRise;

  const handleBackToPlotInputs = useCallback(() => {
    setPlannerStage("input");
    setSelectedTowerIndex(null);
  }, [setPlannerStage, setSelectedTowerIndex]);

  const hasGeometry =
    geometryModel != null && geometryModel.features?.length > 0;

  return (
    <div className="flex h-screen w-full flex-col bg-white font-sans">
      <PlannerTopBar
        profileName={profile.name}
        isHighRise={isHighRise}
        stage={plannerStage}
        isGenerating={isGenerating}
        onGeneratePlan={generatePlan}
        imageModel={imageModel}
        onImageModelChange={setImageModel}
      />

      <main className="flex flex-col min-h-0 flex-1 overflow-hidden rounded-b-lg border border-neutral-100 bg-[#fbfbfb]">
        {plannerStage === "input" && (
          <>
            {showComingSoon ? (
              <div className="flex flex-1 min-h-0 w-full items-center justify-center border border-dashed border-neutral-200 bg-neutral-50/50">
                <div className="text-center">
                  <p className="text-sm font-medium text-neutral-600">Coming Soon</p>
                  <p className="mt-1 text-xs text-neutral-400">
                    Only high-rise residential site planning is available.
                  </p>
                </div>
              </div>
            ) : (
              /* Single stable layout — sidebar slides in when a plot is selected,
                 PlannerTpMap stays mounted to avoid destroying the MapLibre GL instance */
              <div className="flex flex-1 min-h-0 w-full">
                {selectedPlotId && (
                  <aside className="w-80 shrink-0 border-r border-neutral-200 bg-white overflow-y-auto">
                    <PlotInfoSidebar />
                  </aside>
                )}
                <div className="relative flex-1 min-h-0 bg-white">
                  <PlannerTpMap />
                </div>
              </div>
            )}
          </>
        )}

        {(plannerStage === "plan-generating" || plannerStage === "floor-design") && (
          <FloorCanvas
            geometryModel={geometryModel}
            onBackFromFloor={handleBackToPlotInputs}
            backFromFloorLabel="Plot & inputs"
            sitePlanPending={plannerStage === "plan-generating" || !hasGeometry}
          />
        )}
      </main>
    </div>
  );
}
