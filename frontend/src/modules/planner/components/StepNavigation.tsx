"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { PlanningStep } from "@/state/plannerStore";

export function StepNavigation() {
  const planningStep = usePlannerStore((s) => s.planningStep);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);
  const selectedScenario = usePlannerStore((s) => s.selectedScenario);

  const steps: { id: PlanningStep; label: string }[] = [
    { id: "explore", label: "Plot Exploration" },
    { id: "site", label: "Site Plan" },
    { id: "floor", label: "AI Floor Plan" },
  ];

  return (
    <nav className="flex items-center gap-1" aria-label="Planning steps">
      {steps.map(({ id, label }, idx) => {
        const active = planningStep === id;
        const disabled =
          (id === "site" && selectedScenario === null) ||
          (id === "floor" && selectedTowerIndex === null);

        return (
          <div key={id} className="flex items-center">
            <button
              type="button"
              onClick={() => !disabled && setPlanningStep(id)}
              disabled={disabled}
              className={`group flex items-center gap-2 px-4 py-2 transition-all duration-300 ${
                active
                  ? "text-orange-600"
                  : disabled
                    ? "cursor-not-allowed opacity-30 text-neutral-400"
                    : "text-neutral-400 hover:text-neutral-900"
              }`}
            >
              <span className={`font-heading text-sm font-bold tracking-tight ${active ? "" : "font-medium"}`}>
                {label}
              </span>
              {active && (
                <div className="h-1.5 w-1.5 rounded-full bg-orange-600 shadow-[0_0_8px_rgba(234,88,12,0.6)] animate-pulse" />
              )}
            </button>
            {idx < steps.length - 1 && (
              <div className="h-4 w-px bg-neutral-100 mx-1" />
            )}
          </div>
        );
      })}
    </nav>
  );
}
