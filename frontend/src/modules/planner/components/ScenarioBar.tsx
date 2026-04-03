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
      <div className="flex items-center gap-2 rounded-xl border border-dashed border-neutral-300 bg-neutral-50 px-4 py-2 text-xs font-medium text-neutral-500">
        <svg className="h-4 w-4 text-neutral-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
        </svg>
        No scenarios yet. Generate a plan to create your first scenario.
      </div>
    );
  }

  return (
    <div className="flex w-full items-center gap-4 py-1">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
        Scenarios
      </span>
      <div className="flex flex-wrap gap-2">
        {scenarios.map((scenario) => {
          const isActive = scenario.id === activeScenarioId;
          return (
            <button
              key={scenario.id}
              type="button"
              onClick={() =>
                setActiveScenarioId(isActive ? null : scenario.id)
              }
              className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-all duration-300 ${
                isActive
                  ? "bg-orange-500 text-white shadow-md shadow-orange-500/20 ring-2 ring-orange-500 ring-offset-2"
                  : "bg-neutral-100 text-neutral-600 hover:bg-orange-50 hover:text-orange-600"
              }`}
            >
              {scenario.label ?? scenario.id}
            </button>
          );
        })}
      </div>
    </div>
  );
}
