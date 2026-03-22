"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { MiniPlotPreview } from "@/modules/plots/components/MiniPlotPreview";
import { TpMapPicker } from "@/modules/plots/components/TpMapPicker";
import { usePlannerStore } from "@/state/plannerStore";
import type { GeoJsonInput } from "@/geometry/geometryNormalizer";

export default function PlotsPage() {
  const router = useRouter();
  const { data, isLoading, isError } = usePlotsQuery();

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold text-neutral-900">Plots</h2>
        <p className="text-sm text-neutral-500">
          Browse available plots with basic metrics and mini geometry previews.
        </p>
      </header>

      <div className="rounded-md border border-neutral-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-medium text-neutral-700">
          Whole TP overview
        </h3>
        <TpMapPicker
          tpScheme="TP14"
          onPlotSelect={(id) => router.push(`/planner?plotId=${encodeURIComponent(id)}`)}
        />
      </div>

      <div className="rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-600">
        {isLoading && (
          <p className="text-xs text-neutral-500">Loading plots…</p>
        )}
        {isError && (
          <p className="text-xs text-red-600">
            Unable to load plots. Please try again.
          </p>
        )}
        {!isLoading && !isError && (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {data?.map((plot) => (
              <article
                key={plot.id}
                className="flex flex-col justify-between gap-2 rounded-md border border-neutral-200 bg-neutral-50 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-medium text-neutral-900">
                      {plot.name}
                    </h3>
                    <p className="mt-0.5 text-[11px] text-neutral-500">
                      Area: {Math.round(plot.areaSqm)} m²
                    </p>
                    {plot.roadWidthM !== undefined && (
                      <p className="text-[11px] text-neutral-500">
                        Road: {plot.roadWidthM} m
                      </p>
                    )}
                    {plot.designation && (
                      <p className="mt-0.5 rounded bg-amber-50 px-1 text-[10px] text-amber-800">
                        {plot.designation}
                      </p>
                    )}
                  </div>
                </div>
                {plot.geometry ? (
                  <MiniPlotPreview geometry={plot.geometry as GeoJsonInput} />
                ) : (
                  <MiniPlotPreview plotId={plot.id} />
                )}
                <Link
                  href={`/planner?plotId=${encodeURIComponent(plot.id)}`}
                  onClick={() => usePlannerStore.getState().setSelectedPlotId(plot.id)}
                  className="mt-2 block w-full rounded border border-neutral-300 bg-white py-1.5 text-center text-xs font-medium text-neutral-700 hover:bg-neutral-50"
                >
                  Open in planner →
                </Link>
              </article>
            ))}
            {!data?.length && (
              <p className="text-xs text-neutral-500">No plots available.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

