"use client";

import { usePlannerStore } from "@/state/plannerStore";
import { usePlanJobStatus } from "@/modules/planner/hooks/usePlannerData";

/** GDCR Table 6.22 — max ground coverage for DW3 is always 40 %. */
const GC_LIMIT_PCT = 40;

// ── Sub-components ─────────────────────────────────────────────────────────────

function UtilBar({ pct }: { pct: number }) {
  const clamped = Math.min(100, Math.max(0, pct));
  const color =
    clamped >= 90
      ? "bg-emerald-500"
      : clamped >= 60
        ? "bg-orange-400"
        : "bg-amber-400";
  return (
    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
      <div
        className={`h-full rounded-full ${color} transition-all duration-500`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1">
      <dt className="shrink-0 text-[13px] text-neutral-500">{label}</dt>
      <dd className="text-right text-[13px] font-medium text-neutral-900 tabular-nums">
        {value}
      </dd>
    </div>
  );
}

function UtilRow({ label, pct }: { label: string; pct: number }) {
  return (
    <div className="py-1">
      <div className="flex justify-between items-baseline">
        <span className="text-[13px] text-neutral-500">{label}</span>
        <span className="text-[13px] font-medium tabular-nums text-neutral-900">
          {pct.toFixed(1)}%
        </span>
      </div>
      <UtilBar pct={pct} />
    </div>
  );
}

function Section({
  title,
  titleClass,
  borderClass,
  children,
}: {
  title: string;
  titleClass?: string;
  borderClass?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  children: any;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h4
        className={`border-b pb-1.5 text-xs font-semibold uppercase tracking-wider ${titleClass ?? "text-neutral-500"} ${borderClass ?? "border-neutral-100"}`}
      >
        {title}
      </h4>
      <dl className="flex flex-col">{children}</dl>
    </div>
  );
}

// ── Skeleton row ────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="flex items-baseline justify-between gap-1 py-1">
      <div className="h-3 w-16 animate-pulse rounded-md bg-neutral-100" />
      <div className="h-3 w-10 animate-pulse rounded-md bg-neutral-100" />
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export function PlanningMetricsPanel() {
  const activeScenarioId = usePlannerStore((s) => s.activeScenarioId);
  const scenarios = usePlannerStore((s) => s.scenarios);
  const { data: jobStatus } = usePlanJobStatus(activeScenarioId);

  const scenario = scenarios.find((s) => s.id === activeScenarioId);
  const summary =
    (scenario?.planResultSummary as { metrics?: Record<string, unknown> }) ??
    {};
  const m = (summary.metrics ?? {}) as Record<string, unknown>;

  if (!activeScenarioId) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-neutral-200 bg-white p-6 text-center shadow-sm">
        <svg className="h-8 w-8 text-neutral-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <p className="text-sm font-medium text-neutral-500">Generate a scenario to see metrics</p>
      </div>
    );
  }

  // Mirror page.tsx: show skeleton until we actually have metrics, not just until
  // the job status says "completed" — the geometry query may still be in flight.
  const hasMetrics = Object.keys(m).length > 0;
  const isLoading = !hasMetrics && jobStatus?.status !== "failed";

  if (isLoading) {
    return (
      <div className="flex flex-col gap-5 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-neutral-900 border-b border-neutral-100 pb-2">
          Planning Metrics
        </h3>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 pb-2">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
            <span className="text-xs font-semibold uppercase tracking-wider text-orange-600">
              Computing...
            </span>
          </div>
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonRow key={`top-${i}`} />
          ))}
        </div>
        <div className="flex flex-col gap-1 pt-2 border-t border-neutral-50">
          <div className="h-2.5 w-24 animate-pulse rounded bg-neutral-100 mb-2" />
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonRow key={`bot-${i}`} />
          ))}
        </div>
      </div>
    );
  }

  if (jobStatus?.status === "failed") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 shadow-sm">
        <div className="flex items-center gap-2 font-semibold">
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
             <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Plan Generation Failed
        </div>
        {jobStatus.errorMessage && (
          <p className="mt-2 text-red-600 text-xs">{jobStatus.errorMessage}</p>
        )}
      </div>
    );
  }

  /** Parse a metric field to a finite number, or null if absent / non-finite. */
  const n = (key: string): number | null => {
    const val = Number(m[key]);
    return Number.isFinite(val) ? val : null;
  };

  /** Format a nullable number with optional suffix and decimal places. */
  const v = (x: number | null, suffix = "", places = 0): string =>
    x !== null ? x.toFixed(places) + suffix : "—";

  // ── 1. Regulatory limits (from backend, not recomputed) ────────────────────
  const plotAreaSqm = n("plotAreaSqm");
  const roadWidthM  = n("roadWidthM");
  const maxFSI      = n("maxFSI");
  const maxBUA      = n("maxBUA");
  const gdcrMaxH    = n("gdcrMaxHeightM");

  // ── 2. Achieved development (from solver result) ───────────────────────────
  const nTowers      = n("nTowersPlaced");
  const floorCount   = n("floorCount");
  const heightM      = n("buildingHeightM");
  const footprintSqm = n("totalFootprintSqm");
  const achievedBUA  = n("achievedBUA");
  const achievedFSI  = n("achievedFSI");
  // prefer new field; fall back to legacy groundCoveragePct
  const gcPct = n("achievedGCPct") ?? n("groundCoveragePct");

  // ── 3. Utilization ratios (computed in UI, never from backend) ─────────────
  const fsiUtil =
    achievedFSI !== null && maxFSI !== null && maxFSI > 0
      ? (achievedFSI / maxFSI) * 100
      : null;
  const gcUtil  = gcPct !== null ? (gcPct / GC_LIMIT_PCT) * 100 : null;
  const htUtil  =
    heightM !== null && gdcrMaxH !== null && gdcrMaxH > 0
      ? (heightM / gdcrMaxH) * 100
      : null;

  const hasUtil = fsiUtil !== null || gcUtil !== null || htUtil !== null;

  const generationSource = (metrics.generationSource as string) || null;

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-neutral-200 bg-white p-4 font-sans shadow-sm">
      <div className="flex items-center justify-between border-b border-neutral-100 pb-2">
        <h3 className="text-sm font-semibold text-neutral-900">
          Planning Metrics
        </h3>
        {generationSource && (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              generationSource === "ai"
                ? "bg-violet-100 text-violet-700"
                : "bg-neutral-100 text-neutral-600"
            }`}
          >
            {generationSource === "ai" ? (
              <>
                <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 1a1 1 0 0 1 1 1v2.07A5.001 5.001 0 0 1 13 9a5 5 0 0 1-10 0 5.001 5.001 0 0 1 4-4.93V2a1 1 0 0 1 1-1zm0 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" />
                </svg>
                AI-Generated
              </>
            ) : (
              "Algorithmic"
            )}
          </span>
        )}
      </div>

      {/* ① Regulatory Limits */}
      <Section title="Regulatory Limits">
        <Row
          label="Plot Area"
          value={plotAreaSqm !== null ? `${Math.round(plotAreaSqm)} m²` : "—"}
        />
        <Row label="Approach Road"  value={v(roadWidthM, " m")} />
        <Row label="Max FSI"     value={v(maxFSI, "", 1)} />
        <Row
          label="Max BUA"
          value={maxBUA !== null ? `${Math.round(maxBUA)} m²` : "—"}
        />
        <Row label="Max Height"  value={v(gdcrMaxH, " m")} />
        <Row label="GC Limit"    value="40 %" />
      </Section>

      {/* ② Achieved Plan */}
      <Section
        title="Achieved Plan"
        titleClass="text-orange-700"
        borderClass="border-orange-100"
      >
        <Row label="Towers"       value={v(nTowers)} />
        <Row label="Floors"       value={v(floorCount)} />
        <Row label="Height"       value={v(heightM, " m", 1)} />
        <Row
          label="Footprint"
          value={footprintSqm !== null ? `${Math.round(footprintSqm)} m²` : "—"}
        />
        <Row
          label="BUA"
          value={achievedBUA !== null ? `${Math.round(achievedBUA)} m²` : "—"}
        />
        <Row label="FSI"          value={v(achievedFSI, "", 2)} />
        <Row label="Ground Cover" value={v(gcPct, "%", 1)} />
      </Section>

      {/* ③ Utilization */}
      <Section
        title="Utilization"
        titleClass="text-emerald-700"
        borderClass="border-emerald-100"
      >
        {fsiUtil !== null && <UtilRow label="FSI"    pct={fsiUtil} />}
        {gcUtil  !== null && <UtilRow label="GC"     pct={gcUtil}  />}
        {htUtil  !== null && <UtilRow label="Height" pct={htUtil}  />}
        {!hasUtil && (
          <p className="text-xs text-neutral-400 mt-2">Awaiting plan result…</p>
        )}
      </Section>

      {/* ④ Sellable Area */}
      {m.sellableSummary && (() => {
        const ss = m.sellableSummary as Record<string, unknown>;
        const sn = (key: string): number | null => {
          const val = Number(ss[key]);
          return Number.isFinite(val) ? val : null;
        };
        const totalSellable = sn("totalSellableSqft");
        const sellablePerYard = sn("sellablePerYard");
        const avgRca = sn("estimatedRcaPerFlatSqft");
        const efficiency = sn("efficiencyRatio");
        const segment = ss.segment as string | undefined;

        return (
          <Section
            title="Sellable Area"
            titleClass="text-blue-700"
            borderClass="border-blue-100"
          >
            <Row
              label="Total Sellable"
              value={totalSellable !== null ? `${Math.round(totalSellable).toLocaleString()} sqft` : "—"}
            />
            <Row
              label="Sellable/Yard"
              value={sellablePerYard !== null ? `${sellablePerYard.toFixed(1)} sqft` : "—"}
            />
            <Row
              label="Avg RCA/Flat"
              value={avgRca !== null ? `${Math.round(avgRca).toLocaleString()} sqft` : "—"}
            />
            {efficiency !== null && (
              <UtilRow label="Efficiency" pct={efficiency * 100} />
            )}
            {segment && (
              <Row label="Segment" value={segment.charAt(0).toUpperCase() + segment.slice(1)} />
            )}
          </Section>
        );
      })()}
    </div>
  );
}
