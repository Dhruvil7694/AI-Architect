"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePlannerStore } from "@/state/plannerStore";
import { usePlanGeometry } from "@/modules/planner/hooks/usePlannerData";
import { FloorPlanningView } from "@/modules/planner/components/FloorPlanningView";
import { PlanningMetricsPanel } from "@/modules/planner/components/PlanningMetricsPanel";
import { UnitInspectionPanel } from "@/modules/planner/components/UnitInspectionPanel";

function FloorPlanContent() {
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const { data: geometryModel = null } = usePlanGeometry(activeScenarioId);

  return (
    <div className="flex min-h-[calc(100vh-5rem)] flex-col">
      <header className="flex shrink-0 items-center gap-4 border-b border-neutral-200 bg-white px-4 py-2">
        <Link
          href="/planner"
          className="rounded bg-neutral-100 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-200"
        >
          ← Site Plan
        </Link>
        <h1 className="text-lg font-semibold text-neutral-900">Floor Plan</h1>
      </header>
      <div className="flex min-h-0 flex-1 gap-4 p-4">
        <main className="min-h-0 flex-1">
          <FloorPlanningView geometryModel={geometryModel} />
        </main>
        <aside className="flex w-56 shrink-0 flex-col gap-4">
          <PlanningMetricsPanel />
          <UnitInspectionPanel />
        </aside>
      </div>
    </div>
  );
}

export default function FloorPlanPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center p-8 text-sm text-neutral-500">
          Loading…
        </div>
      }
    >
      <FloorPlanContent />
    </Suspense>
  );
}
