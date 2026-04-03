"use client";

import { useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { usePlotExploration } from "@/modules/planner/hooks/usePlannerData";
import { ConstraintsDashboard } from "./ConstraintsDashboard";
import { ScenarioCards } from "./ScenarioCards";
import type { ExplorationScenario } from "@/services/plannerService";
import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { WholeTpMap } from "@/modules/plots/components/WholeTpMap";

export function PlotExplorationView() {
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const setInputs = usePlannerStore((s) => s.setInputs);

  const { data: exploration, isLoading, error } = usePlotExploration(selectedPlotId);
  const { data: plots = [] } = usePlotsQuery({
    tpScheme: locationPreference.tpId,
    city: locationPreference.districtName,
  });

  const handleProceed = useCallback((scenario: ExplorationScenario) => {
    setInputs({
      buildingType: scenario.buildingType,
      floors: scenario.floors,
      segment: scenario.segment,
      unitsPerCore: scenario.unitsPerCore,
      nBuildings: scenario.towers,
      unitMix: scenario.unitMix,
    });
    setPlanningStep("site");
  }, [setInputs, setPlanningStep]);

  return (
    <div className="flex h-full gap-3">
      {/* Left panel: TP Map */}
      <div className="flex-[3] min-h-0 rounded-xl border border-neutral-200 bg-white overflow-hidden">
        {plots.length > 0 ? (
          <WholeTpMap
            plots={plots}
            width={800}
            height={600}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-neutral-400">
            Loading map...
          </div>
        )}
      </div>

      {/* Right panel: Constraints + Scenarios */}
      <div className="flex-[2] min-h-0 overflow-auto space-y-4 pr-1">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load plot analysis. {(error as Error).message}
          </div>
        ) : (
          <>
            <ConstraintsDashboard
              constraints={exploration?.constraints ?? null}
              plotSummary={exploration?.plotSummary ?? null}
              isLoading={isLoading}
            />
            <ScenarioCards
              scenarios={exploration?.scenarios ?? []}
              constraints={exploration?.constraints ?? null}
              unitCompatibility={exploration?.unitCompatibility ?? {}}
              isLoading={isLoading}
              onProceed={handleProceed}
            />
          </>
        )}
      </div>
    </div>
  );
}
