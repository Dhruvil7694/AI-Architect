"use client";

import { Suspense, useEffect } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import FloorPlanPage from "@/app/(protected)/planner/floor/page";

function FloorPlansWrapper() {
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);

  useEffect(() => {
    setPlanningStep("floor");
  }, [setPlanningStep]);

  return <FloorPlanPage />;
}

export default function FloorPlansPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center p-8 text-sm text-neutral-500">
          Loading floor plans…
        </div>
      }
    >
      <FloorPlansWrapper />
    </Suspense>
  );
}

