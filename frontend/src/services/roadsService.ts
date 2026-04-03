import { httpRequest } from "./httpClient";

export type RoadCenterlineGeometry = {
  type: "LineString" | "MultiLineString";
  coordinates: unknown;
};

export interface RoadSummary {
  id: number;
  name: string;
  widthM?: number | null;
  centerline?: RoadCenterlineGeometry | null;
  geometry?: unknown;
}

interface BackendRoadItem {
  id: number;
  name: string;
  widthM?: number | null;
  centerline?: RoadCenterlineGeometry | null;
  geometry?: unknown;
}

function mapBackendRoadToSummary(item: BackendRoadItem): RoadSummary {
  return {
    id: Number(item.id),
    name: item.name,
    widthM: item.widthM ?? null,
    centerline: item.centerline ?? null,
    geometry: item.geometry,
  };
}

export async function getRoads(params: { tp_scheme: string; city?: string }): Promise<RoadSummary[]> {
  const raw = await httpRequest<unknown>("/api/plots/roads/", {
    method: "GET",
    searchParams: {
      tp_scheme: params.tp_scheme,
      city: params.city,
    },
  });

  let items: BackendRoadItem[] = [];
  if (typeof raw === "object" && raw !== null) {
    const roadsRaw = (raw as { roads?: unknown }).roads;
    if (Array.isArray(roadsRaw)) {
      items = roadsRaw as BackendRoadItem[];
    }
  }
  return items.map(mapBackendRoadToSummary);
}

