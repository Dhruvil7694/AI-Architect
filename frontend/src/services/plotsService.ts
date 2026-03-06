import { httpRequest } from "./httpClient";

export interface PlotSummary {
  id: string;
  name: string;
  areaSqm: number;
  areaSqft?: number;
  roadWidthM?: number;
  /** Land-use tag from plan (e.g. "SALE FOR RESIDENTIAL", "S.E.W.S.H.", "PUBLIC PURPOSE") */
  designation?: string | null;
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
  } = {},
): Promise<(PlotSummary & { geometry?: unknown })[]> {
  const raw = await httpRequest<any>("/api/plots/", {
    method: "GET",
    searchParams: params,
  });

  const items: BackendPlotItem[] = Array.isArray(raw)
    ? raw
    : Array.isArray(raw?.results)
      ? raw.results
      : [];

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

