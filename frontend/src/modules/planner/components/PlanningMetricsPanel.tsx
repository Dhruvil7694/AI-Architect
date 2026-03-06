"use client";

import { usePlannerStore } from "@/state/plannerStore";

const SQFT_TO_SQM = 0.09290304;

export function PlanningMetricsPanel() {
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const scenarios = usePlannerStore((s) => s.scenarios);
  const scenario = scenarios.find((s) => s.id === activeScenarioId);
  const summary = (scenario?.planResultSummary as { metrics?: Record<string, unknown> }) ?? {};
  const m = summary.metrics ?? {};

  const safeNum = (x: unknown, fallback: number): number => {
    const n = Number(x);
    return Number.isFinite(n) ? n : fallback;
  };

  const plotAreaSqm = safeNum(m.plotAreaSqm, 0);
  const achievedFSI = safeNum((m as Record<string, unknown>).achievedFSI, NaN);
  const maxFSI = typeof m.maxFSI === "number" && Number.isFinite(m.maxFSI) ? m.maxFSI : safeNum(m.baseFSI, 0);
  const fsi = Number.isFinite(achievedFSI) ? achievedFSI : maxFSI;
  const achievedBUA = safeNum((m as Record<string, unknown>).achievedBUA, NaN);
  const maxBUA = safeNum(m.maxBUA, 0);
  const bua = Number.isFinite(achievedBUA) ? achievedBUA : maxBUA;
  const groundCoveragePct = typeof m.groundCoveragePct === "number" && Number.isFinite(m.groundCoveragePct) ? m.groundCoveragePct : 0;
  const copRequiredSqm = safeNum((m as Record<string, unknown>).copRequiredSqm, 0);
  const copProvidedSqm = safeNum((m as Record<string, unknown>).copProvidedSqm, 0);
  const copAreaSqm = Number.isFinite(copProvidedSqm) ? copProvidedSqm : safeNum(m.copAreaSqft, 0) * SQFT_TO_SQM;
  const nTowers = safeNum((m as Record<string, unknown>).nTowersPlaced, safeNum(m.nTowersRequested, 0));
  const floorCount = safeNum((m as Record<string, unknown>).floorCount, NaN);
  const buildingHeightM = safeNum((m as Record<string, unknown>).buildingHeightM, NaN);
  const floors = Number.isFinite(floorCount) ? floorCount : (Number.isFinite(buildingHeightM) ? buildingHeightM : undefined);
  const roadAccessOk = (m as Record<string, unknown>).roadAccessOk as boolean | undefined;

  if (!activeScenarioId) {
    return (
      <div className="rounded border border-neutral-200 bg-white p-3 text-xs text-neutral-500">
        Generate a scenario to see metrics.
      </div>
    );
  }

  const rows: { label: string; value: string | number }[] = [
    { label: "Plot Area", value: Number.isFinite(plotAreaSqm) ? `${Math.round(plotAreaSqm)} m²` : "—" },
    { label: "FSI", value: Number.isFinite(fsi) ? fsi.toFixed(2) : "—" },
    { label: "BUA", value: Number.isFinite(bua) && bua > 0 ? `${Math.round(bua)} m²` : "—" },
    { label: "Ground Coverage", value: Number.isFinite(groundCoveragePct) ? `${groundCoveragePct.toFixed(1)}%` : "—" },
    { label: "COP Required", value: Number.isFinite(copRequiredSqm) ? `${Math.round(copRequiredSqm)} m²` : "—" },
    { label: "COP Provided", value: Number.isFinite(copProvidedSqm) ? `${Math.round(copProvidedSqm)} m²` : (Number.isFinite(copAreaSqm) ? `${Math.round(copAreaSqm)} m²` : "—") },
    { label: "Calculated Height (m)", value: Number.isFinite(buildingHeightM) ? buildingHeightM.toFixed(1) : "—" },
    { label: "Number of Towers", value: Number.isFinite(nTowers) ? nTowers : "—" },
    { label: "Floors", value: floors != null && Number.isFinite(floors) ? floors : "—" },
    ...(typeof roadAccessOk === "boolean" ? [{ label: "Road Access", value: roadAccessOk ? "OK" : "Fail" as const }] : []),
  ];

  return (
    <div className="flex flex-col gap-2 rounded border border-neutral-200 bg-white p-3 shadow-sm">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-600">
        Planning metrics
      </h3>
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
