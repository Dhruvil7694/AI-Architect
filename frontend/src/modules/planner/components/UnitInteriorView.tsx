"use client";

import { useEffect, useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useUnitLayout } from "@/modules/planner/hooks/usePlannerData";
import type { UnitRoomData, UnitFurnitureItem } from "@/services/plannerService";

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
  studio:   { fill: "#ede9fe", stroke: "#7c3aed", text: "#4c1d95" },
};
const DEFAULT_STYLE = { fill: "#f8fafc", stroke: "#cbd5e1", text: "#334155" };

// Furniture fill colours
const FURNITURE_FILL: Record<string, string> = {
  bed_queen:      "#c7d2fe",
  bed_single:     "#c7d2fe",
  wardrobe:       "#a5b4fc",
  sofa:           "#fde68a",
  coffee_table:   "#fef3c7",
  dining_table:   "#fed7aa",
  kitchen_counter:"#fca5a5",
  wc:             "#93c5fd",
  basin:          "#bae6fd",
  shower:         "#e0f2fe",
  bathtub:        "#bae6fd",
};
const FURN_DEFAULT = "#e2e8f0";

// ─── Architectural SVG drawing ────────────────────────────────────────────────
function ArchitecturalPlan({
  rooms,
  unitW,
  unitD,
}: {
  rooms: UnitRoomData[];
  unitW: number;
  unitD: number;
}) {
  const PAD  = 56;   // canvas padding for dimensions + labels
  const VW   = 780;
  const VH   = 600;
  const scale = Math.min((VW - PAD * 2) / unitW, (VH - PAD * 2) / unitD);
  const EW   = 6;    // external wall stroke px (~230 mm)
  const IW   = 3;    // internal wall stroke px (~115 mm)
  const TOL  = 0.05; // boundary tolerance in metres

  const tx = (x: number) => PAD + x * scale;
  const ty = (y: number) => PAD + y * scale;  // Y=0 = corridor (top of SVG)

  // Whether a room edge touches the unit boundary
  const onSouth = (r: UnitRoomData) => r.y        <= TOL;
  const onNorth = (r: UnitRoomData) => r.y + r.h  >= unitD - TOL;
  const onWest  = (r: UnitRoomData) => r.x        <= TOL;
  const onEast  = (r: UnitRoomData) => r.x + r.w  >= unitW - TOL;

  // Door arc: gap in wall + quarter-circle swing into the room
  function buildDoor(r: UnitRoomData) {
    const dw  = r.door_width * scale;
    const off = r.door_offset * scale;

    switch (r.door_wall) {
      case "south": {
        // Corridor-facing wall at y=r.y (top of room in SVG)
        const hx = tx(r.x) + off;
        const hy = ty(r.y);
        return {
          gapX1: hx, gapY1: hy - IW, gapX2: hx + dw, gapY2: hy + IW,
          arc:  `M ${hx} ${hy + dw} A ${dw} ${dw} 0 0 1 ${hx + dw} ${hy}`,
          leaf: `M ${hx} ${hy} L ${hx} ${hy + dw}`,
        };
      }
      case "north": {
        // Exterior wall at y=r.y+r.h (bottom of room in SVG)
        const hx = tx(r.x) + off;
        const hy = ty(r.y + r.h);
        return {
          gapX1: hx, gapY1: hy - IW, gapX2: hx + dw, gapY2: hy + IW,
          arc:  `M ${hx} ${hy - dw} A ${dw} ${dw} 0 0 0 ${hx + dw} ${hy}`,
          leaf: `M ${hx} ${hy} L ${hx} ${hy - dw}`,
        };
      }
      case "west": {
        // Left wall at x=r.x
        const hx = tx(r.x);
        const hy = ty(r.y) + off;
        return {
          gapX1: hx - IW, gapY1: hy, gapX2: hx + IW, gapY2: hy + dw,
          arc:  `M ${hx + dw} ${hy} A ${dw} ${dw} 0 0 0 ${hx} ${hy + dw}`,
          leaf: `M ${hx} ${hy} L ${hx + dw} ${hy}`,
        };
      }
      case "east": {
        // Right wall at x=r.x+r.w
        const hx = tx(r.x + r.w);
        const hy = ty(r.y) + off;
        return {
          gapX1: hx - IW, gapY1: hy, gapX2: hx + IW, gapY2: hy + dw,
          arc:  `M ${hx - dw} ${hy} A ${dw} ${dw} 0 0 1 ${hx} ${hy + dw}`,
          leaf: `M ${hx} ${hy} L ${hx - dw} ${hy}`,
        };
      }
    }
  }

  // Window glazing: gap in wall + 3 parallel lines
  function buildWindows(r: UnitRoomData) {
    const wo  = r.window_offset ?? (r.w / 2 - r.window_width / 2);
    const ww  = r.window_width * scale;
    const results: JSX.Element[] = [];

    r.window_walls.forEach((wall, wi) => {
      const key = `win-${r.name}-${wi}`;
      if (wall === "north") {
        const wx = tx(r.x + wo), wy = ty(r.y + r.h);
        results.push(
          <g key={key}>
            <rect x={wx} y={wy - EW / 2} width={ww} height={EW} fill="white" />
            <line x1={wx} y1={wy - EW / 2} x2={wx + ww} y2={wy - EW / 2} stroke="#38bdf8" strokeWidth={1} />
            <line x1={wx} y1={wy}          x2={wx + ww} y2={wy}          stroke="#38bdf8" strokeWidth={1.5} />
            <line x1={wx} y1={wy + EW / 2} x2={wx + ww} y2={wy + EW / 2} stroke="#38bdf8" strokeWidth={1} />
          </g>
        );
      } else if (wall === "east") {
        const wx = tx(r.x + r.w), wy = ty(r.y + wo);
        results.push(
          <g key={key}>
            <rect x={wx - EW / 2} y={wy} width={EW} height={ww} fill="white" />
            <line x1={wx - EW / 2} y1={wy} x2={wx - EW / 2} y2={wy + ww} stroke="#38bdf8" strokeWidth={1} />
            <line x1={wx}          y1={wy} x2={wx}          y2={wy + ww} stroke="#38bdf8" strokeWidth={1.5} />
            <line x1={wx + EW / 2} y1={wy} x2={wx + EW / 2} y2={wy + ww} stroke="#38bdf8" strokeWidth={1} />
          </g>
        );
      } else if (wall === "west") {
        const wx = tx(r.x), wy = ty(r.y + wo);
        results.push(
          <g key={key}>
            <rect x={wx - EW / 2} y={wy} width={EW} height={ww} fill="white" />
            <line x1={wx - EW / 2} y1={wy} x2={wx - EW / 2} y2={wy + ww} stroke="#38bdf8" strokeWidth={1} />
            <line x1={wx}          y1={wy} x2={wx}          y2={wy + ww} stroke="#38bdf8" strokeWidth={1.5} />
            <line x1={wx + EW / 2} y1={wy} x2={wx + EW / 2} y2={wy + ww} stroke="#38bdf8" strokeWidth={1} />
          </g>
        );
      }
    });
    return results;
  }

  return (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      className="h-full w-full"
      style={{ maxHeight: "100%", background: "white" }}
    >
      <defs>
        <marker id="arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#475569" />
        </marker>
        <marker id="arrR" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto-start-reverse">
          <path d="M0,0 L6,3 L0,6 Z" fill="#475569" />
        </marker>
      </defs>

      {/* ── 1. Room fills ─────────────────────────────────────────────── */}
      {rooms.map((r, i) => {
        const st = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        return (
          <rect key={`fill-${i}`}
            x={tx(r.x)} y={ty(r.y)}
            width={r.w * scale} height={r.h * scale}
            fill={st.fill}
          />
        );
      })}

      {/* ── 2. Furniture ─────────────────────────────────────────────── */}
      {rooms.flatMap((r, ri) =>
        (r.furniture ?? []).map((f: UnitFurnitureItem, fi) => {
          const fc   = FURNITURE_FILL[f.type] ?? FURN_DEFAULT;
          const fPxW = f.w * scale;
          const fPxH = f.h * scale;
          return (
            <g key={`furn-${ri}-${fi}`}>
              <rect
                x={tx(r.x + f.x)} y={ty(r.y + f.y)}
                width={fPxW} height={fPxH}
                fill={fc} stroke="#94a3b8" strokeWidth={0.75} rx={1} opacity={0.85}
              />
              {fPxW > 28 && fPxH > 18 && (
                <text
                  x={tx(r.x + f.x) + fPxW / 2}
                  y={ty(r.y + f.y) + fPxH / 2}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={Math.min(7, fPxW / 5, fPxH / 3)}
                  fill="#475569"
                  style={{ pointerEvents: "none" }}
                >
                  {f.type.replace(/_/g, " ")}
                </text>
              )}
            </g>
          );
        })
      )}

      {/* ── 3. Wall lines per room ────────────────────────────────────── */}
      {rooms.map((r, i) => {
        const rx = tx(r.x), ry = ty(r.y);
        const rW = r.w * scale, rH = r.h * scale;
        const wN = onNorth(r) ? EW : IW;
        const wS = onSouth(r) ? EW : IW;
        const wE = onEast(r)  ? EW : IW;
        const wW = onWest(r)  ? EW : IW;
        return (
          <g key={`wall-${i}`}>
            <line x1={rx}      y1={ry}      x2={rx + rW} y2={ry}      stroke="#1e293b" strokeWidth={wS} />
            <line x1={rx}      y1={ry + rH} x2={rx + rW} y2={ry + rH} stroke="#1e293b" strokeWidth={wN} />
            <line x1={rx}      y1={ry}      x2={rx}      y2={ry + rH} stroke="#1e293b" strokeWidth={wW} />
            <line x1={rx + rW} y1={ry}      x2={rx + rW} y2={ry + rH} stroke="#1e293b" strokeWidth={wE} />
          </g>
        );
      })}

      {/* ── 4. Windows (before doors so walls overdraw correctly) ─────── */}
      {rooms.flatMap((r) => buildWindows(r))}

      {/* ── 5. Doors ─────────────────────────────────────────────────── */}
      {rooms.map((r, i) => {
        const door = buildDoor(r);
        if (!door) return null;
        const { gapX1, gapY1, gapX2, gapY2, arc, leaf } = door;
        return (
          <g key={`door-${i}`}>
            {/* White gap clears the wall */}
            <rect
              x={gapX1} y={gapY1}
              width={Math.max(1, gapX2 - gapX1)}
              height={Math.max(1, gapY2 - gapY1)}
              fill="white"
            />
            {/* Door leaf */}
            <path d={leaf} stroke="#6b7280" strokeWidth={1.25} fill="none" />
            {/* Swing arc */}
            <path d={arc}  stroke="#6b7280" strokeWidth={0.75} fill="none" strokeDasharray="3 2" />
          </g>
        );
      })}

      {/* ── 6. GDCR fail overlay ─────────────────────────────────────── */}
      {rooms.filter((r) => !r.gdcr_ok).map((r, i) => (
        <rect key={`gdcr-${i}`}
          x={tx(r.x)} y={ty(r.y)}
          width={r.w * scale} height={r.h * scale}
          fill="rgba(239,68,68,0.07)"
          stroke="#ef4444" strokeWidth={1} strokeDasharray="4 2"
        />
      ))}

      {/* ── 7. Room labels ───────────────────────────────────────────── */}
      {rooms.map((r, i) => {
        const st   = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        const cx   = tx(r.x + r.w / 2);
        const cy   = ty(r.y + r.h / 2);
        const pxW  = r.w * scale;
        const pxH  = r.h * scale;
        const fs   = Math.max(7, Math.min(11, pxW / 5.5, pxH / 3.5));
        return (
          <g key={`lbl-${i}`}>
            {pxW > 32 && pxH > 22 && (
              <text
                x={cx} y={cy - (pxH > 44 ? 7 : 0)}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={fs} fontWeight="700" fill={st.text}
              >
                {r.name}
              </text>
            )}
            {pxW > 44 && pxH > 44 && (
              <text
                x={cx} y={cy + 10}
                textAnchor="middle" dominantBaseline="middle"
                fontSize={Math.min(9, pxW / 7)} fill={st.text} opacity={0.75}
              >
                {r.area_sqm.toFixed(1)} m²
              </text>
            )}
            {!r.gdcr_ok && (
              <text x={tx(r.x) + 4} y={ty(r.y) + 12}
                fontSize={10} fill="#dc2626" fontWeight="800">✕</text>
            )}
          </g>
        );
      })}

      {/* ── 8. Entry indicator ───────────────────────────────────────── */}
      <line
        x1={tx(unitW * 0.38)} y1={ty(0)}
        x2={tx(unitW * 0.62)} y2={ty(0)}
        stroke="#0ea5e9" strokeWidth={4} strokeLinecap="round"
      />
      <text x={tx(unitW * 0.5)} y={ty(0) - 9}
        textAnchor="middle" fontSize={8} fill="#0369a1" fontWeight="700">
        ↓ ENTRY / CORRIDOR
      </text>

      {/* ── 9. Dimension annotations ─────────────────────────────────── */}
      {/* Width (bottom) */}
      <line
        x1={tx(0)} y1={ty(unitD) + 20}
        x2={tx(unitW)} y2={ty(unitD) + 20}
        stroke="#475569" strokeWidth={1}
        markerStart="url(#arrR)" markerEnd="url(#arr)"
      />
      <text x={tx(unitW / 2)} y={ty(unitD) + 33}
        textAnchor="middle" fontSize={9} fill="#475569">
        {unitW.toFixed(2)} m
      </text>
      {/* Depth (right) */}
      <line
        x1={tx(unitW) + 20} y1={ty(0)}
        x2={tx(unitW) + 20} y2={ty(unitD)}
        stroke="#475569" strokeWidth={1}
        markerStart="url(#arrR)" markerEnd="url(#arr)"
      />
      <text
        x={tx(unitW) + 38} y={ty(unitD / 2)}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={9} fill="#475569"
        transform={`rotate(90 ${tx(unitW) + 38} ${ty(unitD / 2)})`}
      >
        {unitD.toFixed(2)} m
      </text>

      {/* Compass */}
      <g transform={`translate(${VW - 26} 22)`}>
        <circle cx={0} cy={0} r={11} fill="none" stroke="#e2e8f0" strokeWidth={1} />
        <path d="M 0,-9 L 3,2 L 0,0 L -3,2 Z" fill="#1e293b" />
        <path d="M 0,9 L 3,-2 L 0,0 L -3,-2 Z" fill="#cbd5e1" />
        <text x={0} y={-14} textAnchor="middle" fontSize={7} fill="#64748b" fontWeight="700">N</text>
      </g>
    </svg>
  );
}

// ─── Room compliance list ─────────────────────────────────────────────────────
function RoomList({ rooms }: { rooms: UnitRoomData[] }) {
  return (
    <div className="space-y-1.5">
      {rooms.map((r) => {
        const st = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        return (
          <div
            key={r.name}
            className={`flex items-center gap-2 rounded px-2 py-1.5 ${
              r.gdcr_ok ? "bg-neutral-50" : "bg-red-50 border border-red-100"
            }`}
          >
            <div
              className="h-3 w-3 flex-shrink-0 rounded-sm border"
              style={{ background: st.fill, borderColor: st.stroke }}
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

// ─── Main Stage 3 view ────────────────────────────────────────────────────────
export function UnitInteriorView() {
  const selectedUnit    = usePlannerStore((s) => s.selectedUnit);
  const setPlanningStep = usePlannerStore((s) => s.setPlanningStep);

  const { mutate: requestLayout, data, isPending, isError, error } = useUnitLayout();

  // Auto-generate layout when unit changes
  useEffect(() => {
    if (!selectedUnit?.unitType) return;
    requestLayout({
      unit_type:    selectedUnit.unitType,
      unit_width_m: selectedUnit.unitWidthM ?? 6.0,
      unit_depth_m: selectedUnit.unitDepthM ?? 7.5,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUnit?.id]);

  const goBack = useCallback(() => setPlanningStep("floor"), [setPlanningStep]);

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
    "4BHK":   "bg-red-50 text-red-700 border-red-200",
    "3BHK":   "bg-amber-50 text-amber-700 border-amber-200",
    "2BHK":   "bg-green-50 text-green-700 border-green-200",
    "1BHK":   "bg-sky-50 text-sky-700 border-sky-200",
    "STUDIO": "bg-purple-50 text-purple-700 border-purple-200",
    "1RK":    "bg-purple-50 text-purple-700 border-purple-200",
  };
  const typeCls = TYPE_COLOR[selectedUnit.unitType ?? ""] ?? "bg-neutral-50 text-neutral-700 border-neutral-200";

  return (
    <div className="flex h-full w-full overflow-hidden">

      {/* ── Left: architectural drawing ───────────────────────────────── */}
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
          <span className="text-xs text-neutral-400">{selectedUnit.id}</span>
          {data?.source && (
            <span className={`ml-1 rounded px-1.5 py-0.5 text-[9px] font-semibold ${
              data.source === "llm"
                ? "bg-purple-100 text-purple-700"
                : "bg-neutral-100 text-neutral-600"
            }`}>
              {data.source === "llm" ? "AI Layout" : "Template"}
            </span>
          )}
        </div>

        {/* Canvas area */}
        <div className="relative flex flex-1 items-center justify-center bg-neutral-100 p-4">
          {isPending && (
            <div className="flex flex-col items-center gap-3">
              <div className="h-7 w-7 animate-spin rounded-full border-2 border-neutral-300 border-t-sky-600" />
              <p className="text-xs text-neutral-500">Generating room layout…</p>
            </div>
          )}

          {isError && !isPending && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-center">
              <p className="text-sm font-medium text-red-700">Layout generation failed</p>
              <p className="mt-1 text-xs text-red-600">{error?.message ?? "Unknown error"}</p>
              <button type="button"
                onClick={() => requestLayout({
                  unit_type:    selectedUnit.unitType ?? "2BHK",
                  unit_width_m: selectedUnit.unitWidthM ?? 6.0,
                  unit_depth_m: selectedUnit.unitDepthM ?? 7.5,
                })}
                className="mt-2 rounded bg-red-100 px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-200">
                Retry
              </button>
            </div>
          )}

          {data?.rooms && !isPending && (
            <div className="h-full w-full rounded-lg border border-neutral-200 bg-white shadow-sm overflow-hidden">
              <ArchitecturalPlan
                rooms={data.rooms}
                unitW={data.unit_width_m}
                unitD={data.unit_depth_m}
              />
            </div>
          )}
        </div>
      </div>

      {/* ── Right: unit details + GDCR panel ─────────────────────────── */}
      <div className="flex w-72 flex-shrink-0 flex-col overflow-hidden border-l border-neutral-200 bg-white">
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
              {([
                ["Unit ID",       selectedUnit.id],
                ["Type",          selectedUnit.unitType ?? "—"],
                ["Width",         selectedUnit.unitWidthM  ? `${selectedUnit.unitWidthM.toFixed(1)} m`  : "—"],
                ["Depth",         selectedUnit.unitDepthM  ? `${selectedUnit.unitDepthM.toFixed(1)} m`  : "—"],
                ["Built-up area", selectedUnit.builtUpArea ? `${selectedUnit.builtUpArea.toFixed(1)} m²` : "—"],
                ["Carpet area",   selectedUnit.carpetArea  ? `${selectedUnit.carpetArea.toFixed(1)} m²`  : "—"],
                ["RERA carpet",   selectedUnit.reraCarpet  ? `${selectedUnit.reraCarpet.toFixed(1)} m²`  : "—"],
              ] as [string, string][]).map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-neutral-500">{k}</span>
                  <span className="font-medium text-neutral-800">{v}</span>
                </div>
              ))}
              {selectedUnit.efficiency != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-neutral-500">Efficiency</span>
                  <span className={`font-bold ${
                    selectedUnit.efficiency >= 0.70 ? "text-green-700"
                    : selectedUnit.efficiency >= 0.60 ? "text-amber-700"
                    : "text-red-600"
                  }`}>
                    {(selectedUnit.efficiency * 100).toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* AI design notes */}
          {data?.design_notes && (
            <div className="rounded bg-purple-50 p-2.5 text-[10px] text-purple-800 leading-relaxed">
              <div className="mb-1 font-semibold text-purple-900">AI Design Notes</div>
              {data.design_notes}
            </div>
          )}

          {/* GDCR compliance banner */}
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

          {/* Warnings */}
          {data?.warnings && data.warnings.length > 0 && (
            <div className="rounded border border-amber-200 bg-amber-50 p-2 space-y-0.5">
              {data.warnings.map((w, i) => (
                <p key={i} className="text-[10px] text-amber-700">{w}</p>
              ))}
            </div>
          )}

          {/* Per-room compliance list */}
          {data?.rooms && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
                Rooms ({data.rooms.length})
              </h3>
              <RoomList rooms={data.rooms} />
            </section>
          )}

          {/* Legend */}
          <div className="rounded bg-neutral-50 p-2 text-[9px] leading-relaxed text-neutral-500 space-y-0.5">
            <div><span className="inline-block h-2 w-2 rounded-sm border border-sky-300 bg-sky-100 mr-1" />Windows (blue lines)</div>
            <div><span className="inline-block h-2 w-2 rounded-sm border border-gray-400 bg-gray-100 mr-1" />Door + swing arc (dashed)</div>
            <div><span className="inline-block h-2 w-2 rounded-sm border border-red-300 bg-red-50 mr-1" />GDCR violation (red dashed)</div>
          </div>

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
