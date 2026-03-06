"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { PlanningStep } from "@/state/plannerStore";

export function StepNavigation() {
  const planningStep = usePlannerStore((s) => s.planningStep);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const selectedTowerIndex = usePlannerStore((s) => s.selectedTowerIndex);

  const steps: { id: PlanningStep; label: string }[] = [
    { id: "site", label: "Step 1 — Site Plan" },
    { id: "floor", label: "Step 2 — Floor Plan" },
  ];

  return (
    <nav className="flex items-center gap-1 rounded-md border border-neutral-200 bg-white p-0.5" aria-label="Planning steps">
      {steps.map(({ id, label }) => {
        const active = planningStep === id;
        const disabled = id === "floor" && selectedTowerIndex === null;
        return (
          <button
            key={id}
            type="button"
            onClick={() => !disabled && setPlanningStep(id)}
            disabled={disabled}
            className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "bg-neutral-900 text-white"
                : disabled
                  ? "cursor-not-allowed text-neutral-400"
                  : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
            }`}
          >
            {label}
          </button>
        );
      })}
    </nav>
  );
}
