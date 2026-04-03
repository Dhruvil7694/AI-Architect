"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PlotDropdown } from "@/modules/planner/components/PlotDropdown";
import { SiteMetricsSummary } from "@/modules/planner/components/SiteMetricsSummary";
import { DevelopmentInputs } from "@/modules/planner/components/DevelopmentInputs";
import { usePlannerStore } from "@/state/plannerStore";

/** Inner component that safely uses useSearchParams inside a Suspense boundary */
function SearchParamSync() {
  const searchParams = useSearchParams();
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);

  useEffect(() => {
    const plotId = searchParams.get("plotId");
    if (plotId) setSelectedPlotId(plotId);
  }, [searchParams, setSelectedPlotId]);

  return null;
}

export default function PlannerInputsPage() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 pb-10">
      <Suspense fallback={null}>
        <SearchParamSync />
      </Suspense>

      {/* Stepper */}
      <section className="rounded-3xl border border-neutral-200/70 bg-[#f6f2e8] px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral-500">
            <span className="rounded-full bg-neutral-900 px-3 py-1 text-white">1 · Inputs</span>
            <span className="rounded-full bg-white/60 px-3 py-1 text-neutral-700">2 · Site plan</span>
            <span className="rounded-full bg-white/40 px-3 py-1 text-neutral-500">3 · Floor plans</span>
            <span className="rounded-full bg-white/30 px-3 py-1 text-neutral-500">4 · Flats</span>
          </div>
          <div className="text-[11px] text-neutral-500">
            Start with basic plot + GDCR inputs. You can refine everything later.
          </div>
        </div>
      </section>

      {/* Main card */}
      <section className="grid gap-6 rounded-3xl border border-neutral-200/70 bg-white/90 p-5 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        {/* Inputs column */}
        <div className="space-y-4">
          <header className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral-500">
              Step 1
            </p>
            <h1 className="text-xl font-semibold tracking-tight text-neutral-900">
              Plot inputs &amp; controls
            </h1>
            <p className="text-sm text-neutral-600">
              Choose a plot, set development controls, and review the key capacity numbers
              before generating a site plan.
            </p>
          </header>

          <div className="flex flex-col gap-3 rounded-2xl bg-[#f6f2e8] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-neutral-700">Selected plot</span>
              <PlotDropdown />
            </div>
          </div>

          <div className="rounded-2xl border border-neutral-200/80 bg-white/80 p-3">
            <DevelopmentInputs />
          </div>
        </div>

        {/* Metrics + next CTA */}
        <div className="flex flex-col justify-between gap-4 rounded-2xl bg-[#f6f2e8] p-4">
          <div className="space-y-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-neutral-600">
                Capacity at a glance
              </p>
              <p className="mt-1 text-sm text-neutral-700">
                Live metrics for the current plot and controls.
              </p>
            </div>
            <div className="rounded-2xl border border-neutral-200 bg-white/90 p-3">
              <SiteMetricsSummary />
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-2 border-t border-neutral-200 pt-3">
            <Link
              href="/planner/site-plan"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-neutral-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-neutral-800"
            >
              Generate site plan
              <ArrowRight className="h-4 w-4" />
            </Link>
            <p className="text-xs text-neutral-500">
              This will open a full planner canvas for envelopes, roads, towers, and spacing.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
