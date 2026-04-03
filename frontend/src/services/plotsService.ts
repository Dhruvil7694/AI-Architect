import { httpRequest } from "./httpClient";

export interface PlotSummary {
  id: string;
  name: string;
  areaSqm: number;
  areaSqft?: number;
  labelPoint?: [number, number] | null;
  roadWidthM?: number;
  /** Land-use tag from plan (e.g. "SALE FOR RESIDENTIAL", "S.E.W.S.H.", "PUBLIC PURPOSE") */
  designation?: string | null;
  geometry?: unknown;
}

export interface PlotDetail extends PlotSummary {
  geometry?: unknown;
  metrics?: unknown;
}

/** Backend plot DTO shape (api/plots/ and api/v1/plots/) */
interface BackendPlotItem {
  id: string;
  name: string;
  areaSqm: number;
  labelPoint?: [number, number] | null;
  roadWidthM?: number | null;
  designation?: string | null;
  geometry?: unknown;
}

function mapBackendPlotToSummary(
  item: BackendPlotItem,
): PlotSummary & { geometry?: unknown } {
  const SQM_TO_SQFT = 10.7639;
  return {
    id: item.id,
    name: item.name,
    areaSqm: item.areaSqm,
    areaSqft: item.areaSqm * SQM_TO_SQFT,
    labelPoint: item.labelPoint ?? null,
    roadWidthM: item.roadWidthM ?? undefined,
    designation: item.designation ?? undefined,
    geometry: item.geometry,
  };
}

export async function getPlots(
  params: {
    search?: string;
    limit?: number;
    offset?: number;
    tpScheme?: string;
    city?: string;
  } = {},
): Promise<(PlotSummary & { geometry?: unknown })[]> {
  const raw = await httpRequest<unknown>("/api/plots/", {
    method: "GET",
    searchParams: {
      search: params.search,
      limit: params.limit,
      offset: params.offset,
      tp_scheme: params.tpScheme,
      city: params.city,
    },
  });

  let items: BackendPlotItem[] = [];
  if (Array.isArray(raw)) {
    items = raw as BackendPlotItem[];
  } else if (typeof raw === "object" && raw !== null) {
    const results = (raw as { results?: unknown }).results;
    if (Array.isArray(results)) {
      items = results as BackendPlotItem[];
    }
  }

  return items.map(mapBackendPlotToSummary);
}

export async function getPlotById(id: string): Promise<PlotDetail> {
  const raw = await httpRequest<BackendPlotItem>(
    `/api/plots/${encodeURIComponent(id)}/`,
    {
      method: "GET",
    },
  );
  const mapped = mapBackendPlotToSummary(raw);
  return {
    ...mapped,
    geometry: raw.geometry,
    metrics: undefined,
  };
}
