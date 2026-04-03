"use client";

import { useMemo } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useFeasibility } from "../hooks/usePlannerData";
import type { FeasibilityResponse } from "@/services/plannerService";

const BUILDING_TYPES = [
  { id: 1 as const, label: "Low-Rise", sub: "≤15m" },
  { id: 2 as const, label: "Mid-Rise", sub: "≤30m" },
  { id: 3 as const, label: "High-Rise", sub: "45m+" },
];

const CORE_OPTIONS = [
  { value: 2 as const, label: "2" },
  { value: 4 as const, label: "4" },
  { value: 6 as const, label: "6" },
];

const SEGMENT_OPTIONS = [
  { value: "budget" as const, label: "Budget" },
  { value: "mid" as const, label: "Mid" },
  { value: "premium" as const, label: "Premium" },
  { value: "luxury" as const, label: "Luxury" },
];

const UNIT_OPTIONS = ["1BHK", "2BHK", "3BHK", "4BHK"] as const;

// ─── Pill button (reusable) ──────────────────────────────────────────────────

function Pill({
  selected,
  disabled,
  onClick,
  children,
}: {
  selected: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-lg px-3 py-2 text-xs font-medium transition-all ${
        disabled
          ? "cursor-not-allowed bg-neutral-50 text-neutral-300"
          : selected
            ? "bg-neutral-900 text-white shadow-sm"
            : "bg-neutral-50 text-neutral-600 hover:bg-neutral-100"
      }`}
    >
      {children}
    </button>
  );
}

// ─── Section wrapper ─────────────────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">{label}</p>
      {children}
    </div>
  );
}

// ─── Feasibility quick stats ─────────────────────────────────────────────────

function FeasibilityStrip({ data }: { data: FeasibilityResponse }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {[
        { label: "Plot", value: `${Math.round(data.plotAreaSqm)} m²` },
        { label: "Height", value: `${data.maxHeightM}m` },
        { label: "FSI", value: data.maxFSI.toFixed(2) },
        { label: "GC", value: `${data.maxGCPct}%` },
      ].map((item) => (
        <div key={item.label} className="text-center">
          <div className="text-[10px] text-neutral-400">{item.label}</div>
          <div className="text-xs font-semibold text-neutral-800">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export function DevelopmentInputs() {
  const inputs = usePlannerStore((state) => state.inputs);
  const setInputs = usePlannerStore((state) => state.setInputs);
  const selectedPlotId = usePlannerStore((state) => state.selectedPlotId);

  const { data: feasibility, isLoading: feasibilityLoading } =
    useFeasibility(selectedPlotId);

  const gdcrMaxFloors = useMemo(() => {
    if (!feasibility) return null;
    const btOption = feasibility.permissibleBuildingTypes?.find(
      (bt) => bt.id === inputs.buildingType,
    );
    return btOption?.effectiveMaxFloors ?? feasibility.maxFloors;
  }, [feasibility, inputs.buildingType]);

  if (!selectedPlotId) {
    return (
      <div className="flex items-center justify-center py-8 text-xs text-neutral-400">
        Select a plot to configure inputs
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Feasibility strip */}
      {feasibilityLoading && (
        <div className="flex items-center gap-2 py-3 text-xs text-neutral-400">
          <div className="h-3 w-3 animate-spin rounded-full border border-neutral-300 border-t-neutral-600" />
          Loading feasibility...
        </div>
      )}
      {feasibility && !feasibilityLoading && <FeasibilityStrip data={feasibility} />}

      <div className="h-px bg-neutral-100" />

      {/* Building Type */}
      <Section label="Building type">
        <div className="grid grid-cols-3 gap-2">
          {BUILDING_TYPES.map((bt) => {
            const permissible = feasibility?.permissibleBuildingTypes;
            const isDisabled = permissible ? !permissible.some((p) => p.id === bt.id) : false;
            return (
              <Pill
                key={bt.id}
                selected={inputs.buildingType === bt.id}
                disabled={isDisabled}
                onClick={() => setInputs({ buildingType: bt.id })}
              >
                <div>{bt.label}</div>
                <div className={`mt-0.5 text-[9px] ${inputs.buildingType === bt.id ? "text-neutral-300" : "text-neutral-400"}`}>
                  {bt.sub}
                </div>
              </Pill>
            );
          })}
        </div>
      </Section>

      {/* Floors */}
      <Section label="Floors">
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1}
            max={gdcrMaxFloors ?? 50}
            value={inputs.floors ?? ""}
            placeholder={gdcrMaxFloors ? `Auto (${gdcrMaxFloors})` : "Auto"}
            onChange={(e) => setInputs({ floors: e.target.value === "" ? null : Number(e.target.value) })}
            className="w-full rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-neutral-400 focus:bg-white focus:outline-none"
          />
          {inputs.floors !== null && (
            <button
              type="button"
              onClick={() => setInputs({ floors: null })}
              className="shrink-0 rounded-lg bg-neutral-50 px-3 py-2 text-xs text-neutral-500 hover:bg-neutral-100"
            >
              Reset
            </button>
          )}
        </div>
      </Section>

      {/* Units per Core */}
      <Section label="Units per core">
        <div className="flex gap-2">
          {CORE_OPTIONS.map((opt) => (
            <Pill
              key={opt.value}
              selected={inputs.unitsPerCore === opt.value}
              onClick={() => setInputs({ unitsPerCore: opt.value })}
            >
              {opt.label}
            </Pill>
          ))}
        </div>
      </Section>

      {/* Segment */}
      <Section label="Segment">
        <div className="flex flex-wrap gap-2">
          {SEGMENT_OPTIONS.map((opt) => (
            <Pill
              key={opt.value}
              selected={inputs.segment === opt.value}
              onClick={() => setInputs({ segment: opt.value })}
            >
              {opt.label}
            </Pill>
          ))}
        </div>
      </Section>

      {/* Unit Mix */}
      <Section label="Unit mix">
        <div className="flex flex-wrap gap-2">
          {UNIT_OPTIONS.map((label) => {
            const isChecked = inputs.unitMix.includes(label);
            return (
              <Pill
                key={label}
                selected={isChecked}
                onClick={() => {
                  const newMix = isChecked
                    ? inputs.unitMix.filter((u) => u !== label)
                    : [...inputs.unitMix, label];
                  setInputs({ unitMix: newMix });
                }}
              >
                {label}
              </Pill>
            );
          })}
        </div>
      </Section>

      {/* Sellable estimate */}
      {feasibility?.sellableEstimate && (
        <>
          <div className="h-px bg-neutral-100" />
          <div className="space-y-1.5 text-xs">
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400">Estimate</p>
            <div className="flex justify-between text-neutral-600">
              <span>Sellable/yard</span>
              <span className="font-medium text-neutral-800">{feasibility.sellableEstimate.sellablePerYard.toFixed(1)} sqft</span>
            </div>
            <div className="flex justify-between text-neutral-600">
              <span>Total sellable</span>
              <span className="font-medium text-neutral-800">{Math.round(feasibility.sellableEstimate.totalSellableSqft).toLocaleString()} sqft</span>
            </div>
            <div className="flex justify-between text-neutral-600">
              <span>Efficiency</span>
              <span className="font-medium text-neutral-800">{(feasibility.sellableEstimate.efficiencyRatio * 100).toFixed(1)}%</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
