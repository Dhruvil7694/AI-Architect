import { httpRequest } from "./httpClient";
import { TP_MAP_COORD_SPACE } from "@/modules/planner/config/tpMapSpec";

export type FeatureCollection = GeoJSON.FeatureCollection;

export interface TpMapBundleMeta {
  tpScheme: string;
  city?: string | null;
  coordSpace: "LOCAL_DXF";
  srid: number;
  unitLinear: "foot";
  unitArea: "sqft";
  bbox: [number, number, number, number];
  ingestionVersion: string;
  source: {
    dxfFile: string | null;
    excelFile: string | null;
  };
}

export interface TpMapBundle {
  meta: TpMapBundleMeta;
  layers: {
    fpPolygons: FeatureCollection;
    fpLabelPoints: FeatureCollection;
    roads: FeatureCollection;
    roadCenterlines: FeatureCollection;
    blockLabels: FeatureCollection;
  };
  stats: {
    fpCount: number;
    roadCount: number;
    blockLabelCount: number;
  };
}

const DEFAULT_BBOX: [number, number, number, number] = [0, 0, 1, 1];

function emptyCollection(): FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}

function toFiniteNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function toOptionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function normalizeBBox(value: unknown): [number, number, number, number] {
  if (!Array.isArray(value) || value.length !== 4) return DEFAULT_BBOX;
  const minX = toFiniteNumber(value[0], 0);
  const minY = toFiniteNumber(value[1], 0);
  let maxX = toFiniteNumber(value[2], minX + 1);
  let maxY = toFiniteNumber(value[3], minY + 1);
  if (maxX <= minX) maxX = minX + 1;
  if (maxY <= minY) maxY = minY + 1;
  return [minX, minY, maxX, maxY];
}

function normalizeFeatureCollection(value: unknown): FeatureCollection {
  if (
    !value ||
    typeof value !== "object" ||
    (value as { type?: unknown }).type !== "FeatureCollection" ||
    !Array.isArray((value as { features?: unknown }).features)
  ) {
    return emptyCollection();
  }

  const features = (value as { features: unknown[] }).features.filter((feature) => {
    if (!feature || typeof feature !== "object") return false;
    const candidate = feature as { type?: unknown; geometry?: unknown };
    return candidate.type === "Feature" && !!candidate.geometry;
  }) as GeoJSON.Feature[];

  return {
    type: "FeatureCollection",
    features,
  };
}

function normalizeMeta(
  value: unknown,
  params: { tpScheme: string; city?: string },
): TpMapBundleMeta {
  const raw = (value && typeof value === "object" ? value : {}) as {
    tpScheme?: unknown;
    city?: unknown;
    coordSpace?: unknown;
    srid?: unknown;
    unitLinear?: unknown;
    unitArea?: unknown;
    bbox?: unknown;
    ingestionVersion?: unknown;
    source?: { dxfFile?: unknown; excelFile?: unknown } | unknown;
  };

  const source =
    raw.source && typeof raw.source === "object"
      ? (raw.source as { dxfFile?: unknown; excelFile?: unknown })
      : {};

  return {
    tpScheme:
      typeof raw.tpScheme === "string" && raw.tpScheme.trim().length > 0
        ? raw.tpScheme
        : params.tpScheme,
    city: typeof raw.city === "string" ? raw.city : params.city ?? null,
    coordSpace: raw.coordSpace === TP_MAP_COORD_SPACE ? raw.coordSpace : TP_MAP_COORD_SPACE,
    srid: toFiniteNumber(raw.srid, 0),
    unitLinear: raw.unitLinear === "foot" ? raw.unitLinear : "foot",
    unitArea: raw.unitArea === "sqft" ? raw.unitArea : "sqft",
    bbox: normalizeBBox(raw.bbox),
    ingestionVersion:
      typeof raw.ingestionVersion === "string" && raw.ingestionVersion.trim().length > 0
        ? raw.ingestionVersion
        : "v1",
    source: {
      dxfFile: toOptionalString(source.dxfFile),
      excelFile: toOptionalString(source.excelFile),
    },
  };
}

function normalizeStats(value: unknown): TpMapBundle["stats"] {
  const raw = (value && typeof value === "object" ? value : {}) as {
    fpCount?: unknown;
    roadCount?: unknown;
    blockLabelCount?: unknown;
  };

  return {
    fpCount: Math.max(0, Math.floor(toFiniteNumber(raw.fpCount, 0))),
    roadCount: Math.max(0, Math.floor(toFiniteNumber(raw.roadCount, 0))),
    blockLabelCount: Math.max(0, Math.floor(toFiniteNumber(raw.blockLabelCount, 0))),
  };
}

function hasAnyGeometryLayers(bundle: TpMapBundle): boolean {
  return (
    bundle.layers.fpPolygons.features.length > 0 ||
    bundle.layers.roads.features.length > 0 ||
    bundle.layers.roadCenterlines.features.length > 0 ||
    bundle.layers.blockLabels.features.length > 0
  );
}

function normalizeBundle(raw: unknown, params: { tpScheme: string; city?: string }): TpMapBundle {
  const data = (raw && typeof raw === "object" ? raw : {}) as {
    meta?: unknown;
    layers?: Record<string, unknown>;
    stats?: unknown;
  };

  const meta = normalizeMeta(data.meta, params);

  return {
    meta,
    layers: {
      fpPolygons: normalizeFeatureCollection(data.layers?.fpPolygons),
      fpLabelPoints: normalizeFeatureCollection(data.layers?.fpLabelPoints),
      roads: normalizeFeatureCollection(data.layers?.roads),
      roadCenterlines: normalizeFeatureCollection(data.layers?.roadCenterlines),
      blockLabels: normalizeFeatureCollection(data.layers?.blockLabels),
    },
    stats: normalizeStats(data.stats),
  };
}

export async function getTpMapBundle(params: {
  tpScheme: string;
  city?: string;
}): Promise<TpMapBundle> {
  const endpoints = ["/api/map/tp-bundle/", "/api/v1/map/tp-bundle/"];

  // 1) Primary fetch with current city filter.
  for (const endpoint of endpoints) {
    try {
      const raw = await httpRequest<unknown>(endpoint, {
        method: "GET",
        searchParams: {
          tp_scheme: params.tpScheme,
          city: params.city,
        },
      });
      const bundle = normalizeBundle(raw, params);
      if (hasAnyGeometryLayers(bundle) || !params.city) {
        return bundle;
      }
    } catch {
      // try next endpoint/fallback mode
    }
  }

  // 2) Fallback fetch without city to avoid over-filtering.
  for (const endpoint of endpoints) {
    try {
      const raw = await httpRequest<unknown>(endpoint, {
        method: "GET",
        searchParams: {
          tp_scheme: params.tpScheme,
        },
      });
      return normalizeBundle(raw, { tpScheme: params.tpScheme });
    } catch {
      // keep trying fallbacks
    }
  }

  // 3) Surface the original failure state if all requests fail.
  return {
    meta: normalizeMeta(undefined, params),
    layers: {
      fpPolygons: emptyCollection(),
      fpLabelPoints: emptyCollection(),
      roads: emptyCollection(),
      roadCenterlines: emptyCollection(),
      blockLabels: emptyCollection(),
    },
    stats: { fpCount: 0, roadCount: 0, blockLabelCount: 0 },
  };
}
