export default function DashboardPage() {
  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold text-neutral-900">
          Overview dashboard
        </h2>
        <p className="text-sm text-neutral-500">
          High-level summary of plots, site metrics, and recent development
          scenarios.
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-neutral-200 bg-white p-4 text-sm text-neutral-600">
          Key metrics will appear here (e.g., number of plots, average COP).
        </div>
        <div className="rounded-lg border border-neutral-200 bg-white p-4 text-sm text-neutral-600">
          Quick links into planner, recent plots, and saved scenarios.
        </div>
        <div className="rounded-lg border border-neutral-200 bg-white p-4 text-sm text-neutral-600">
          Activity feed or plan generation history.
        </div>
      </div>
    </section>
  );
}

