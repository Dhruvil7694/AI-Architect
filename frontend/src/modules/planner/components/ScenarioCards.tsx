"use client";

import { useState, useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import type { ExplorationScenario, ExplorationConstraints } from "@/services/plannerService";

interface Props {
  scenarios: ExplorationScenario[];
  constraints: ExplorationConstraints | null;
  unitCompatibility: Record<string, boolean>;
  isLoading: boolean;
  onProceed: (scenario: ExplorationScenario) => void;
}

function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border border-neutral-200 p-4 space-y-3">
      <div className="h-5 w-32 rounded bg-neutral-200" />
      <div className="h-3 w-48 rounded bg-neutral-100" />
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-8 rounded bg-neutral-100" />
        ))}
      </div>
    </div>
  );
}

function MetricBox({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md bg-neutral-50 px-2 py-1.5 text-center">
      <div className="text-xs font-bold text-neutral-900">{value}</div>
      <div className="text-[10px] text-neutral-400">{label}</div>
    </div>
  );
}

const SEGMENT_OPTIONS = ["budget", "mid", "premium", "luxury"];
const UNITS_PER_CORE_OPTIONS = [2, 4, 6];
const UNIT_TYPES = ["1BHK", "2BHK", "3BHK", "4BHK"];

export function ScenarioCards({ scenarios, constraints, unitCompatibility, isLoading, onProceed }: Props) {
  const selectedScenario = usePlannerStore((s) => s.selectedScenario);
  const setSelectedScenario = usePlannerStore((s) => s.setSelectedScenario);

  const [editedScenario, setEditedScenario] = useState<ExplorationScenario | null>(null);

  const handleSelect = useCallback((scenario: ExplorationScenario) => {
    setSelectedScenario(scenario);
    setEditedScenario({ ...scenario });
  }, [setSelectedScenario]);

  const handleEdit = useCallback((field: string, value: unknown) => {
    setEditedScenario((prev) => prev ? { ...prev, [field]: value } : null);
  }, []);

  const handleProceed = useCallback(() => {
    if (editedScenario) {
      setSelectedScenario(editedScenario);
      onProceed(editedScenario);
    }
  }, [editedScenario, setSelectedScenario, onProceed]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
          Generating Scenarios...
        </h3>
        {Array.from({ length: 3 }).map((_, i) => <CardSkeleton key={i} />)}
      </div>
    );
  }

  if (!scenarios.length) return null;

  const isSelected = (s: ExplorationScenario) => selectedScenario?.id === s.id;

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
        Development Scenarios
      </h3>

      {scenarios.map((scenario) => (
        <button
          key={scenario.id}
          type="button"
          onClick={() => handleSelect(scenario)}
          className={`w-full text-left rounded-xl border-2 p-4 transition-all ${
            isSelected(scenario)
              ? "border-orange-500 bg-orange-50/50 shadow-md"
              : "border-neutral-200 bg-white hover:border-neutral-300 hover:shadow-sm"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-bold text-neutral-900">{scenario.label}</h4>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
              scenario.id === "high_density" ? "bg-red-100 text-red-700" :
              scenario.id === "balanced" ? "bg-blue-100 text-blue-700" :
              "bg-purple-100 text-purple-700"
            }`}>
              {scenario.segment}
            </span>
          </div>
          <p className="text-xs text-neutral-500 mb-3">{scenario.description}</p>

          <div className="grid grid-cols-3 gap-1.5">
            <MetricBox label="Towers" value={scenario.towers} />
            <MetricBox label="Floors" value={scenario.floors} />
            <MetricBox label="Est. FSI" value={scenario.estimatedFSI.toFixed(1)} />
            <MetricBox label="Sellable" value={`${(scenario.estimatedSellableAreaSqm / 1000).toFixed(1)}k sqm`} />
            <MetricBox label="Units" value={scenario.estimatedTotalUnits} />
            <MetricBox label="Sell/yd" value={scenario.sellablePerSqYd.toFixed(0)} />
          </div>

          <p className="text-[10px] italic text-neutral-400 mt-2">{scenario.tradeoffNote}</p>
        </button>
      ))}

      {/* Parameter Editor — shown when a scenario is selected */}
      {editedScenario && (
        <div className="rounded-xl border border-orange-200 bg-orange-50/30 p-4 space-y-3">
          <h4 className="text-xs font-bold text-neutral-700">Customize Parameters</h4>

          <div className="grid grid-cols-2 gap-3">
            {/* Towers */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Towers</label>
              <input
                type="number"
                min={1}
                max={constraints?.maxFeasibleTowers ?? 10}
                value={editedScenario.towers}
                onChange={(e) => handleEdit("towers", parseInt(e.target.value) || 1)}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              />
            </div>

            {/* Floors */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Floors</label>
              <input
                type="number"
                min={1}
                max={constraints?.maxFloors ?? 30}
                value={editedScenario.floors}
                onChange={(e) => handleEdit("floors", parseInt(e.target.value) || 1)}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              />
            </div>

            {/* Segment */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Segment</label>
              <select
                value={editedScenario.segment}
                onChange={(e) => handleEdit("segment", e.target.value)}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              >
                {SEGMENT_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            </div>

            {/* Units per core */}
            <div>
              <label className="text-[10px] font-medium text-neutral-500">Units / Core</label>
              <select
                value={editedScenario.unitsPerCore}
                onChange={(e) => handleEdit("unitsPerCore", parseInt(e.target.value))}
                className="mt-0.5 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs"
              >
                {UNITS_PER_CORE_OPTIONS.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Unit mix checkboxes */}
          <div>
            <label className="text-[10px] font-medium text-neutral-500">Unit Mix</label>
            <div className="mt-1 flex flex-wrap gap-2">
              {UNIT_TYPES.map((ut) => {
                const compatible = unitCompatibility[ut] !== false;
                const checked = editedScenario.unitMix.includes(ut);
                return (
                  <label
                    key={ut}
                    className={`flex items-center gap-1 text-xs ${!compatible ? "opacity-40" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!compatible}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...editedScenario.unitMix, ut]
                          : editedScenario.unitMix.filter((u) => u !== ut);
                        handleEdit("unitMix", next);
                      }}
                      className="rounded border-neutral-300"
                    />
                    {ut}
                  </label>
                );
              })}
            </div>
          </div>

          {/* Proceed button */}
          <button
            type="button"
            onClick={handleProceed}
            className="w-full rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-orange-700 transition-colors"
          >
            Proceed to Site Plan →
          </button>
        </div>
      )}
    </div>
  );
}
