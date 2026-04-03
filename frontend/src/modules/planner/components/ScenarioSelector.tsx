"use client";

import { useMemo } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { ScenarioCard } from "@/modules/planner/components/ScenarioCard";

export function ScenarioSelector() {
  const scenarios = usePlannerStore((s) => s.scenarios);
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const setActiveScenarioId = usePlannerStore((s) => s.setActiveScenarioId);

  const ordered = useMemo(() => {
    return scenarios;
  }, [scenarios]);

  if (!ordered.length) {
    return null;
  }

  return (
    <div className="flex items-center justify-between pb-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Scenarios
        </span>
        <span className="text-[10px] text-neutral-400">
          Compare alternative layout options
        </span>
      </div>
      <div className="flex flex-1 justify-end">
        <div className="flex max-w-full gap-2 overflow-x-auto pb-1">
          {ordered.map((scenario, idx) => {
            const summary = (scenario.planResultSummary as {
              metrics?: Record<string, unknown>;
            })?.metrics as Record<string, unknown> | undefined;

            const fsi =
              (summary?.achievedFSI as number | undefined) ??
              (summary?.achievedFSINet as number | undefined) ??
              null;
            const floors =
              (summary?.floorCount as number | undefined) ??
              (summary?.nTowersRequested as number | undefined) ??
              null;
            const openSpacePct =
              (summary?.achievedGCPct as number | undefined) ?? null;
            const copAreaSqm =
              (summary?.copAreaSqft as number | undefined) != null
                ? (summary?.copAreaSqft as number) * 0.09290304
                : null;

            const isActive = scenario.id === activeScenarioId;
            const title = scenario.label ?? `Option ${String.fromCharCode(65 + idx)}`;

            return (
              <ScenarioCard
                key={scenario.id}
                title={title}
                fsi={typeof fsi === "number" ? fsi : null}
                floors={typeof floors === "number" ? floors : null}
                openSpacePct={typeof openSpacePct === "number" ? openSpacePct : null}
                copAreaSqm={typeof copAreaSqm === "number" ? copAreaSqm : null}
                selected={isActive}
                onClick={() => setActiveScenarioId(scenario.id)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

