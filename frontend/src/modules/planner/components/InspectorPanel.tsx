"use client";

interface InspectorFeature {
  kind: "tower" | "cop" | "plot";
  properties: Record<string, unknown>;
}

interface InspectorPanelProps {
  selectedFeature: InspectorFeature;
  onClose: () => void;
}

export function InspectorPanel({ selectedFeature, onClose }: InspectorPanelProps) {
  const { kind, properties } = selectedFeature;

  const getNumber = (key: string): number | null => {
    const v = properties[key];
    const num = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
    return Number.isFinite(num) ? num : null;
  };

  const towerName =
    (properties.tower_name as string | undefined) ??
    (properties.name as string | undefined) ??
    (properties.label as string | undefined) ??
    "Tower";
  const floors =
    getNumber("floors") ??
    getNumber("n_floors") ??
    null;
  const heightM =
    getNumber("height_m") ??
    getNumber("building_height_m") ??
    getNumber("height") ??
    null;
  const footprintAreaSqft =
    getNumber("area_sqft") ??
    getNumber("footprint_area_sqft") ??
    null;
  const coreLayoutType =
    (properties.core_layout_type as string | undefined) ??
    (properties.coreType as string | undefined) ??
    null;

  const copAreaSqft =
    getNumber("area_sqft") ??
    getNumber("cop_area_sqft") ??
    null;
  const copMinDimM =
    getNumber("min_dimension_m") ??
    getNumber("cop_min_dimension_m") ??
    null;
  const copOk =
    typeof properties.cop_ok === "boolean"
      ? (properties.cop_ok as boolean)
      : copMinDimM == null
      ? null
      : copMinDimM >= 6;

  const plotAreaSqm =
    getNumber("plot_area_sqm") ??
    getNumber("plotAreaSqm") ??
    null;
  const buildableAreaSqft =
    getNumber("envelope_area_sqft") ??
    getNumber("buildable_area_sqft") ??
    null;
  const roadWidthM =
    getNumber("road_width_m") ??
    getNumber("roadWidthM") ??
    null;
  const maxFsi =
    getNumber("max_fsi") ??
    getNumber("maxFSI") ??
    null;

  return (
    <div className="flex h-full flex-col rounded-lg border border-neutral-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-neutral-200 px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-neutral-600">
          {kind === "tower"
            ? "Tower Inspector"
            : kind === "cop"
            ? "COP Inspector"
            : "Plot Inspector"}
        </h2>
        <button
          type="button"
          onClick={onClose}
          className="flex h-5 w-5 items-center justify-center rounded text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
          aria-label="Close inspector"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3 text-xs text-neutral-700">
        {kind === "tower" && (
          <>
            <section>
              <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
                Tower
              </h3>
              <div className="space-y-1">
                <Row label="Name" value={towerName} />
                {floors != null && <Row label="Floors" value={`${floors} F`} />}
                {heightM != null && <Row label="Height" value={`${heightM.toFixed(1)} m`} />}
                {footprintAreaSqft != null && (
                  <Row
                    label="Footprint"
                    value={`${Math.round(footprintAreaSqft * 0.0929)} m²  (${Math.round(footprintAreaSqft)} sqft)`}
                  />
                )}
                {(() => {
                  const wm = getNumber("width_m");
                  const dm = getNumber("depth_m");
                  if (wm == null || dm == null) return null;
                  return <Row label="Dimensions" value={`${wm.toFixed(1)} × ${dm.toFixed(1)} m`} />;
                })()}
                {(() => {
                  const bua = getNumber("bua_sqm");
                  if (bua == null) return null;
                  return <Row label="BUA (total)" value={`${Math.round(bua)} m²`} />;
                })()}
                {coreLayoutType && <Row label="Core Layout" value={coreLayoutType} />}
              </div>
            </section>
          </>
        )}

        {kind === "cop" && (
          <section>
            <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
              Common Open Plot
            </h3>
            <div className="space-y-1">
              {(() => {
                const sqm = getNumber("area_sqm") ?? (copAreaSqft != null ? Math.round(copAreaSqft * 0.0929) : null);
                return sqm != null ? <Row label="Area" value={`${Math.round(sqm)} m²`} /> : null;
              })()}
              {(() => {
                const wm = getNumber("width_m");
                const dm = getNumber("depth_m");
                if (wm == null || dm == null) return null;
                return <Row label="Dimensions" value={`${wm.toFixed(1)} × ${dm.toFixed(1)} m`} />;
              })()}
              {copMinDimM != null && (
                <Row label="Min Dimension" value={`${copMinDimM.toFixed(1)} m`} />
              )}
              {copOk != null && (
                <Row
                  label="GDCR Compliance"
                  value={copOk ? "✓ OK (≥ 7.5 m)" : "⚠ Violation (< 7.5 m)"}
                  valueClass={copOk ? "text-green-700" : "text-red-700 font-bold"}
                />
              )}
            </div>
          </section>
        )}

        {kind === "plot" && (
          <section>
            <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
              Plot
            </h3>
            <div className="space-y-1">
              {plotAreaSqm != null && (
                <Row label="Plot Area" value={`${Math.round(plotAreaSqm)} m²`} />
              )}
              {buildableAreaSqft != null && (
                <Row label="Buildable Area" value={`${Math.round(buildableAreaSqft)} sqft`} />
              )}
              {roadWidthM != null && (
                <Row label="Approach Road" value={`${roadWidthM.toFixed(1)} m`} />
              )}
              {maxFsi != null && (
                <Row label="FSI Allowed" value={maxFsi.toFixed(2)} />
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between rounded bg-neutral-50 px-2 py-1">
      <span className="text-[11px] text-neutral-500">{label}</span>
      <span className={`ml-2 text-[11px] font-medium text-neutral-900 ${valueClass ?? ""}`}>
        {value}
      </span>
    </div>
  );
}

