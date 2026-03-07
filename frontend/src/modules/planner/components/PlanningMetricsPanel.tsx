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
        ? "bg-blue-500"
        : "bg-amber-400";
  return (
    <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-neutral-100">
      <div
        className={`h-full rounded-full ${color} transition-all duration-500`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-1">
      <dt className="shrink-0 text-neutral-500">{label}</dt>
      <dd className="text-right font-medium text-neutral-900 tabular-nums">
        {value}
      </dd>
    </div>
  );
}

function UtilRow({ label, pct }: { label: string; pct: number }) {
  return (
    <div>
      <div className="flex justify-between">
        <span className="text-neutral-500">{label}</span>
        <span className="font-medium tabular-nums text-neutral-900">
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
    <div className="flex flex-col gap-1.5">
      <h4
        className={`border-b pb-0.5 text-[10px] font-semibold uppercase tracking-widest ${titleClass ?? "text-neutral-500"} ${borderClass ?? "border-neutral-200"}`}
      >
        {title}
      </h4>
      <dl className="flex flex-col gap-1">{children}</dl>
    </div>
  );
}

// ── Skeleton row ────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="flex items-baseline justify-between gap-1">
      <div className="h-2.5 w-16 animate-pulse rounded bg-neutral-200" />
      <div className="h-2.5 w-10 animate-pulse rounded bg-neutral-200" />
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
      <div className="rounded border border-neutral-200 bg-white p-3 text-xs text-neutral-500">
        Generate a scenario to see metrics.
      </div>
    );
  }

  // Mirror page.tsx: show skeleton until we actually have metrics, not just until
  // the job status says "completed" — the geometry query may still be in flight.
  const hasMetrics = Object.keys(m).length > 0;
  const isLoading = !hasMetrics && jobStatus?.status !== "failed";

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 rounded border border-neutral-200 bg-white p-3 text-xs shadow-sm">
        <h3 className="text-[10px] font-semibold uppercase tracking-wide text-neutral-600">
          Planning metrics
        </h3>
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 pb-0.5">
            <div className="h-3 w-3 animate-spin rounded-full border border-neutral-400 border-t-transparent" />
            <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400">
              Computing…
            </span>
          </div>
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
        <div className="flex flex-col gap-2">
          <div className="h-2 w-20 animate-pulse rounded bg-neutral-200" />
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (jobStatus?.status === "failed") {
    return (
      <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700">
        <p className="font-medium">Plan generation failed</p>
        {jobStatus.errorMessage && (
          <p className="mt-1 text-red-600">{jobStatus.errorMessage}</p>
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

  return (
    <div className="flex flex-col gap-3 rounded border border-neutral-200 bg-white p-3 text-xs shadow-sm">
      <h3 className="text-[10px] font-semibold uppercase tracking-wide text-neutral-600">
        Planning metrics
      </h3>

      {/* ① Regulatory Limits */}
      <Section title="Regulatory Limits">
        <Row
          label="Plot Area"
          value={plotAreaSqm !== null ? `${Math.round(plotAreaSqm)} m²` : "—"}
        />
        <Row label="Road Width"  value={v(roadWidthM, " m")} />
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
        titleClass="text-blue-700"
        borderClass="border-blue-100"
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
          <p className="text-neutral-400">Awaiting plan result…</p>
        )}
      </Section>
    </div>
  );
}
