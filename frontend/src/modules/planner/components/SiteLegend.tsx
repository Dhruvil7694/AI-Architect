"use client";

import { useState } from "react";

/**
 * SiteLegend — collapsible legend panel for the professional site plan view.
 *
 * Rendered as an HTML overlay positioned absolutely over the SVG canvas.
 */

interface SiteLegendProps {
  showLandscape: boolean;
  showCop:       boolean;
}

const BASE_ITEMS = [
  { key: "tower",    fill: "#bfdbfe", stroke: "#3b82f6", label: "Tower Footprint" },
  { key: "envelope", fill: "none",    stroke: "#94a3b8", label: "Buildable Envelope", dashed: true },
  { key: "plot",     fill: "none",    stroke: "#6b7280", label: "Plot Boundary" },
] as const;

const LANDSCAPE_ITEM = {
  key: "landscape", fill: "#bbf7d0", stroke: "#4ade80", label: "Landscape",
};

const COP_ITEM = {
  key: "cop", fill: "rgba(167,243,208,0.55)", stroke: "#22c55e", label: "Common Open Plot",
};

const SHADOW_ITEM = {
  key: "shadow", fill: "rgba(0,0,0,0.14)", stroke: "transparent", label: "Tower Shadow",
};

const DRIVEWAY_ITEM = {
  key: "driveway", fill: "none", stroke: "#4b5563", label: "Driveway",
};

export function SiteLegend({ showLandscape, showCop }: SiteLegendProps) {
  const [collapsed, setCollapsed] = useState(false);

  const items = [
    ...BASE_ITEMS,
    ...(showLandscape ? [LANDSCAPE_ITEM] : []),
    ...(showCop ? [COP_ITEM] : []),
    SHADOW_ITEM,
    DRIVEWAY_ITEM,
  ];

  return (
    <div className="absolute bottom-3 right-3 z-10 rounded-lg border border-neutral-200 bg-white/95 shadow-sm">
      {/* Header */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex w-full items-center justify-between gap-4 px-3 py-2"
      >
        <span className="text-[9px] font-semibold uppercase tracking-widest text-neutral-500">
          Legend
        </span>
        <svg
          className={`h-3 w-3 text-neutral-400 transition-transform ${collapsed ? "-rotate-90" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Items */}
      {!collapsed && (
        <div className="flex flex-col gap-1 px-3 pb-2">
          {items.map(({ key, fill, stroke, label, ...rest }) => (
            <div key={key} className="flex items-center gap-1.5">
              <div
                className="h-3 w-4 flex-shrink-0 rounded-sm border"
                style={{
                  background: fill === "none" ? "transparent" : fill,
                  borderColor: stroke,
                  borderStyle: "dashed" in rest && rest.dashed ? "dashed" : "solid",
                }}
              />
              <span className="text-[9px] text-neutral-600">{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
