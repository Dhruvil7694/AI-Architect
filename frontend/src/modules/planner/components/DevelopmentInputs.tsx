"use client";

import { useMemo } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useFeasibility } from "../hooks/usePlannerData";
import type { FeasibilityResponse } from "@/services/plannerService";

const BUILDING_TYPES = [
  { id: 1 as const, label: "Low-Rise", description: "Up to 15m / 5 floors" },
  { id: 2 as const, label: "Mid-Rise", description: "Up to 30m / 10 floors" },
  { id: 3 as const, label: "High-Rise", description: "Up to 45m+ / 15 floors" },
];

const CORE_OPTIONS = [
  { value: 2 as const, label: "2 Units/Core" },
  { value: 4 as const, label: "4 Units/Core" },
  { value: 6 as const, label: "6 Units/Core" },
];

const SEGMENT_OPTIONS = [
  { value: "budget" as const, label: "Budget" },
  { value: "mid" as const, label: "Mid" },
  { value: "premium" as const, label: "Premium" },
  { value: "luxury" as const, label: "Luxury" },
];

const UNIT_OPTIONS = ["1BHK", "2BHK", "3BHK", "4BHK", "5BHK"] as const;

function FeasibilityPanel({ data }: { data: FeasibilityResponse }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-white/10 px-2 py-2">
          <div className="text-xs font-medium text-white/60">Height Cap</div>
          <div className="text-sm font-bold text-white">{data.maxHeightM}m</div>
          <div className="text-xs text-white/50">{data.maxFloors} floors</div>
        </div>
        <div className="rounded-lg bg-white/10 px-2 py-2">
          <div className="text-xs font-medium text-white/60">Max FSI</div>
          <div className="text-sm font-bold text-white">{data.maxFSI.toFixed(2)}</div>
        </div>
        <div className="rounded-lg bg-white/10 px-2 py-2">
          <div className="text-xs font-medium text-white/60">Max Towers</div>
          <div className="text-sm font-bold text-white">{data.maxFeasibleTowers}</div>
        </div>
      </div>

      {data.recommendationReason && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
          <div className="text-xs font-semibold text-emerald-300 uppercase tracking-wide">
            Recommended
          </div>
          <div className="mt-1 text-sm text-white/90">{data.recommendationReason}</div>
        </div>
      )}

      {data.suggestions.length > 0 && (
        <div className="space-y-1.5">
          {data.suggestions.slice(0, 3).map((s, i) => (
            <div
              key={i}
              className="flex items-start gap-2 rounded-lg bg-white/5 px-3 py-2 text-xs text-white/80 leading-relaxed"
            >
              <span className="mt-0.5 text-orange-400 shrink-0">*</span>
              <span>{s}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SellableEstimatePanel({ data }: { data: FeasibilityResponse }) {
  const est = data.sellableEstimate;
  if (!est) return null;

  return (
    <div className="rounded-lg bg-white/10 px-3 py-2 space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-white/60">Sellable/Yard</span>
        <span className="font-medium text-white">{est.sellablePerYard.toFixed(1)} sqft</span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-white/60">Total Sellable</span>
        <span className="font-medium text-white">{Math.round(est.totalSellableSqft).toLocaleString()} sqft</span>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-white/60">Efficiency</span>
        <span className="font-medium text-white">{(est.efficiencyRatio * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}

export function DevelopmentInputs() {
  const inputs = usePlannerStore((state) => state.inputs);
  const setInputs = usePlannerStore((state) => state.setInputs);
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);

  const { data: feasibility, isLoading: feasibilityLoading } =
    useFeasibility(selectedPlotId);

  // Resolve max floors from feasibility + building type
  const gdcrMaxFloors = useMemo(() => {
    if (!feasibility) return null;
    const btOption = feasibility.permissibleBuildingTypes?.find(
      (bt) => bt.id === inputs.buildingType,
    );
    return btOption?.effectiveMaxFloors ?? feasibility.maxFloors;
  }, [feasibility, inputs.buildingType]);

  // Build the tower count options capped at maxFeasibleTowers
  const maxTowers = feasibility?.maxFeasibleTowers ?? 4;
  const towerCountOptions = useMemo(() => {
    const opts: { value: number | null; label: string }[] = [
      { value: null, label: `Auto${feasibility?.recommendedTowers ? ` (${feasibility.recommendedTowers}T recommended)` : ""}` },
    ];
    for (let i = 1; i <= maxTowers; i++) {
      opts.push({ value: i, label: `${i} Building${i > 1 ? "s" : ""}` });
    }
    return opts;
  }, [maxTowers, feasibility?.recommendedTowers]);

  return (
    <div className="space-y-8 font-sans text-white">
      {/* Feasibility summary */}
      {feasibilityLoading && selectedPlotId && (
        <div className="rounded-xl border border-white/15 bg-white/5 p-4">
          <div className="flex items-center gap-2 text-sm text-white/60">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Analyzing plot feasibility...
          </div>
        </div>
      )}

      {feasibility && !feasibilityLoading && (
        <section className="space-y-3">
          <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2 flex items-center justify-between">
            <span>Plot Feasibility</span>
            <span className="text-xs font-medium text-emerald-400 bg-emerald-500/15 px-2.5 py-1 rounded-full">
              AI Analyzed
            </span>
          </h3>
          <FeasibilityPanel data={feasibility} />
        </section>
      )}

      {/* 1. Building Type */}
      <section className="space-y-4">
        <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2">
          Building Type
        </h3>
        <div className="grid grid-cols-3 gap-3">
          {BUILDING_TYPES.map((bt) => {
            const isSelected = inputs.buildingType === bt.id;
            const permissible = feasibility?.permissibleBuildingTypes;
            const isDisabled = permissible
              ? !permissible.some((p) => p.id === bt.id)
              : false;

            return (
              <button
                key={bt.id}
                type="button"
                disabled={isDisabled}
                onClick={() => setInputs({ buildingType: bt.id })}
                className={`rounded-xl border p-3 text-center transition-all
                  ${isDisabled
                    ? "cursor-not-allowed border-white/10 bg-white/5 opacity-40"
                    : isSelected
                      ? "border-white/50 bg-white/20 ring-1 ring-white/40"
                      : "cursor-pointer border-white/25 bg-white/10 hover:bg-white/15"
                  }`}
              >
                <div className={`text-sm font-semibold ${isSelected ? "text-white" : "text-white/80"}`}>
                  {bt.label}
                </div>
                <div className="text-[10px] text-white/50 mt-1">{bt.description}</div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 2. Floors */}
      <section className="space-y-4">
        <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2 flex items-center justify-between">
          <span>Floors</span>
          {gdcrMaxFloors !== null && (
            <span className="text-xs font-medium text-white/60 bg-white/15 px-2.5 py-1 rounded-full">
              GDCR max: {gdcrMaxFloors}
            </span>
          )}
        </h3>
        <div className="flex items-center gap-3">
          <input
            type="number"
            min={1}
            max={gdcrMaxFloors ?? 50}
            value={inputs.floors ?? ""}
            placeholder="Auto (GDCR max)"
            onChange={(e) => {
              const val = e.target.value === "" ? null : Number(e.target.value);
              setInputs({ floors: val });
            }}
            className="w-full rounded-xl border border-white/25 bg-white/10 px-4 py-3 text-base font-medium text-white shadow-sm transition-all focus:border-white/50 focus:outline-none focus:ring-2 focus:ring-white/30 placeholder:text-white/40"
          />
          {inputs.floors !== null && (
            <button
              type="button"
              onClick={() => setInputs({ floors: null })}
              className="shrink-0 rounded-lg border border-white/20 bg-white/10 px-3 py-2.5 text-xs font-medium text-white/70 hover:bg-white/15 transition-all"
            >
              Auto
            </button>
          )}
        </div>
      </section>

      {/* 3. Core (Units per Core) */}
      <section className="space-y-4">
        <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2">
          Core Configuration
        </h3>
        <div className="grid grid-cols-3 gap-3">
          {CORE_OPTIONS.map((opt) => {
            const isSelected = inputs.unitsPerCore === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setInputs({ unitsPerCore: opt.value })}
                className={`rounded-xl border p-3 text-center transition-all
                  ${isSelected
                    ? "border-white/50 bg-white/20 ring-1 ring-white/40"
                    : "cursor-pointer border-white/25 bg-white/10 hover:bg-white/15"
                  }`}
              >
                <div className={`text-sm font-semibold ${isSelected ? "text-white" : "text-white/80"}`}>
                  {opt.label}
                </div>
              </button>
            );
          })}
        </div>
        {feasibility?.coreConfigs && feasibility.coreConfigs.length > 0 && (
          <div className="text-xs text-white/50 mt-1">
            Recommended: {feasibility.coreConfigs[0].label} ({feasibility.coreConfigs[0].preferredPattern})
          </div>
        )}
      </section>

      {/* 4. Number of Buildings */}
      <section className="space-y-4">
        <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2">
          Number of Buildings
        </h3>
        <div className="relative">
          <select
            value={inputs.nBuildings === null ? "auto" : String(inputs.nBuildings)}
            onChange={(e) => {
              const val = e.target.value === "auto" ? null : Number(e.target.value);
              setInputs({ nBuildings: val });
            }}
            className="w-full appearance-none rounded-xl border border-white/25 bg-white/10 px-4 py-3.5 text-base font-semibold text-white shadow-sm transition-all focus:border-white/50 focus:outline-none focus:ring-2 focus:ring-white/30"
          >
            {towerCountOptions.map((opt) => (
              <option
                key={opt.value ?? "auto"}
                value={opt.value === null ? "auto" : String(opt.value)}
                className="bg-neutral-800 text-white"
              >
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-white/60">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </section>

      {/* 5. Sellable Area / Segment */}
      <section className="space-y-4">
        <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2">
          Segment &amp; Sellable Area
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {SEGMENT_OPTIONS.map((opt) => {
            const isSelected = inputs.segment === opt.value;
            return (
              <label
                key={opt.value}
                className={`group relative flex cursor-pointer rounded-xl border p-4 shadow-sm transition-all
                  ${isSelected
                    ? "border-white/50 bg-white/20 ring-1 ring-white/40"
                    : "border-white/25 bg-white/10 hover:bg-white/15"
                  }`}
              >
                <div className="flex w-full items-center justify-between gap-3">
                  <span className={`text-base font-semibold capitalize ${isSelected ? "text-white" : "text-white/80"}`}>
                    {opt.label}
                  </span>
                  <input
                    type="radio"
                    name="segment"
                    value={opt.value}
                    checked={isSelected}
                    onChange={() => setInputs({ segment: opt.value })}
                    className="h-5 w-5 border-white/40 bg-white/10 text-orange-600 focus:ring-white/30"
                  />
                </div>
              </label>
            );
          })}
        </div>

        {/* Sellable estimate (read-only) */}
        {feasibility && <SellableEstimatePanel data={feasibility} />}
      </section>

      {/* Unit Mix */}
      <section className="space-y-4">
        <h3 className="text-base font-bold uppercase tracking-wide text-white/95 border-b border-white/20 pb-2">
          Unit Mix
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {UNIT_OPTIONS.map((label) => {
            const isChecked = inputs.unitMix.includes(label);
            return (
              <label
                key={label}
                className={`group relative flex cursor-pointer rounded-xl border p-4 shadow-sm transition-all
                  ${isChecked
                    ? "border-white/50 bg-white/20 ring-1 ring-white/40"
                    : "border-white/25 bg-white/10 hover:bg-white/15"
                  }`}
              >
                <div className="flex w-full items-center justify-between gap-3">
                  <span className={`text-base font-semibold ${isChecked ? "text-white" : "text-white/80"}`}>
                    {label}
                  </span>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => {
                      const newMix = isChecked
                        ? inputs.unitMix.filter((u) => u !== label)
                        : [...inputs.unitMix, label];
                      setInputs({ unitMix: newMix });
                    }}
                    className="h-5 w-5 rounded border-white/40 bg-white/10 text-orange-600 focus:ring-white/30"
                  />
                </div>
              </label>
            );
          })}
        </div>
      </section>
    </div>
  );
}
