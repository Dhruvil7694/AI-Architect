"use client";

import { usePlannerStore } from "@/state/plannerStore";
import type { SelectedUnitInfo } from "@/state/plannerStore";

export function UnitInspectionPanel() {
  const selectedUnit = usePlannerStore((s) => s.selectedUnit);
  const setSelectedUnit = usePlannerStore((s) => s.setSelectedUnit);

  if (!selectedUnit) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-neutral-200 bg-white p-6 text-center shadow-sm">
        <svg className="h-8 w-8 text-neutral-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 2.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
        </svg>
        <p className="text-sm font-medium text-neutral-500">Select a unit on the floor plan to inspect</p>
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
    <div className="flex flex-col gap-4 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm font-sans">
      <div className="flex items-center justify-between border-b border-neutral-100 pb-2">
        <h3 className="text-sm font-semibold text-neutral-900">
          Unit Inspection
        </h3>
        <button
          type="button"
          onClick={() => setSelectedUnit(null)}
          className="rounded-full p-1.5 text-neutral-400 transition-colors hover:bg-neutral-100 hover:text-neutral-700"
          aria-label="Close"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <dl className="flex flex-col gap-1.5">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex justify-between items-baseline py-1 group">
            <dt className="text-[13px] text-neutral-500 group-hover:text-neutral-700 transition-colors">{label}</dt>
            <dd className="text-[13px] font-medium text-neutral-900 tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
