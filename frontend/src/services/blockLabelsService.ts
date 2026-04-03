import { httpRequest } from "./httpClient";

export type BlockLabelGeometry = {
  type: "Point";
  coordinates: [number, number];
};

export type BlockLabelSummary = {
  id: string;
  text: string;
  geometry?: BlockLabelGeometry;
  plotId?: string | null;
};

interface BackendBlockLabelItem {
  id: number | string;
  text: string;
  geometry?: BlockLabelGeometry;
  plotId?: string | null;
}

function mapBackendItemToSummary(item: BackendBlockLabelItem): BlockLabelSummary {
  return {
    id: String(item.id),
    text: item.text,
    geometry: item.geometry,
    plotId: item.plotId ?? null,
  };
}

export async function getBlockLabels(params: { tp_scheme?: string } = {}): Promise<BlockLabelSummary[]> {
  const raw = await httpRequest<unknown>("/api/block-labels/", {
    method: "GET",
    searchParams: params as Record<string, string | number | boolean | undefined>,
  });

  const items: BackendBlockLabelItem[] = Array.isArray(raw)
    ? raw
    : typeof raw === "object" &&
        raw !== null &&
        Array.isArray((raw as { results?: unknown }).results)
      ? ((raw as { results?: unknown }).results as BackendBlockLabelItem[])
      : [];

  return items.map(mapBackendItemToSummary);
}

