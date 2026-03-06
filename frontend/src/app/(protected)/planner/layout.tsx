import type { ReactNode } from "react";

type PlannerLayoutProps = {
  children: ReactNode;
};

export default function PlannerLayout({ children }: PlannerLayoutProps) {
  return (
    <div className="flex h-full flex-col gap-2">
      <header className="flex items-center justify-between rounded-md border border-neutral-200 bg-white px-4 py-2">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900">Planner</h2>
          <p className="text-xs text-neutral-500">
            Select plots, adjust development inputs, and generate scenarios.
          </p>
        </div>
        <div className="text-xs text-neutral-500">
          {/* PlanGenerationStatus and scenario controls mount here later */}
          Status · Scenarios
        </div>
      </header>
      <div className="flex min-h-0 flex-1 gap-2">{children}</div>
    </div>
  );
}

