"use client";

import { Suspense } from "react";
import { UnitInteriorView } from "@/modules/planner/components/UnitInteriorView";

export default function FlatDesignerPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center p-8 text-sm text-neutral-500">
          Loading flat designer…
        </div>
      }
    >
      <UnitInteriorView />
    </Suspense>
  );
}

