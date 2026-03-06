"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { SelectedUnitInfo } from "@/state/plannerStore";

export function UnitInspectionPanel() {
  const selectedUnit = usePlannerStore((s) => s.selectedUnit);
  const setSelectedUnit = usePlannerStore((s) => s.setSelectedUnit);

  if (!selectedUnit) {
    return (
      <div className="rounded border border-neutral-200 bg-white p-3 text-xs text-neutral-500">
        Click a unit on the floor plan to inspect.
      </div>
    );
  }

  const rows: { label: string; value: string | number }[] = [
    { label: "Unit type", value: selectedUnit.unitType ?? "—" },
    { label: "Carpet area", value: selectedUnit.carpetArea != null ? `${selectedUnit.carpetArea} m²` : "—" },
    { label: "Built-up area", value: selectedUnit.builtUpArea != null ? `${selectedUnit.builtUpArea} m²` : "—" },
    { label: "RERA carpet", value: selectedUnit.reraCarpet != null ? `${selectedUnit.reraCarpet} m²` : "—" },
    { label: "Efficiency", value: selectedUnit.efficiency != null ? `${(selectedUnit.efficiency * 100).toFixed(1)}%` : "—" },
  ];

  return (
    <div className="flex flex-col gap-2 rounded border border-neutral-200 bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-600">
          Unit
        </h3>
        <button
          type="button"
          onClick={() => setSelectedUnit(null)}
          className="rounded p-0.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
          aria-label="Close"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <dl className="grid gap-1 text-sm">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex justify-between gap-2">
            <dt className="text-neutral-600">{label}</dt>
            <dd className="font-medium text-neutral-900">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
