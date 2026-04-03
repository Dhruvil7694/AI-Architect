"use client";

import { useEffect, useCallback } from "react";
import { usePlannerStore } from "@/state/plannerStore";
import { useUnitLayout } from "@/modules/planner/hooks/usePlannerData";
import type { UnitRoomData, UnitFurnitureItem } from "@/services/plannerService";
import { 
  Bed, 
  Bath, 
  Sofa, 
  ChefHat, 
  Utensils, 
  Home, 
  ArrowLeft,
  Info,
  AlertTriangle,
  CheckCircle2,
  Zap
} from "lucide-react";

// ─── Room colour palette (Premium Architectural) ───────────────────────────
const ROOM_STYLE: Record<string, { stroke: string; text: string; bg: string }> = {
  foyer:    { stroke: "#64748b", text: "#475569", bg: "#f8fafc" },
  living:   { stroke: "#f97316", text: "#9a3412", bg: "#fffaf5" },
  dining:   { stroke: "#f97316", text: "#9a3412", bg: "#fffaf5" },
  kitchen:  { stroke: "#14b8a6", text: "#134e4a", bg: "#f0fdfa" },
  bedroom:  { stroke: "#6366f1", text: "#312e81", bg: "#f5f3ff" },
  bedroom2: { stroke: "#8b5cf6", text: "#4c1d95", bg: "#f5f3ff" },
  bathroom: { stroke: "#0ea5e9", text: "#075985", bg: "#f0f9ff" },
  toilet:   { stroke: "#3b82f6", text: "#1e3a8a", bg: "#eff6ff" },
  balcony:  { stroke: "#22c55e", text: "#14532d", bg: "#f0fdf4" },
  utility:  { stroke: "#14b8a6", text: "#134e4a", bg: "#f0fdfa" },
  studio:   { stroke: "#6366f1", text: "#312e81", bg: "#f5f3ff" },
};
const DEFAULT_STYLE = { stroke: "#64748b", text: "#334155", bg: "#ffffff" };

// Furniture colours (Muted Architectural)
const FURN_THEME: Record<string, { fill: string; stroke: string }> = {
  bed:          { fill: "#f1f5f9", stroke: "#cbd5e1" },
  sofa:         { fill: "#fffbeb", stroke: "#fde68a" },
  wardrobe:     { fill: "#f8fafc", stroke: "#e2e8f0" },
  kitchen:      { fill: "#fdf2f2", stroke: "#fecaca" },
  sanitary:     { fill: "#f0f9ff", stroke: "#bae6fd" },
  utility:      { fill: "#f9fafb", stroke: "#f3f4f6" },
};

function getFurnitureTheme(type: string) {
  const t = type.toLowerCase();
  if (t.includes("bed")) return FURN_THEME.bed;
  if (t.includes("sofa")) return FURN_THEME.sofa;
  if (t.includes("wardrobe")) return FURN_THEME.wardrobe;
  if (t.includes("kitchen") || t.includes("counter")) return FURN_THEME.kitchen;
  if (t.includes("wc") || t.includes("basin") || t.includes("shower") || t.includes("bathtub")) return FURN_THEME.sanitary;
  return FURN_THEME.utility;
}

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
  const PAD  = 60;   
  const VW   = 800;
  const VH   = 600;
  const scale = Math.min((VW - PAD * 2) / unitW, (VH - PAD * 2) / unitD);
  const EW   = 8;    // load-bearing external wall
  const IW   = 4;    // partition wall
  const TOL  = 0.05; 

  const tx = (x: number) => PAD + x * scale;
  const ty = (y: number) => PAD + y * scale;  

  const onSouth = (r: UnitRoomData) => r.y        <= TOL;
  const onNorth = (r: UnitRoomData) => r.y + r.h  >= unitD - TOL;
  const onWest  = (r: UnitRoomData) => r.x        <= TOL;
  const onEast  = (r: UnitRoomData) => r.x + r.w  >= unitW - TOL;

  function buildDoor(r: UnitRoomData) {
    const dw  = r.door_width * scale;
    const off = r.door_offset * scale;

    switch (r.door_wall) {
      case "south": {
        const hx = tx(r.x) + off;
        const hy = ty(r.y);
        return {
          gapX1: hx, gapY1: hy - IW, gapX2: hx + dw, gapY2: hy + IW,
          arc:  `M ${hx} ${hy + dw} A ${dw} ${dw} 0 0 0 ${hx + dw} ${hy}`,
          leaf: `M ${hx} ${hy} L ${hx} ${hy + dw}`,
        };
      }
      case "north": {
        const hx = tx(r.x) + off;
        const hy = ty(r.y + r.h);
        return {
          gapX1: hx, gapY1: hy - IW, gapX2: hx + dw, gapY2: hy + IW,
          arc:  `M ${hx} ${hy - dw} A ${dw} ${dw} 0 0 1 ${hx + dw} ${hy}`,
          leaf: `M ${hx} ${hy} L ${hx} ${hy - dw}`,
        };
      }
      case "west": {
        const hx = tx(r.x);
        const hy = ty(r.y) + off;
        return {
          gapX1: hx - IW, gapY1: hy, gapX2: hx + IW, gapY2: hy + dw,
          arc:  `M ${hx + dw} ${hy} A ${dw} ${dw} 0 0 1 ${hx} ${hy + dw}`,
          leaf: `M ${hx} ${hy} L ${hx + dw} ${hy}`,
        };
      }
      case "east": {
        const hx = tx(r.x + r.w);
        const hy = ty(r.y) + off;
        return {
          gapX1: hx - IW, gapY1: hy, gapX2: hx + IW, gapY2: hy + dw,
          arc:  `M ${hx - dw} ${hy} A ${dw} ${dw} 0 0 0 ${hx} ${hy + dw}`,
          leaf: `M ${hx} ${hy} L ${hx - dw} ${hy}`,
        };
      }
      default: return null;
    }
  }

  function buildWindows(r: UnitRoomData) {
    const wo  = r.window_offset ?? (r.w / 2 - r.window_width / 2);
    const ww  = r.window_width * scale;
    const results: any[] = [];

    r.window_walls.forEach((wall, wi) => {
      const key = `win-${r.name}-${wi}`;
      if (wall === "north") {
        const wx = tx(r.x + wo), wy = ty(r.y + r.h);
        results.push(
          <g key={key}>
            <rect x={wx} y={wy - EW / 2} width={ww} height={EW} fill="white" />
            <line x1={wx} y1={wy} x2={wx + ww} y2={wy} stroke="#0ea5e9" strokeWidth={2} />
            <rect x={wx + 2} y={wy - 1.5} width={ww - 4} height={3} fill="#f0f9ff" stroke="#7dd3fc" strokeWidth={0.5} />
          </g>
        );
      } else if (wall === "east") {
        const wx = tx(r.x + r.w), wy = ty(r.y + wo);
        results.push(
          <g key={key}>
            <rect x={wx - EW / 2} y={wy} width={EW} height={ww} fill="white" />
            <line x1={wx} y1={wy} x2={wx} y2={wy + ww} stroke="#0ea5e9" strokeWidth={2} />
            <rect x={wx - 1.5} y={wy + 2} width={3} height={ww - 4} fill="#f0f9ff" stroke="#7dd3fc" strokeWidth={0.5} />
          </g>
        );
      } else if (wall === "west") {
        const wx = tx(r.x), wy = ty(r.y + wo);
        results.push(
          <g key={key}>
            <rect x={wx - EW / 2} y={wy} width={EW} height={ww} fill="white" />
            <line x1={wx} y1={wy} x2={wx} y2={wy + ww} stroke="#0ea5e9" strokeWidth={2} />
            <rect x={wx - 1.5} y={wy + 2} width={3} height={ww - 4} fill="#f0f9ff" stroke="#7dd3fc" strokeWidth={0.5} />
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
      style={{ maxHeight: "100%", background: "#fdfdfd" }}
    >
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
           <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#f1f5f9" strokeWidth="0.5" />
        </pattern>
      </defs>

      <rect width="100%" height="100%" fill="url(#grid)" />

      {/* 1. Room Fills */}
      {rooms.map((r, i) => {
        const st = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        return (
          <rect key={`fill-${i}`}
            x={tx(r.x)} y={ty(r.y)}
            width={r.w * scale} height={r.h * scale}
            fill={st.bg}
          />
        );
      })}

      {/* 2. Furniture (Redesigned) */}
      {rooms.flatMap((r, ri) =>
        (r.furniture ?? []).map((f: UnitFurnitureItem, fi) => {
          const theme = getFurnitureTheme(f.type);
          const pxW = f.w * scale;
          const pxH = f.h * scale;
          const fx = tx(r.x + f.x);
          const fy = ty(r.y + f.y);
          const t = f.type.toLowerCase();
          
          return (
            <g key={`furn-${ri}-${fi}`}>
              <rect
                x={fx} y={fy}
                width={pxW} height={pxH}
                fill={theme.fill} stroke={theme.stroke} strokeWidth={1} rx={2}
              />
              {/* Detail overlays for furniture */}
              {t.includes("bed") && (
                <g opacity={0.5}>
                   <rect x={fx + 4} y={fy + 4} width={pxW - 8} height={pxH * 0.3} fill="none" stroke={theme.stroke} rx={1} />
                   <line x1={fx + pxW * 0.5} y1={fy + 4} x2={fx + pxW * 0.5} y2={fy + 4 + pxH * 0.3} stroke={theme.stroke} />
                </g>
              )}
              {t.includes("sofa") && (
                <line x1={fx + 5} y1={fy + pxH - 5} x2={fx + pxW - 5} y2={fy + pxH - 5} stroke={theme.stroke} strokeWidth={2} strokeLinecap="round" opacity={0.4} />
              )}
              {t.includes("wc") && (
                <ellipse cx={fx + pxW * 0.5} cy={fy + pxH * 0.6} rx={pxW * 0.3} ry={pxH * 0.4} fill="none" stroke={theme.stroke} strokeWidth={1} opacity={0.6} />
              )}
            </g>
          );
        })
      )}

      {/* 3. Wall Lines */}
      {rooms.map((r, i) => {
        const rx = tx(r.x), ry = ty(r.y);
        const rW = r.w * scale, rH = r.h * scale;
        const wN = onNorth(r) ? EW : IW;
        const wS = onSouth(r) ? EW : IW;
        const wE = onEast(r)  ? EW : IW;
        const wW = onWest(r)  ? EW : IW;
        return (
          <g key={`wall-${i}`}>
            <line x1={rx}      y1={ry}      x2={rx + rW} y2={ry}      stroke="#0f172a" strokeWidth={wS} strokeLinecap="square" />
            <line x1={rx}      y1={ry + rH} x2={rx + rW} y2={ry + rH} stroke="#0f172a" strokeWidth={wN} strokeLinecap="square" />
            <line x1={rx}      y1={ry}      x2={rx}      y2={ry + rH} stroke="#0f172a" strokeWidth={wW} strokeLinecap="square" />
            <line x1={rx + rW} y1={ry}      x2={rx + rW} y2={ry + rH} stroke="#0f172a" strokeWidth={wE} strokeLinecap="square" />
          </g>
        );
      })}

      {/* 4. Windows */}
      {rooms.flatMap((r) => buildWindows(r))}

      {/* 5. Doors */}
      {rooms.map((r, i) => {
        const door = buildDoor(r);
        if (!door) return null;
        const { gapX1, gapY1, gapX2, gapY2, arc, leaf } = door;
        return (
          <g key={`door-${i}`}>
            <rect x={gapX1} y={gapY1} width={Math.max(2, gapX2 - gapX1)} height={Math.max(2, gapY2 - gapY1)} fill="white" />
            <path d={leaf} stroke="#475569" strokeWidth={2} fill="none" />
            <path d={arc}  stroke="#94a3b8" strokeWidth={1} fill="none" strokeDasharray="4 3" />
          </g>
        );
      })}

      {/* 6. GDCR Violations */}
      {rooms.filter((r) => !r.gdcr_ok).map((r, i) => (
        <rect key={`gdcr-${i}`} x={tx(r.x)} y={ty(r.y)} width={r.w * scale} height={r.h * scale} fill="rgba(239, 68, 68, 0.04)" stroke="#ef4444" strokeWidth={1} strokeDasharray="8 4" />
      ))}

      {/* 7. Room Labels */}
      {rooms.map((r, i) => {
        const st = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        const cx = tx(r.x + r.w / 2);
        const cy = ty(r.y + r.h / 2);
        const pxW = r.w * scale;
        const pxH = r.h * scale;
        if (pxW < 30 || pxH < 20) return null;
        
        return (
          <g key={`lbl-${i}`} style={{ pointerEvents: "none" }}>
            <text x={cx} y={cy - 4} textAnchor="middle" className="font-heading text-[11px] font-bold tracking-tight" fill={st.text}>
              {r.name.toUpperCase()}
            </text>
            <text x={cx} y={cy + 10} textAnchor="middle" className="text-[9px] font-medium" fill={st.text} opacity={0.6}>
              {r.area_sqm.toFixed(1)} m²
            </text>
            {!r.gdcr_ok && (
              <circle cx={tx(r.x) + 12} cy={ty(r.y) + 12} r={6} fill="#ef4444" />
            )}
          </g>
        );
      })}

      {/* 8. Entry Marker */}
      <g transform={`translate(${tx(unitW * 0.5)} ${ty(0)})`}>
        <path d="M -15 0 L 15 0" stroke="#f97316" strokeWidth={4} strokeLinecap="round" />
        <text y={-12} textAnchor="middle" className="font-heading text-[9px] font-black text-orange-600 tracking-widest uppercase">
          Arrival
        </text>
      </g>

      {/* 9. Dimensions */}
      <g stroke="#94a3b8" strokeWidth={0.5}>
         <line x1={tx(0)} y1={ty(unitD) + 30} x2={tx(unitW)} y2={ty(unitD) + 30} />
         <line x1={tx(0)} y1={ty(unitD) + 25} x2={tx(0)} y2={ty(unitD) + 35} />
         <line x1={tx(unitW)} y1={ty(unitD) + 25} x2={tx(unitW)} y2={ty(unitD) + 35} />
      </g>
      <text x={tx(unitW / 2)} y={ty(unitD) + 45} textAnchor="middle" className="font-sans text-[10px] font-bold text-slate-400">
        {unitW.toFixed(2)} m
      </text>

      <g stroke="#94a3b8" strokeWidth={0.5}>
         <line x1={tx(unitW) + 30} y1={ty(0)} x2={tx(unitW) + 30} y2={ty(unitD)} />
         <line x1={tx(unitW) + 25} y1={ty(0)} x2={tx(unitW) + 35} y2={ty(0)} />
         <line x1={tx(unitW) + 25} y1={ty(unitD)} x2={tx(unitW) + 35} y2={ty(unitD)} />
      </g>
      <text x={tx(unitW) + 45} y={ty(unitD / 2)} textAnchor="middle" className="font-sans text-[10px] font-bold text-slate-400" transform={`rotate(90 ${tx(unitW) + 45} ${ty(unitD / 2)})`}>
        {unitD.toFixed(2)} m
      </text>
    </svg>
  );
}

// ─── Room compliance list ─────────────────────────────────────────────────────
function RoomList({ rooms }: { rooms: UnitRoomData[] }) {
  return (
    <div className="grid gap-2">
      {rooms.map((r) => {
        const st = ROOM_STYLE[r.type] ?? DEFAULT_STYLE;
        const Icon = r.type.toLowerCase().includes("bedroom") ? Bed :
                   r.type.toLowerCase().includes("kitchen") ? ChefHat :
                   r.type.toLowerCase().includes("living") ? Sofa :
                   r.type.toLowerCase().includes("bath") ? Bath :
                   r.type.toLowerCase().includes("dining") ? Utensils : Home;
                   
        return (
          <div
            key={r.name}
            className={`flex items-start gap-3 rounded-xl p-3 transition-colors ${
              r.gdcr_ok ? "bg-white border border-slate-100 shadow-sm" : "bg-red-50 border border-red-100"
            }`}
          >
            <div className={`flex h-8 w-8 items-center justify-center rounded-lg bg-white shadow-sm border ${r.gdcr_ok ? "border-slate-100" : "border-red-100"}`}>
               <Icon className={`h-4 w-4 ${r.gdcr_ok ? "text-slate-600" : "text-red-500"}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="font-heading text-xs font-bold text-slate-900 truncate">{r.name}</span>
                <span className="text-[10px] font-bold text-slate-500">{r.area_sqm.toFixed(1)} m²</span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">{r.width_m.toFixed(1)}m × {r.depth_m.toFixed(1)}m</p>
            </div>
            <div className={`mt-1 h-2 w-2 rounded-full ${r.gdcr_ok ? "bg-emerald-400" : "bg-red-500"}`} />
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

  useEffect(() => {
    if (!selectedUnit?.unitType) return;
    requestLayout({
      unit_type:    selectedUnit.unitType,
      unit_width_m: selectedUnit.unitWidthM ?? 6.0,
      unit_depth_m: selectedUnit.unitDepthM ?? 7.5,
    });
  }, [selectedUnit?.id, selectedUnit?.unitType, selectedUnit?.unitWidthM, selectedUnit?.unitDepthM, requestLayout]);

  const goBack = useCallback(() => setPlanningStep("floor"), [setPlanningStep]);

  if (!selectedUnit) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-6 p-8">
        <div className="flex flex-col items-center text-center max-w-xs gap-2">
           <Home className="h-12 w-12 text-slate-200" />
           <p className="font-heading text-lg font-bold text-slate-900">No unit selected</p>
           <p className="text-sm text-slate-500">Go back to the floor plan and select a specific unit to design its interior layout.</p>
        </div>
        <button type="button" onClick={goBack}
          className="rounded-xl bg-orange-500 px-6 py-2.5 text-sm font-bold text-white shadow-lg shadow-orange-500/20 hover:bg-orange-600 transition-all">
          Return to Floor Plan
        </button>
      </div>
    );
  }

  const TYPE_COLOR: Record<string, string> = {
    "4BHK":   "bg-rose-50 text-rose-600",
    "3BHK":   "bg-orange-50 text-orange-600",
    "2BHK":   "bg-emerald-50 text-emerald-600",
    "1BHK":   "bg-blue-50 text-blue-600",
    "STUDIO": "bg-purple-50 text-purple-600",
  };
  const typeCls = TYPE_COLOR[selectedUnit.unitType ?? ""] ?? "bg-slate-50 text-slate-600";

  return (
    <div className="flex h-full w-full overflow-hidden bg-white">
      {/* Drawing Column */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Unit Header */}
        <div className="flex items-center justify-between border-b border-slate-100 bg-white/50 backdrop-blur px-6 py-4">
          <div className="flex items-center gap-4">
             <button onClick={goBack} className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-slate-50 text-slate-400 hover:text-slate-900 transition-colors">
                <ArrowLeft className="h-4 w-4" />
             </button>
             <div className="flex flex-col">
                <div className="flex items-center gap-2">
                   <h1 className="font-heading text-lg font-bold text-slate-900 tracking-tight">Interior Layout Generator</h1>
                   <span className={`rounded-lg px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${typeCls}`}>
                     {selectedUnit.unitType}
                   </span>
                </div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Unit ID: {selectedUnit.id}</span>
             </div>
          </div>
          
          <div className="flex items-center gap-3">
            {data?.source === "llm" && (
              <div className="flex items-center gap-2 rounded-lg bg-orange-50 px-3 py-1.5 border border-orange-100 transition-all animate-in fade-in slide-in-from-right-2">
                 <Zap className="h-3.5 w-3.5 text-orange-500 fill-orange-500" />
                 <span className="text-[10px] font-bold uppercase tracking-wider text-orange-700">AI Synthesized</span>
              </div>
            )}
          </div>
        </div>

        {/* Canvas Area */}
        <div className="flex-1 overflow-hidden relative">
          {isPending && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-white/80 backdrop-blur-sm gap-4">
               <div className="relative flex h-12 w-12">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-12 w-12 bg-orange-500 flex items-center justify-center">
                    <Zap className="h-6 w-6 text-white" />
                  </span>
               </div>
               <p className="font-heading text-sm font-bold text-slate-900 animate-pulse">Designing Architectural Configuration...</p>
            </div>
          )}

          <div className="h-full w-full p-8 flex items-center justify-center bg-slate-50/10">
             <div className="h-full w-full max-w-4xl max-h-[600px] bg-white rounded-[2.5rem] shadow-2xl shadow-slate-200/40 border border-slate-100 overflow-hidden">
                {data?.rooms && (
                  <ArchitecturalPlan rooms={data.rooms} unitW={data.unit_width_m} unitD={data.unit_depth_m} />
                )}
             </div>
          </div>
        </div>
      </div>

      {/* Details Bar */}
      <aside className="w-80 border-l border-slate-100 bg-[#fdfdfd] flex flex-col overflow-hidden">
        <div className="px-6 py-5 border-b border-slate-100">
           <h2 className="font-heading text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Unit Intelligence</h2>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8 scrollbar-hide">
           {/* KPI Cards */}
           <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                 <p className="text-[9px] font-bold uppercase tracking-widest text-slate-400">Net Area</p>
                 <p className="font-heading text-base font-bold text-slate-900 mt-1">{selectedUnit.carpetArea?.toFixed(1) ?? "—"} m²</p>
              </div>
              <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                 <p className="text-[9px] font-bold uppercase tracking-widest text-slate-400">Efficiency</p>
                 <p className={`font-heading text-base font-bold mt-1 ${selectedUnit.efficiency ? (selectedUnit.efficiency > 0.7 ? "text-emerald-500" : "text-amber-500") : "text-slate-900"}`}>
                   {selectedUnit.efficiency ? `${(selectedUnit.efficiency * 100).toFixed(0)}%` : "—"}
                 </p>
              </div>
           </div>

           {/* AI Recommendations */}
           {data?.design_notes && (
             <section className="space-y-3">
                <div className="flex items-center gap-2">
                   <Info className="h-3.5 w-3.5 text-orange-500" />
                   <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-900">Design insights</h3>
                </div>
                <div className="rounded-2xl bg-white border border-slate-100 p-4 shadow-sm text-xs leading-relaxed text-slate-600 italic">
                   "{data.design_notes}"
                </div>
             </section>
           )}

           {/* Regulatory Compliance */}
           {data?.gdcr_summary && (
             <section className="space-y-3">
                <div className="flex items-center gap-2">
                   {data.gdcr_summary.all_ok ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : <AlertTriangle className="h-3.5 w-3.5 text-rose-500" /> }
                   <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-900">Compliance Radar</h3>
                </div>
                <div className={`rounded-2xl p-4 border ${data.gdcr_summary.all_ok ? "bg-emerald-50 border-emerald-100 text-emerald-800" : "bg-rose-50 border-rose-100 text-rose-800"}`}>
                   <p className="text-[11px] font-bold">
                     {data.gdcr_summary.all_ok ? "Standard Compliant" : `${data.gdcr_summary.violations.length} Violations Detected`}
                   </p>
                   {!data.gdcr_summary.all_ok && (
                     <div className="mt-2 space-y-1.5">
                       {data.gdcr_summary.violations.slice(0, 3).map((v, i) => (
                         <div key={i} className="flex gap-2 text-[10px] opacity-80 leading-snug">
                            <span className="font-bold shrink-0">{v.room}:</span>
                            <span>{v.issue}</span>
                         </div>
                       ))}
                     </div>
                   )}
                </div>
             </section>
           )}

           {/* Room List */}
           {data?.rooms && (
             <section className="space-y-3">
                <div className="flex items-center justify-between">
                   <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-900">Configured Rooms</h3>
                   <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-500">{data.rooms.length}</span>
                </div>
                <RoomList rooms={data.rooms} />
             </section>
           )}
        </div>
        
        <div className="p-6 bg-white border-t border-slate-100 space-y-3">
           <div className="flex items-center justify-between px-1">
              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Visual Legend</span>
              <div className="flex gap-4">
                 <div className="flex items-center gap-1"><div className="h-1.5 w-1.5 rounded-full bg-sky-500" /> <span className="text-[9px] text-slate-500 font-medium">Glazing</span></div>
                 <div className="flex items-center gap-1"><div className="h-1.5 w-1.5 rounded-full bg-orange-500" /> <span className="text-[9px] text-slate-500 font-medium">Access</span></div>
              </div>
           </div>
           <button onClick={goBack} className="w-full flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-all hover:border-slate-300">
              <ArrowLeft className="h-4 w-4" />
              Return to Floor Plan
           </button>
        </div>
      </aside>
    </div>
  );
}
