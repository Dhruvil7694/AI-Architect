"use client";

import { useSiteMetrics } from "@/modules/planner/hooks/usePlannerData";
import { usePlannerStore } from "@/state/plannerStore";
import { Box, Layers, Ruler, BarChart3 } from "lucide-react";

export function SiteMetricsSummary() {
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const { data: metrics, isLoading } = useSiteMetrics(selectedPlotId);

  if (!selectedPlotId) return null;

  const SQM_TO_SQFT = 10.7639;
  const items = [
    { 
      label: "Plot Area", 
      value: metrics?.plotAreaSqm ? `${Math.round(metrics.plotAreaSqm * SQM_TO_SQFT).toLocaleString()} sqft` : "0", 
      icon: Ruler 
    },
    { 
      label: "Max BUA", 
      value: metrics?.maxBUA ? `${Math.round(metrics.maxBUA * SQM_TO_SQFT).toLocaleString()} sqft` : "0", 
      icon: Layers 
    },
    { 
      label: "Max FSI", 
      value: metrics?.maxFSI ? metrics.maxFSI.toFixed(2) : "0.00", 
      icon: Box 
    },
    { 
      label: "Min COP", 
      value: metrics?.plotAreaSqm && metrics.copAreaSqm ? `${Math.round((metrics.copAreaSqm / metrics.plotAreaSqm) * 100)}%` : "0%", 
      highlight: true, 
      icon: BarChart3 
    },
  ];

  return (
    <div className="flex items-center gap-6 rounded-2xl border border-neutral-100 bg-white px-5 py-2.5 shadow-sm">
      {items.map((item, idx) => (
        <div key={item.label} className="flex items-center gap-6">
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 opacity-40">
               <item.icon className="h-3 w-3" />
               <span className="text-[10px] font-bold uppercase tracking-wider">{item.label}</span>
            </div>
            <div className={`font-heading text-sm font-bold tracking-tight ${item.highlight ? "text-orange-500" : "text-neutral-900"}`}>
              {isLoading ? "---" : item.value}
            </div>
          </div>
          {idx < items.length - 1 && (
            <div className="h-6 w-px bg-neutral-100" />
          )}
        </div>
      ))}
    </div>
  );
}
