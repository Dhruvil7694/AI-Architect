"use client";

import type { ExplorationConstraints } from "@/services/plannerService";

interface Props {
  constraints: ExplorationConstraints | null;
  plotSummary: { areaSqm: number; roadWidthM: number; zone: string; authority: string; designation: string } | null;
  isLoading: boolean;
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex justify-between">
          <div className="h-4 w-24 rounded bg-neutral-200" />
          <div className="h-4 w-16 rounded bg-neutral-200" />
        </div>
      ))}
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-neutral-500">{label}</span>
      <span className={`text-xs font-semibold ${highlight ? "text-orange-600" : "text-neutral-900"}`}>
        {value}
      </span>
    </div>
  );
}

export function ConstraintsDashboard({ constraints, plotSummary, isLoading }: Props) {
  if (isLoading || !constraints || !plotSummary) return <Skeleton />;

  const c = constraints;
  const p = plotSummary;

  return (
    <div className="space-y-4">
      <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
        GDCR Constraints
      </h3>

      {/* Plot info */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row label="Plot Area" value={`${p.areaSqm.toFixed(0)} sqm (${(p.areaSqm / 0.8361).toFixed(0)} sq.yd)`} />
        <Row label="Approach Road" value={`${p.roadWidthM}m`} />
        <Row label="Zone" value={p.zone} />
        <Row label="Authority" value={p.authority} />
      </div>

      {/* Regulatory limits */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row label="Max Height" value={`${c.maxHeightM}m`} />
        <Row label="Max Floors" value={c.maxFloors} />
        <Row label="Max FSI" value={c.maxFSI} highlight />
        <Row label="Base FSI" value={c.baseFSI} />
        <Row label="Ground Cover" value={`${c.maxGroundCoverPct}%`} />
        <Row label="Max Towers" value={c.maxFeasibleTowers} />
      </div>

      {/* Corridor */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row
          label="Corridor Eligible"
          value={c.corridorEligible ? "Yes" : "No"}
          highlight={c.corridorEligible}
        />
        <p className="text-[10px] text-neutral-400 mt-1">{c.corridorReason}</p>
      </div>

      {/* Setbacks */}
      <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3 space-y-1">
        <Row label="Road Setback" value={`${c.setbacks.road}m`} />
        <Row label="Side Setback" value={`${c.setbacks.side}m`} />
        <Row label="Rear Setback" value={`${c.setbacks.rear}m`} />
      </div>

      {/* Premium tiers */}
      {c.premiumTiers.length > 0 && (
        <div className="rounded-lg border border-neutral-100 bg-neutral-50 p-3">
          <p className="text-[10px] font-semibold text-neutral-500 mb-2">Premium FSI Tiers</p>
          <div className="space-y-1">
            {c.premiumTiers.map((tier, i) => (
              <div key={i} className="flex justify-between text-[10px]">
                <span className="text-neutral-500">FSI {tier.fromFSI} → {tier.toFSI}</span>
                <span className="font-semibold text-neutral-700">{(tier.rate * 100).toFixed(0)}% premium</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
