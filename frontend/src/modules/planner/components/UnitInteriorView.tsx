"use client";

import { useEffect, useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useUnitLayout } from "@/modules/planner/hooks/usePlannerData";
import type { UnitRoomFeature } from "@/services/plannerService";

// ─── Room colour palette ──────────────────────────────────────────────────────
const ROOM_STYLE: Record<string, { fill: string; stroke: string; text: string }> = {
  foyer:    { fill: "#f1f5f9", stroke: "#94a3b8", text: "#475569" },
  living:   { fill: "#fef3c7", stroke: "#d97706", text: "#92400e" },
  dining:   { fill: "#fde68a", stroke: "#ca8a04", text: "#78350f" },
  kitchen:  { fill: "#ffedd5", stroke: "#ea580c", text: "#7c2d12" },
  bedroom:  { fill: "#ede9fe", stroke: "#7c3aed", text: "#4c1d95" },
  bedroom2: { fill: "#f3e8ff", stroke: "#9333ea", text: "#581c87" },
  bathroom: { fill: "#dbeafe", stroke: "#3b82f6", text: "#1e3a8a" },
  toilet:   { fill: "#bfdbfe", stroke: "#2563eb", text: "#1e40af" },
  balcony:  { fill: "#dcfce7", stroke: "#16a34a", text: "#14532d" },
  utility:  { fill: "#f0fdf4", stroke: "#86efac", text: "#166534" },
};
const DEFAULT_STYLE = { fill: "#f8fafc", stroke: "#cbd5e1", text: "#334155" };

// ─── SVG room renderer ────────────────────────────────────────────────────────
function RoomSvg({
  features,
  unitW,
  unitD,
}: {
  features: UnitRoomFeature[];
  unitW: number;
  unitD: number;
}) {
  // Canvas viewport with padding
  const PAD   = 32;
  const VW    = 560;
  const VH    = 480;
  const scale = Math.min((VW - PAD * 2) / unitW, (VH - PAD * 2) / unitD);

  const tx = (x: number) => PAD + x * scale;
  const ty = (y: number) => PAD + y * scale;   // Y=0 at top = corridor side

  return (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      className="h-full w-full"
      style={{ maxHeight: "100%" }}
    >
      {/* Outer unit boundary */}
      <rect
        x={PAD} y={PAD}
        width={unitW * scale} height={unitD * scale}
        fill="none" stroke="#1e293b" strokeWidth={2}
      />

      {/* Entry door indicator on the corridor side (Y=0) */}
      <rect
        x={tx(unitW * 0.42)} y={ty(0) - 4}
        width={unitW * scale * 0.16} height={6}
        fill="#0ea5e9" rx={1}
      />
      <text
        x={tx(unitW * 0.50)} y={ty(0) - 7}
        textAnchor="middle" fontSize={9} fill="#0369a1" fontWeight="600"
      >
        ENTRY (Corridor)
      </text>

      {/* Exterior wall label */}
      <text
        x={tx(unitW * 0.50)} y={ty(unitD) + 14}
        textAnchor="middle" fontSize={9} fill="#64748b"
      >
        Exterior wall
      </text>

      {/* Rooms */}
      {features.map((f) => {
        const coords = f.geometry.coordinates[0];
        const xs = coords.map((c) => c[0]);
        const ys = coords.map((c) => c[1]);
        const x0 = Math.min(...xs), x1 = Math.max(...xs);
        const y0 = Math.min(...ys), y1 = Math.max(...ys);
        const rw = x1 - x0, rd = y1 - y0;
        const cx = tx(x0 + rw / 2), cy = ty(y0 + rd / 2);
        const p = f.properties;
        const style = ROOM_STYLE[p.room_type] ?? DEFAULT_STYLE;
        const pxW = rw * scale, pxH = rd * scale;

        return (
          <g key={f.id}>
            <rect
              x={tx(x0)} y={ty(y0)}
              width={pxW} height={pxH}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={1.5}
            />
            {/* GDCR non-compliance overlay */}
            {!p.gdcr_ok && (
              <rect
                x={tx(x0)} y={ty(y0)}
                width={pxW} height={pxH}
                fill="rgba(239,68,68,0.08)"
                stroke="#ef4444"
                strokeWidth={1}
                strokeDasharray="3 2"
              />
            )}
            {/* Room name */}
            {pxW > 40 && pxH > 28 && (
              <text
                x={cx} y={cy - (pxH > 48 ? 6 : 0)}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={Math.min(10, pxW / 6, pxH / 3.5)}
                fontWeight="600"
                fill={style.text}
                style={{ pointerEvents: "none" }}
              >
                {p.name}
              </text>
            )}
            {/* Area */}
            {pxW > 50 && pxH > 48 && (
              <text
                x={cx} y={cy + 9}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={Math.min(9, pxW / 7)}
                fill={style.text}
                opacity={0.75}
                style={{ pointerEvents: "none" }}
              >
                {p.area_sqm.toFixed(1)} m²
              </text>
            )}
            {/* GDCR fail indicator */}
            {!p.gdcr_ok && (
              <text
                x={tx(x0) + 4} y={ty(y0) + 11}
                fontSize={9} fill="#dc2626" fontWeight="700"
              >
                ✕
              </text>
            )}
          </g>
        );
      })}

      {/* Dimension annotations */}
      {/* Width arrow */}
      <line
        x1={tx(0)} y1={ty(unitD) + 22}
        x2={tx(unitW)} y2={ty(unitD) + 22}
        stroke="#475569" strokeWidth={1}
        markerEnd="url(#arr)" markerStart="url(#arr)"
      />
      <text
        x={tx(unitW / 2)} y={ty(unitD) + 33}
        textAnchor="middle" fontSize={9} fill="#475569"
      >
        {unitW.toFixed(1)} m
      </text>
      {/* Depth arrow */}
      <line
        x1={tx(unitW) + 22} y1={ty(0)}
        x2={tx(unitW) + 22} y2={ty(unitD)}
        stroke="#475569" strokeWidth={1}
        markerEnd="url(#arr)" markerStart="url(#arr)"
      />
      <text
        x={tx(unitW) + 34} y={ty(unitD / 2)}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={9} fill="#475569"
        transform={`rotate(90, ${tx(unitW) + 34}, ${ty(unitD / 2)})`}
      >
        {unitD.toFixed(1)} m
      </text>

      <defs>
        <marker id="arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#475569" />
        </marker>
      </defs>
    </svg>
  );
}

// ─── GDCR room compliance list ────────────────────────────────────────────────
function RoomList({
  rooms,
}: {
  rooms: Array<{
    name: string; type: string; area_sqm: number;
    width_m: number; depth_m: number;
    gdcr_ok: boolean; gdcr_ref: string;
  }>;
}) {
  return (
    <div className="space-y-1.5">
      {rooms.map((r) => {
        const style = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        return (
          <div
            key={r.name}
            className={`flex items-center gap-2 rounded px-2 py-1.5 ${
              r.gdcr_ok ? "bg-neutral-50" : "bg-red-50 border border-red-100"
            }`}
          >
            {/* Colour swatch */}
            <div
              className="h-3 w-3 flex-shrink-0 rounded-sm border"
              style={{ background: style.fill, borderColor: style.stroke }}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[11px] font-medium text-neutral-800 truncate">{r.name}</span>
                <span className="text-[11px] font-semibold text-neutral-700 flex-shrink-0">
                  {r.area_sqm.toFixed(1)} m²
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[9px] text-neutral-400">
                  {r.width_m.toFixed(1)} × {r.depth_m.toFixed(1)} m
                </span>
                <span className={`text-[9px] font-medium ${r.gdcr_ok ? "text-green-600" : "text-red-600"}`}>
                  {r.gdcr_ok ? `✓ ${r.gdcr_ref}` : `✕ ${r.gdcr_ref}`}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Main Stage 3 component ───────────────────────────────────────────────────
export function UnitInteriorView() {
  const selectedUnit    = usePlannerStore((s) => s.selectedUnit);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);
  const setSelectedUnit = usePlannerStore((s) => s.setSelectedUnit);

  const { mutate: requestLayout, data, isPending, isError, error } = useUnitLayout();

  // Auto-request layout when component mounts / unit changes
  useEffect(() => {
    if (!selectedUnit?.unitType) return;
    requestLayout({
      unit_type:    selectedUnit.unitType,
      unit_width_m: selectedUnit.unitWidthM  ?? 6.0,
      unit_depth_m: selectedUnit.unitDepthM  ?? 7.5,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUnit?.id]);

  const goBack = useCallback(() => {
    setPlanningStep("floor");
  }, [setPlanningStep]);

  // ── Guard: no unit selected ───────────────────────────────────────────────
  if (!selectedUnit) {
    return (
      <div className="flex h-full w-full items-center justify-center gap-4 rounded border border-dashed border-neutral-300 bg-neutral-50 p-8">
        <p className="text-sm text-neutral-500">No unit selected. Go back and click a unit.</p>
        <button type="button" onClick={goBack}
          className="rounded bg-neutral-200 px-3 py-1.5 text-sm font-medium text-neutral-800 hover:bg-neutral-300">
          Back to Floor Plan
        </button>
      </div>
    );
  }

  const TYPE_COLOR: Record<string, string> = {
    "4BHK": "bg-red-50 text-red-700 border-red-200",
    "3BHK": "bg-amber-50 text-amber-700 border-amber-200",
    "2BHK": "bg-green-50 text-green-700 border-green-200",
    "1BHK": "bg-sky-50 text-sky-700 border-sky-200",
    "STUDIO": "bg-purple-50 text-purple-700 border-purple-200",
    "1RK":  "bg-purple-50 text-purple-700 border-purple-200",
  };
  const typeCls = TYPE_COLOR[selectedUnit.unitType ?? ""] ?? "bg-neutral-50 text-neutral-700 border-neutral-200";

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* ── Left: SVG canvas ─────────────────────────────────────────────── */}
      <div className="relative flex flex-1 flex-col bg-white">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 border-b border-neutral-200 px-3 py-2">
          <button type="button" onClick={() => setPlanningStep("site")}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-100">
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Site Plan
          </button>
          <span className="text-neutral-300">/</span>
          <button type="button" onClick={goBack}
            className="rounded px-2 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100">
            Floor Plan
          </button>
          <span className="text-neutral-300">/</span>
          <span className="rounded-sm bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800">
            Unit Interior
          </span>
          <span className={`rounded border px-2 py-0.5 text-xs font-bold ${typeCls}`}>
            {selectedUnit.unitType}
          </span>
          <span className="text-xs text-neutral-500">{selectedUnit.id}</span>
        </div>

        {/* Canvas area */}
        <div className="relative flex flex-1 items-center justify-center p-4">
          {isPending && (
            <div className="flex flex-col items-center gap-3">
              <div className="h-7 w-7 animate-spin rounded-full border-2 border-neutral-300 border-t-sky-600" />
              <p className="text-xs text-neutral-500">Generating room layout…</p>
            </div>
          )}

          {isError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
              <p className="text-sm font-medium text-red-700">Layout generation failed</p>
              <p className="mt-1 text-xs text-red-600">{error?.message ?? "Unknown error"}</p>
              <button type="button"
                onClick={() => requestLayout({
                  unit_type: selectedUnit.unitType ?? "2BHK",
                  unit_width_m: selectedUnit.unitWidthM ?? 6.0,
                  unit_depth_m: selectedUnit.unitDepthM ?? 7.5,
                })}
                className="mt-2 rounded bg-red-100 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-200">
                Retry
              </button>
            </div>
          )}

          {data?.layout && !isPending && (
            <RoomSvg
              features={data.layout.features}
              unitW={data.unit_width_m}
              unitD={data.unit_depth_m}
            />
          )}
        </div>
      </div>

      {/* ── Right: room list + GDCR panel ────────────────────────────────── */}
      <div className="flex w-72 flex-shrink-0 flex-col overflow-hidden border-l border-neutral-200 bg-white">

        {/* Header */}
        <div className="border-b border-neutral-200 px-4 py-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-neutral-700">
            Unit Interior
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* Unit summary */}
          <section>
            <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
              Unit Summary
            </h3>
            <div className="space-y-1">
              {[
                ["Unit ID",          selectedUnit.id],
                ["Type",             selectedUnit.unitType ?? "—"],
                ["Width",            selectedUnit.unitWidthM ? `${selectedUnit.unitWidthM.toFixed(1)} m` : "—"],
                ["Depth",            selectedUnit.unitDepthM ? `${selectedUnit.unitDepthM.toFixed(1)} m` : "—"],
                ["Built-up area",    selectedUnit.builtUpArea ? `${selectedUnit.builtUpArea.toFixed(1)} m²` : "—"],
                ["Carpet area",      selectedUnit.carpetArea  ? `${selectedUnit.carpetArea.toFixed(1)} m²`  : "—"],
                ["RERA carpet",      selectedUnit.reraCarpet  ? `${selectedUnit.reraCarpet.toFixed(1)} m²`  : "—"],
              ].map(([k, v]) => (
                <div key={k as string} className="flex justify-between text-xs">
                  <span className="text-neutral-500">{k as string}</span>
                  <span className="font-medium text-neutral-800">{v as string}</span>
                </div>
              ))}
              {selectedUnit.efficiency != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-neutral-500">Efficiency</span>
                  <span className={`font-bold ${selectedUnit.efficiency >= 0.7 ? "text-green-700" : selectedUnit.efficiency >= 0.6 ? "text-amber-700" : "text-red-600"}`}>
                    {(selectedUnit.efficiency * 100).toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* GDCR compliance summary banner */}
          {data?.gdcr_summary && (
            <div className={`rounded-md p-2.5 text-xs ${
              data.gdcr_summary.all_ok
                ? "bg-green-50 border border-green-200 text-green-800"
                : "bg-red-50 border border-red-200 text-red-800"
            }`}>
              {data.gdcr_summary.all_ok
                ? "✓ All rooms comply with GDCR §13.1.8 / §13.1.9"
                : `✕ ${data.gdcr_summary.violations.length} room(s) below GDCR minimum`}
              {!data.gdcr_summary.all_ok && (
                <ul className="mt-1.5 space-y-0.5">
                  {data.gdcr_summary.violations.map((v, i) => (
                    <li key={i} className="text-[10px]">
                      <span className="font-semibold">{v.room}</span>: {v.issue} ({v.ref})
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Per-room list */}
          {data?.rooms && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
                Rooms ({data.rooms.length})
              </h3>
              <RoomList rooms={data.rooms} />
            </section>
          )}

          {/* Regulatory note */}
          <div className="rounded bg-amber-50 p-2 text-[9px] leading-relaxed text-amber-700">
            Room sizes checked against GDCR Part II §13.1.8 (Table 14.1 habitable rooms)
            and §13.1.9 (Table 14.2 bath/WC). Carpet areas per RERA 2016 §2(k).
          </div>

          {/* Back button */}
          <button type="button" onClick={goBack}
            className="w-full rounded-md border border-neutral-200 px-3 py-2 text-xs font-medium text-neutral-700 hover:bg-neutral-50">
            ← Back to Floor Plan
          </button>

        </div>
      </div>
    </div>
  );
}
