"use client";

import { useState, useMemo } from "react";
import { useSiteMetrics, useFeasibility } from "../hooks/usePlannerData";
import { usePlannerStore } from "@/state/plannerStore";
import {
  type AreaUnit,
  AREA_UNIT_LABELS,
  AREA_UNIT_SHORT,
  convertArea,
  formatArea,
} from "@/lib/units";

/** Compact unit toggle pill group. */
function UnitToggle({
  value,
  onChange,
}: {
  value: AreaUnit;
  onChange: (u: AreaUnit) => void;
}) {
  const units: AreaUnit[] = ["sqm", "sqft", "var"];
  return (
    <div className="flex rounded-lg border border-neutral-200 bg-neutral-50 p-0.5 text-[10px] font-semibold">
      {units.map((u) => (
        <button
          key={u}
          type="button"
          onClick={() => onChange(u)}
          className={`rounded-md px-2 py-1 transition-all ${
            value === u
              ? "bg-white text-neutral-900 shadow-sm"
              : "text-neutral-500 hover:text-neutral-700"
          }`}
        >
          {AREA_UNIT_SHORT[u]}
        </button>
      ))}
    </div>
  );
}

/** A single metric row in the sidebar. */
function MetricRow({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between py-1.5">
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="text-right">
        <span
          className={`text-sm font-semibold ${
            highlight ? "text-orange-600" : "text-neutral-900"
          }`}
        >
          {value}
        </span>
        {sub && (
          <span className="ml-1 text-[10px] text-neutral-400">{sub}</span>
        )}
      </dd>
    </div>
  );
}

/** Section header inside the sidebar. */
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mb-1 mt-4 text-[10px] font-bold uppercase tracking-widest text-neutral-400 first:mt-0">
      {children}
    </h4>
  );
}

export function PlotInfoSidebar() {
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const [unit, setUnit] = useState<AreaUnit>("sqft");

  const { data: metrics, isLoading: metricsLoading } =
    useSiteMetrics(selectedPlotId);
  const { data: feasibility, isLoading: feasLoading } =
    useFeasibility(selectedPlotId);

  const isLoading = metricsLoading || feasLoading;

  // Derive values
  const plotAreaSqm = metrics?.plotAreaSqm ?? feasibility?.plotAreaSqm ?? 0;
  const maxFSI = metrics?.maxFSI ?? feasibility?.maxFSI ?? 0;
  const maxBUA = metrics?.maxBUA ?? 0;
  const copAreaSqm = metrics?.copAreaSqm ?? 0;
  const copPct =
    plotAreaSqm > 0 ? ((copAreaSqm / plotAreaSqm) * 100).toFixed(1) : "0";
  const maxHeightM = feasibility?.maxHeightM ?? 0;
  const maxFloors = feasibility?.maxFloors ?? 0;
  const maxGCPct = feasibility?.maxGCPct ?? 0;
  const roadWidthM = feasibility?.roadWidthM ?? 0;
  const maxFeasibleTowers = feasibility?.maxFeasibleTowers ?? 0;

  // FSI breakdown
  const baseFSI = metrics?.baseFSI ?? 0;

  if (!selectedPlotId) return null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-bold text-neutral-900 tracking-tight">
            Plot Details
          </h3>
          <p className="text-[10px] text-neutral-500 font-mono mt-0.5">
            {selectedPlotId}
          </p>
        </div>
        <UnitToggle value={unit} onChange={setUnit} />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 scrollbar-hide">
        {isLoading ? (
          <div className="flex items-center gap-2 py-8 text-xs text-neutral-400">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-200 border-t-orange-500" />
            Loading parameters...
          </div>
        ) : (
          <dl className="divide-y divide-neutral-50">
            {/* Plot Area */}
            <SectionTitle>Plot Area</SectionTitle>
            <MetricRow
              label="Total Area"
              value={formatArea(plotAreaSqm, unit)}
              highlight
            />
            {/* Show all three units for quick reference */}
            <div className="rounded-lg bg-neutral-50 px-3 py-2 mb-2">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-[10px] text-neutral-400">sq.m</div>
                  <div className="text-xs font-bold text-neutral-800">
                    {Math.round(plotAreaSqm).toLocaleString("en-IN")}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-neutral-400">sq.ft</div>
                  <div className="text-xs font-bold text-neutral-800">
                    {Math.round(convertArea(plotAreaSqm, "sqft")).toLocaleString("en-IN")}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-neutral-400">VAR</div>
                  <div className="text-xs font-bold text-neutral-800">
                    {Math.round(convertArea(plotAreaSqm, "var")).toLocaleString("en-IN")}
                  </div>
                </div>
              </div>
            </div>

            {/* Regulatory Limits */}
            <SectionTitle>GDCR Permissible Limits</SectionTitle>
            <MetricRow
              label="Max FSI"
              value={maxFSI.toFixed(2)}
              sub={baseFSI > 0 && baseFSI !== maxFSI ? `(base ${baseFSI.toFixed(2)})` : undefined}
            />
            <MetricRow
              label="Max BUA"
              value={formatArea(maxBUA, unit)}
            />
            <MetricRow
              label="Max Ground Coverage"
              value={`${maxGCPct.toFixed(0)}%`}
            />

            {/* Height */}
            <SectionTitle>Height Regulation</SectionTitle>
            <MetricRow
              label="Max Height"
              value={`${maxHeightM} m`}
              sub={`(${Math.round(maxHeightM * 3.28084)} ft)`}
            />
            <MetricRow
              label="Max Floors"
              value={`${maxFloors}`}
              sub="@ 3.0m/floor"
            />
            <MetricRow
              label="Approach Road"
              value={`${roadWidthM} m`}
              sub="(MT)"
            />

            {/* Open Space */}
            <SectionTitle>Open Space (COP)</SectionTitle>
            <MetricRow
              label="Required COP"
              value={formatArea(copAreaSqm, unit)}
              sub={`(${copPct}%)`}
            />

            {/* Tower Feasibility */}
            <SectionTitle>Tower Feasibility</SectionTitle>
            <MetricRow
              label="Max Feasible Towers"
              value={`${maxFeasibleTowers}`}
            />
            {feasibility && feasibility.recommendedTowers > 0 && (
              <MetricRow
                label="Recommended"
                value={`${feasibility.recommendedTowers}T × ${feasibility.recommendedFloors}F`}
                highlight
              />
            )}

            {/* Per-tower options */}
            {feasibility &&
              feasibility.towerOptions.filter((t) => t.isFeasible).length >
                0 && (
                <div className="mt-2 space-y-1.5">
                  {feasibility.towerOptions
                    .filter((t) => t.isFeasible)
                    .map((t) => (
                      <div
                        key={t.nTowers}
                        className="flex items-center justify-between rounded-lg bg-emerald-50 px-3 py-1.5 text-xs"
                      >
                        <span className="font-medium text-emerald-800">
                          {t.nTowers} Tower{t.nTowers > 1 ? "s" : ""}
                        </span>
                        <span className="text-emerald-600">
                          {t.minFloors}-{t.maxFloors}F |{" "}
                          {formatArea(t.estimatedFootprintSqm, unit)}/tower
                        </span>
                      </div>
                    ))}
                </div>
              )}

            {/* Unit Type Compatibility */}
            {feasibility?.floorPlanCompat && (
              <>
                <SectionTitle>Unit Type Compatibility</SectionTitle>
                <div className="grid grid-cols-5 gap-1.5 mt-1">
                  {(
                    [
                      ["1BHK", feasibility.floorPlanCompat.canFit1bhk],
                      ["2BHK", feasibility.floorPlanCompat.canFit2bhk],
                      ["3BHK", feasibility.floorPlanCompat.canFit3bhk],
                      ["4BHK", feasibility.floorPlanCompat.canFit4bhk],
                      ["5BHK", feasibility.floorPlanCompat.canFit5bhk],
                    ] as [string, boolean][]
                  ).map(([label, fits]) => (
                    <div
                      key={label}
                      className={`rounded-md px-2 py-1.5 text-center text-[10px] font-bold ${
                        fits
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-red-50 text-red-400"
                      }`}
                    >
                      {label}
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Suggestions */}
            {feasibility &&
              feasibility.suggestions.length > 0 && (
                <>
                  <SectionTitle>AI Suggestions</SectionTitle>
                  <div className="space-y-1.5 mt-1">
                    {feasibility.suggestions.slice(0, 4).map((s, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-1.5 text-[11px] leading-relaxed text-neutral-600"
                      >
                        <span className="mt-0.5 text-orange-400 shrink-0">
                          *
                        </span>
                        <span>{s}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
          </dl>
        )}
      </div>
    </div>
  );
}
