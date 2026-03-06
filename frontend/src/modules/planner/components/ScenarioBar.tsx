"use client";

import { usePlannerStore } from "@/state/plannerStore";

export function ScenarioBar() {
  const scenarios = usePlannerStore((state) => state.scenarios);
  const activeScenarioId = usePlannerStore(
    (state) => state.activeScenarioId,
  );
  const setActiveScenarioId = usePlannerStore(
    (state) => state.setActiveScenarioId,
  );

  if (!scenarios.length) {
    return (
      <div className="rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-3 py-1 text-[11px] text-neutral-500">
        No scenarios yet. Generate a plan to create your first scenario.
      </div>
    );
  }

  return (
    <div className="inline-flex flex-wrap gap-2 rounded-md border border-neutral-200 bg-white px-3 py-1 text-[11px]">
      {scenarios.map((scenario) => {
        const isActive = scenario.id === activeScenarioId;
        return (
          <button
            key={scenario.id}
            type="button"
            onClick={() =>
              setActiveScenarioId(isActive ? null : scenario.id)
            }
            className={`rounded-full px-3 py-0.5 ${
              isActive
                ? "bg-neutral-900 text-neutral-50"
                : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
            }`}
          >
            {scenario.label ?? scenario.id}
          </button>
        );
      })}
    </div>
  );
}

