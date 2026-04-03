"use client";

import Link from "next/link";
import { ArrowRight, Layout, PieChart, Clock, MapPin } from "lucide-react";

export default function DashboardPage() {
  const kpis = [
    { label: "Active Plots", value: "7", hint: "Ready to plan", icon: MapPin },
    { label: "Scenarios", value: "32", hint: "Last 30 days", icon: Layout },
    { label: "Reviews", value: "5", hint: "Awaiting decisions", icon: PieChart },
    { label: "Last Run", value: "TP‑14", hint: "Updated 2h ago", icon: Clock },
  ];

  return (
    <div className="flex w-full flex-col gap-10 pb-10">
      {/* Page header */}
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="h-1 w-8 rounded-full bg-orange-500" />
          <p className="font-heading text-sm font-bold uppercase tracking-wider text-orange-500">
            Overview
          </p>
        </div>
        <h1 className="font-heading text-4xl font-bold tracking-tight text-neutral-900">
          Welcome back, <span className="text-neutral-400 font-medium">Architect</span>
        </h1>
        <p className="max-w-2xl text-base text-neutral-500">
          Manage your architectural site planning projects with AI-driven insights and deterministic precision.
        </p>
      </header>

      {/* KPI row */}
      <section className="grid gap-6 sm:grid-cols-4">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="group flex flex-col justify-between rounded-3xl border border-neutral-100 bg-white p-6 shadow-sm transition-all hover:-translate-y-1 hover:shadow-xl hover:shadow-orange-500/5"
          >
            <div className="flex items-center justify-between">
               <span className="text-xs font-bold uppercase tracking-wider text-neutral-400 group-hover:text-orange-500 transition-colors">
                 {kpi.label}
               </span>
               <kpi.icon className="h-4 w-4 text-neutral-300 group-hover:text-orange-500 transition-colors" />
            </div>
            <div className="mt-4 flex items-baseline gap-1">
              <div className="font-heading text-3xl font-bold tracking-tight text-neutral-900">
                {kpi.value}
              </div>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs font-medium text-neutral-400">
              <span className="h-1 w-1 rounded-full bg-orange-400" />
              {kpi.hint}
            </div>
          </div>
        ))}
      </section>

      {/* Main Grid */}
      <section className="grid gap-8 lg:grid-cols-3">
        {/* Planner Entry - Large Card */}
        <div className="lg:col-span-2 flex flex-col justify-between overflow-hidden rounded-[2rem] border border-neutral-100 bg-white p-8 shadow-sm relative group">
          <div className="absolute top-0 right-0 p-8 text-neutral-50/10 group-hover:text-orange-500/10 transition-colors pointer-events-none">
            <Layout className="h-64 w-64 rotate-12" />
          </div>
          
          <div className="relative z-10 space-y-4">
            <div className="inline-flex items-center rounded-full bg-orange-50 text-orange-600 px-4 py-1.5 text-xs font-bold uppercase tracking-wider border border-orange-100">
              New Project
            </div>
            <h2 className="font-heading text-4xl font-bold leading-[1.1] tracking-tight text-neutral-900 max-w-lg">
              Generate a high-density <br /> development scenario.
            </h2>
            <p className="max-w-md text-neutral-500 leading-relaxed">
              Pick your plot, define regulatory constraints, and allow our engines to compute the optimal architectural configuration.
            </p>
          </div>

          <div className="relative z-10 mt-12 flex items-center gap-6">
            <Link
              href="/planner/inputs"
              className="flex items-center gap-3 rounded-2xl bg-orange-500 px-8 py-4 text-sm font-bold text-white shadow-lg shadow-orange-500/30 transition-all hover:bg-orange-600 hover:-translate-y-0.5"
            >
              Launch Planner
              <ArrowRight className="h-4 w-4 stroke-[3px]" />
            </Link>
            <div className="hidden sm:block text-xs font-medium text-neutral-400">
              Regulatory check <span className="mx-2 text-neutral-200">|</span> 
              Envelope generation <span className="mx-2 text-neutral-200">|</span> 
              3D Layout
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="flex flex-col gap-4 rounded-[2rem] border border-neutral-100 bg-[#fbfbfb] p-8 shadow-inner">
          <div className="flex items-center justify-between">
            <h3 className="font-heading text-xl font-bold text-neutral-900 tracking-tight">Recent Scenarios</h3>
            <button className="text-xs font-bold text-orange-600 hover:text-orange-700">View all</button>
          </div>
          <div className="flex flex-col gap-3 mt-4">
            {[
              { id: "TP-14 · Max FSI", date: "2h ago", status: "Completed", color: "bg-emerald-500" },
              { id: "FP-133 · Multi-road", date: "5h ago", status: "Review", color: "bg-amber-400" },
              { id: "FP-108 · 2BHK Mix", date: "1d ago", status: "Draft", color: "bg-neutral-300" },
              { id: "GDCR-100 · Compliance", date: "2d ago", status: "Completed", color: "bg-emerald-500" },
              { id: "TP-21 · Commercial", date: "1w ago", status: "Archive", color: "bg-neutral-300" },
            ].map((row) => (
              <div
                key={row.id}
                className="flex items-center justify-between rounded-2xl bg-white p-4 text-sm shadow-sm transition-all hover:shadow-md"
              >
                <div className="flex flex-col">
                  <span className="font-bold text-neutral-900 tracking-tight">{row.id}</span>
                  <span className="text-[11px] font-medium text-neutral-400">{row.date}</span>
                </div>
                <div className="flex items-center gap-2">
                   <div className={`h-1.5 w-1.5 rounded-full ${row.color}`} />
                   <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-500">{row.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

