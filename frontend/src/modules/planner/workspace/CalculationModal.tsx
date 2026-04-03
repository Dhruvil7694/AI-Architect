"use client";

import { usePlannerStore } from "@/state/plannerStore";

type CalculationModalProps = {
  open: boolean;
  onClose: () => void;
};

// ---------------------------------------------------------------------------
// Client-side GDCR / NBC derived calculations
// ---------------------------------------------------------------------------

/** Parking requirement: ~1 ECS per 100 sqm BUA (GDCR residential). */
function computeParking(achievedBUA: number | null): string {
  if (!achievedBUA) return "—";
  return `${Math.ceil(achievedBUA / 100)} ECS`;
}

/** Fire compliance tier (NBC/GDCR). */
function computeFireCompliance(heightM: number | null): string {
  if (heightM === null) return "—";
  if (heightM > 45) return "High-rise Special (>45 m)";
  if (heightM > 15) return "High-rise NOC required";
  return "Standard (≤ 15 m)";
}

/** Staircase requirement (NBC Table 4, high-rise provisions). */
function computeStaircase(heightM: number | null, floors: number | null): string {
  if (heightM === null && floors === null) return "—";
  const h = heightM ?? 0;
  const f = floors ?? 0;
  const count = h > 15 || f > 5 ? 2 : 1;
  return `${count} × min 1.2 m wide`;
}

/** Lift core requirement (NBC: required if height > 10 m). */
function computeLiftCore(heightM: number | null, footprintSqm: number | null): string {
  if (heightM === null) return "—";
  if (heightM <= 10) return "Not required (≤ 10 m)";
  // NBC: 1 lift per 2 000 sqm floor area; min 1
  const floorArea = footprintSqm ?? 0;
  const lifts = floorArea > 0 ? Math.max(1, Math.ceil(floorArea / 2000)) : 1;
  return `${lifts} lift${lifts > 1 ? "s" : ""} required`;
}

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex justify-between border-b border-neutral-100 py-2 text-sm">
      <span className="text-neutral-500">{label}</span>
      <span className={`font-medium tabular-nums ${highlight ? "text-orange-700" : "text-neutral-900"}`}>
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CalculationModal({ open, onClose }: CalculationModalProps) {
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const scenarios = usePlannerStore((s) => s.scenarios);

  const scenario = scenarios.find((s) => s.id === activeScenarioId);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const m = ((scenario?.planResultSummary as any)?.metrics ?? {}) as Record<string, unknown>;

  const n = (key: string): number | null => {
    const val = Number(m[key]);
    return Number.isFinite(val) && val !== 0 ? val : null;
  };
  const fmt = (v: number | null, unit = "", dp = 0) =>
    v !== null ? `${v.toFixed(dp)} ${unit}`.trim() : "—";

  const plotArea   = n("plotAreaSqm");
  const achievedFSI = n("achievedFSI");
  const maxFSI     = n("maxFSI");
  const achievedBUA = n("achievedBUA");
  const maxBUA     = n("maxBUA");
  const gcPct      = n("achievedGCPct") ?? n("groundCoveragePct");
  const heightM    = n("buildingHeightM");
  const floors     = n("floorCount");
  const nTowers    = n("nTowersPlaced");
  const footprint  = n("totalFootprintSqm");
  const copProvided = n("copProvidedSqm");
  const copRequired = n("copRequiredSqm");
  const roadAccess = m["roadAccessOk"];

  const hasData = Object.keys(m).length > 0;

  if (!open) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-neutral-900/20 backdrop-blur-sm"
        aria-hidden
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="calculation-modal-title"
        className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-neutral-200 bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="calculation-modal-title" className="text-lg font-semibold text-neutral-900">
            Calculations
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-800"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {!hasData ? (
          <p className="py-6 text-center text-sm text-neutral-400">
            Generate a plan to see calculations.
          </p>
        ) : (
          <div className="space-y-1">
            {/* Site */}
            <p className="pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-neutral-400">Site</p>
            <Row label="Plot area" value={plotArea !== null ? `${Math.round(plotArea).toLocaleString()} m²` : "—"} />
            <Row label="Ground coverage" value={gcPct !== null ? `${gcPct.toFixed(1)}% (limit 40%)` : "—"} highlight={gcPct !== null && gcPct > 40} />
            <Row label="COP provided" value={copProvided !== null ? `${Math.round(copProvided)} m²` : "—"} />
            <Row label="COP required" value={copRequired !== null ? `${Math.round(copRequired)} m²` : "—"} />
            <Row label="Road access" value={roadAccess === true ? "✓ Compliant" : roadAccess === false ? "✗ Non-compliant" : "—"} highlight={roadAccess === false} />

            {/* FSI / BUA */}
            <p className="pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-neutral-400">FSI & Built-up Area</p>
            <Row label="FSI achieved" value={achievedFSI !== null ? achievedFSI.toFixed(3) : "—"} />
            <Row label="Max FSI (GDCR)" value={maxFSI !== null ? maxFSI.toFixed(2) : "—"} />
            <Row label="Built-up area" value={achievedBUA !== null ? `${Math.round(achievedBUA).toLocaleString()} m²` : "—"} />
            <Row label="Max BUA" value={maxBUA !== null ? `${Math.round(maxBUA).toLocaleString()} m²` : "—"} />

            {/* Towers */}
            <p className="pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-neutral-400">Towers</p>
            <Row label="Towers placed" value={nTowers !== null ? String(Math.round(nTowers)) : "—"} />
            <Row label="Floors" value={floors !== null ? String(Math.round(floors)) : "—"} />
            <Row label="Building height" value={fmt(heightM, "m", 1)} />
            <Row label="Total footprint" value={footprint !== null ? `${Math.round(footprint)} m²` : "—"} />

            {/* Code requirements */}
            <p className="pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-neutral-400">Code Requirements (NBC / GDCR)</p>
            <Row label="Parking requirement" value={computeParking(achievedBUA)} />
            <Row label="Fire compliance" value={computeFireCompliance(heightM)} highlight={heightM !== null && heightM > 15} />
            <Row label="Staircase" value={computeStaircase(heightM, floors)} />
            <Row label="Lift core" value={computeLiftCore(heightM, footprint)} />
          </div>
        )}
      </div>
    </>
  );
}
