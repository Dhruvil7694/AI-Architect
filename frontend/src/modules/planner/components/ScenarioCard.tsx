"use client";

interface ScenarioCardProps {
  title: string;
  fsi?: number | null;
  floors?: number | null;
  openSpacePct?: number | null;
  copAreaSqm?: number | null;
  selected?: boolean;
  onClick?: () => void;
}

export function ScenarioCard({
  title,
  fsi,
  floors,
  openSpacePct,
  copAreaSqm,
  selected = false,
  onClick,
}: ScenarioCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex min-w-[140px] flex-col gap-2 rounded-md border px-3 py-2 text-left text-[11px] shadow-sm transition-colors ${
        selected
          ? "border-blue-600 bg-blue-50/80"
          : "border-neutral-200 bg-white hover:border-neutral-400"
      }`}
    >
      <div className="flex items-center justify-between">
        <span
          className={`text-[11px] font-semibold ${
            selected ? "text-blue-800" : "text-neutral-800"
          }`}
        >
          {title}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <Metric label="FSI" value={fsi != null ? fsi.toFixed(2) : "—"} />
        <Metric label="Floors" value={floors != null ? String(floors) : "—"} />
        <Metric
          label="Open Space"
          value={openSpacePct != null ? `${openSpacePct.toFixed(0)}%` : "—"}
        />
        <Metric
          label="COP Area"
          value={copAreaSqm != null ? `${Math.round(copAreaSqm)} m²` : "—"}
        />
      </div>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] text-neutral-400">{label}</span>
      <span className="text-[11px] font-medium text-neutral-800">{value}</span>
    </div>
  );
}

