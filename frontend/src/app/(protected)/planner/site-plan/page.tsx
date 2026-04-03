"use client";

import { Suspense, useEffect } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import PlannerPage from "@/app/(protected)/planner/page";

function SitePlanWrapper() {
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);

  useEffect(() => {
    setPlanningStep("site");
  }, [setPlanningStep]);

  return <PlannerPage />;
}

export default function SitePlanPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center p-8 text-sm text-neutral-500">
          Loading site plan…
        </div>
      }
    >
      <SitePlanWrapper />
    </Suspense>
  );
}

