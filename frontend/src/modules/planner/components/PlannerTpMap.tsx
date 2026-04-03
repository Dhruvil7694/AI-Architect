"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type LngLatBoundsLike } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { usePlannerStore } from "@/state/plannerStore";
import { formatArea } from "@/lib/units";
import { useTpMapBundle } from "@/modules/plots/hooks/useTpMapBundle";
import type { TpMapBundle } from "@/services/tpMapService";
import {
  TP_FP_MAJOR_AREA_SQM_MIN,
  TP_LABEL_DEFAULT_VISIBILITY,
  TP_MAP_ANCHOR,
  TP_MAP_LAYER_IDS,
  TP_MAP_SOURCE_IDS,
  TP_MAP_ZOOM_MATRIX,
} from "@/modules/planner/config/tpMapSpec";

type Coord = [number, number];

type PlotMapRecord = {
  id: string;
  name: string;
  areaSqm: number;
  roadWidthM: number | null;
  designation: string;
};

type LabelVisibility = {
  fp: boolean;
  road: boolean;
  block: boolean;
};

type NormalizedMapData = {
  scopeKey: string;
  bounds: LngLatBoundsLike;
  plots: GeoJSON.FeatureCollection;
  fpLabels: GeoJSON.FeatureCollection;
  roadPolygons: GeoJSON.FeatureCollection;
  roadCenterlines: GeoJSON.FeatureCollection;
  roadLabelPoints: GeoJSON.FeatureCollection;
  blockLabels: GeoJSON.FeatureCollection;
  plotById: Map<string, PlotMapRecord>;
};

function flattenCoords(input: unknown): Coord[] {
  const out: Coord[] = [];
  const walk = (node: unknown) => {
    if (!Array.isArray(node)) return;
    if (node.length >= 2 && typeof node[0] === "number" && typeof node[1] === "number") {
      out.push([Number(node[0]), Number(node[1])]);
      return;
    }
    for (const child of node) walk(child);
  };
  walk(input);
  return out;
}

function inferKind(designation?: string | null): string {
  const d = (designation ?? "").toUpperCase();
  if (d.includes("ROAD")) return "road";
  if (d.includes("RESIDENTIAL") || d.includes("SALE FOR RES")) return "residential";
  if (d.includes("COMMERCIAL") || d.includes("SALE FOR COM")) return "commercial";
  if (d.includes("PUBLIC")) return "public";
  if (d.includes("OPEN SPACE") || d.includes("GARDEN")) return "open_space";
  if (d.includes("S.E.W") || d.includes("SEWAGE") || d.includes("E.W.S")) return "sewage";
  return "other";
}

function mapPointCoord(input: unknown, toMapCoord: (c: Coord) => Coord): Coord | null {
  if (!Array.isArray(input) || input.length < 2) return null;
  if (typeof input[0] !== "number" || typeof input[1] !== "number") return null;
  return toMapCoord([Number(input[0]), Number(input[1])]);
}

function mapLineCoords(input: unknown, toMapCoord: (c: Coord) => Coord): Coord[] | null {
  if (!Array.isArray(input)) return null;
  const out: Coord[] = [];
  for (const pt of input) {
    const mapped = mapPointCoord(pt, toMapCoord);
    if (mapped) out.push(mapped);
  }
  return out.length >= 2 ? out : null;
}

function mapPolygonCoords(
  input: unknown,
  toMapCoord: (c: Coord) => Coord,
): Coord[][] | null {
  if (!Array.isArray(input)) return null;
  const out: Coord[][] = [];
  for (const ring of input) {
    const mapped = mapLineCoords(ring, toMapCoord);
    if (mapped && mapped.length >= 4) out.push(mapped);
  }
  return out.length > 0 ? out : null;
}

function mapGeometry(
  geometry: unknown,
  toMapCoord: (c: Coord) => Coord,
): GeoJSON.Geometry | null {
  const g = geometry as { type?: string; coordinates?: unknown };
  if (!g?.type || g.coordinates == null) return null;

  switch (g.type) {
    case "Point": {
      const coords = mapPointCoord(g.coordinates, toMapCoord);
      return coords ? ({ type: "Point", coordinates: coords } as GeoJSON.Point) : null;
    }
    case "LineString": {
      const coords = mapLineCoords(g.coordinates, toMapCoord);
      return coords ? ({ type: "LineString", coordinates: coords } as GeoJSON.LineString) : null;
    }
    case "MultiLineString": {
      if (!Array.isArray(g.coordinates)) return null;
      const lines: Coord[][] = [];
      for (const line of g.coordinates) {
        const mapped = mapLineCoords(line, toMapCoord);
        if (mapped) lines.push(mapped);
      }
      return lines.length
        ? ({ type: "MultiLineString", coordinates: lines } as GeoJSON.MultiLineString)
        : null;
    }
    case "Polygon": {
      const coords = mapPolygonCoords(g.coordinates, toMapCoord);
      return coords ? ({ type: "Polygon", coordinates: coords } as GeoJSON.Polygon) : null;
    }
    case "MultiPolygon": {
      if (!Array.isArray(g.coordinates)) return null;
      const polys: Coord[][][] = [];
      for (const poly of g.coordinates) {
        const mapped = mapPolygonCoords(poly, toMapCoord);
        if (mapped) polys.push(mapped);
      }
      return polys.length
        ? ({ type: "MultiPolygon", coordinates: polys } as GeoJSON.MultiPolygon)
        : null;
    }
    default:
      return null;
  }
}

function normalizeMapData(bundle?: TpMapBundle): NormalizedMapData | null {
  if (!bundle) return null;

  let [minX, minY, maxX, maxY] = bundle.meta.bbox;
  const hasValidBBox =
    Number.isFinite(minX) &&
    Number.isFinite(minY) &&
    Number.isFinite(maxX) &&
    Number.isFinite(maxY) &&
    maxX > minX &&
    maxY > minY;

  if (!hasValidBBox) {
    const allCoords = [
      ...bundle.layers.fpPolygons.features.flatMap((f) =>
        flattenCoords((f.geometry as { coordinates?: unknown } | null)?.coordinates),
      ),
      ...bundle.layers.roads.features.flatMap((f) =>
        flattenCoords((f.geometry as { coordinates?: unknown } | null)?.coordinates),
      ),
      ...bundle.layers.roadCenterlines.features.flatMap((f) =>
        flattenCoords((f.geometry as { coordinates?: unknown } | null)?.coordinates),
      ),
      ...bundle.layers.blockLabels.features.flatMap((f) =>
        flattenCoords((f.geometry as { coordinates?: unknown } | null)?.coordinates),
      ),
    ];
    if (!allCoords.length) return null;

    const xs = allCoords.map((c) => c[0]);
    const ys = allCoords.map((c) => c[1]);
    minX = Math.min(...xs);
    maxX = Math.max(...xs);
    minY = Math.min(...ys);
    maxY = Math.max(...ys);
  }

  const dx = Math.max(1e-6, maxX - minX);
  const dy = Math.max(1e-6, maxY - minY);

  const lng0 = TP_MAP_ANCHOR.lng;
  const lat0 = TP_MAP_ANCHOR.lat;
  const spanLng = TP_MAP_ANCHOR.spanLng;
  const spanLat = spanLng * (dy / dx);

  const toMapCoord = (c: Coord): Coord => [
    lng0 + ((c[0] - minX) / dx) * spanLng,
    lat0 + ((c[1] - minY) / dy) * spanLat,
  ];

  const plotById = new Map<string, PlotMapRecord>();
  const plotFeatures: GeoJSON.Feature[] = [];
  for (const feature of bundle.layers.fpPolygons.features) {
    const mappedGeometry = mapGeometry(feature.geometry, toMapCoord);
    if (!mappedGeometry) continue;
    const properties = (feature.properties ?? {}) as Record<string, unknown>;
    const plotId = String(properties.plotId ?? feature.id ?? "");
    if (!plotId) continue;
    const name = String(properties.name ?? plotId);
    const areaSqm = Number(properties.areaSqm ?? 0);
    const roadWidthRaw = properties.roadWidthM;
    const roadWidthM =
      typeof roadWidthRaw === "number" && Number.isFinite(roadWidthRaw)
        ? roadWidthRaw
        : null;
    const designation = String(properties.designation ?? "");
    const fpLabel = String(properties.fpLabel ?? name.replace(/^FP\s*/i, ""));

    plotById.set(plotId, {
      id: plotId,
      name,
      areaSqm: Number.isFinite(areaSqm) ? areaSqm : 0,
      roadWidthM,
      designation,
    });

    plotFeatures.push({
      type: "Feature",
      id: plotId,
      geometry: mappedGeometry,
      properties: {
        plotId,
        name,
        fpLabel,
        areaSqm,
        designation,
        roadWidthM,
        kind: inferKind(designation),
      },
    });
  }

  const fpLabelFeatures: GeoJSON.Feature[] = [];
  for (const feature of bundle.layers.fpLabelPoints.features) {
    const mappedGeometry = mapGeometry(feature.geometry, toMapCoord);
    if (!mappedGeometry || mappedGeometry.type !== "Point") continue;
    const properties = (feature.properties ?? {}) as Record<string, unknown>;
    const plotId = String(properties.plotId ?? "");
    const fallbackPlot = plotId ? plotById.get(plotId) : null;
    fpLabelFeatures.push({
      type: "Feature",
      id: String(feature.id ?? `${plotId}-label`),
      geometry: mappedGeometry,
      properties: {
        plotId,
        fpLabel: String(properties.fpLabel ?? fallbackPlot?.name?.replace(/^FP\s*/i, "") ?? ""),
        areaSqm: Number(properties.areaSqm ?? fallbackPlot?.areaSqm ?? 0),
      },
    });
  }

  const roadPolygonFeatures: GeoJSON.Feature[] = [];
  for (const feature of bundle.layers.roads.features) {
    const mappedGeometry = mapGeometry(feature.geometry, toMapCoord);
    if (!mappedGeometry) continue;
    roadPolygonFeatures.push({
      type: "Feature",
      id: feature.id ?? undefined,
      geometry: mappedGeometry,
      properties: feature.properties ?? {},
    });
  }

  const roadCenterlineFeatures: GeoJSON.Feature[] = [];
  for (const feature of bundle.layers.roadCenterlines.features) {
    const mappedGeometry = mapGeometry(feature.geometry, toMapCoord);
    if (!mappedGeometry) continue;
    roadCenterlineFeatures.push({
      type: "Feature",
      id: feature.id ?? undefined,
      geometry: mappedGeometry,
      properties: feature.properties ?? {},
    });
  }

  // Build road label points from POLYGON geometry (not centerlines).
  // Strategy: group by label text, pick the most road-shaped polygon per
  // group (highest aspect ratio), use the oriented bounding box center as
  // the label position.  This avoids centroids landing on plots for
  // concave/L-shaped road polygons and deduplicates labels.
  type RoadCandidate = {
    feature: GeoJSON.Feature;
    ring: Coord[];
    aspectRatio: number;
    area: number;
    angle: number;       // PCA principal axis (radians)
    center: Coord;       // oriented bbox center
  };

  const candidatesByLabel = new Map<string, RoadCandidate[]>();

  for (const feature of roadPolygonFeatures) {
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const label = String(props.label ?? props.name ?? "");
    if (!label) continue;

    const geom = feature.geometry as { type?: string; coordinates?: unknown };
    let ring: Coord[] = [];
    if (geom.type === "Polygon" && Array.isArray(geom.coordinates)) {
      const outerRing = geom.coordinates[0];
      if (Array.isArray(outerRing)) {
        for (const pt of outerRing) {
          if (Array.isArray(pt) && pt.length >= 2) ring.push([pt[0], pt[1]]);
        }
      }
    } else if (geom.type === "MultiPolygon" && Array.isArray(geom.coordinates)) {
      let maxA = 0;
      for (const poly of geom.coordinates) {
        if (!Array.isArray(poly) || !Array.isArray(poly[0])) continue;
        const r = poly[0] as Coord[];
        let a = 0;
        for (let i = 0; i < r.length - 1; i++) {
          a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
        }
        if (Math.abs(a) > maxA) {
          maxA = Math.abs(a);
          ring = r.map((p: number[]) => [p[0], p[1]] as Coord);
        }
      }
    }
    if (ring.length < 4) continue;

    // PCA principal axis
    let meanX = 0, meanY = 0;
    for (const p of ring) { meanX += p[0]; meanY += p[1]; }
    meanX /= ring.length;
    meanY /= ring.length;
    let cxx = 0, cyy = 0, cxy = 0;
    for (const p of ring) {
      const ddx = p[0] - meanX;
      const ddy = p[1] - meanY;
      cxx += ddx * ddx;
      cyy += ddy * ddy;
      cxy += ddx * ddy;
    }
    const angle = Math.atan2(2 * cxy, cxx - cyy) / 2;

    // Project ring onto principal axis to get oriented bounding box
    const cosA = Math.cos(angle);
    const sinA = Math.sin(angle);
    let minU = Infinity, maxU = -Infinity, minV = Infinity, maxV = -Infinity;
    for (const p of ring) {
      const u = (p[0] - meanX) * cosA + (p[1] - meanY) * sinA;
      const v = -(p[0] - meanX) * sinA + (p[1] - meanY) * cosA;
      if (u < minU) minU = u;
      if (u > maxU) maxU = u;
      if (v < minV) minV = v;
      if (v > maxV) maxV = v;
    }
    const obbLength = maxU - minU;
    const obbWidth = maxV - minV;
    const aspectRatio = obbWidth > 1e-9 ? obbLength / obbWidth : 1;

    // Oriented bbox center (projected back to map coords)
    const uMid = (minU + maxU) / 2;
    const vMid = (minV + maxV) / 2;
    const center: Coord = [
      meanX + uMid * cosA - vMid * sinA,
      meanY + uMid * sinA + vMid * cosA,
    ];

    // Polygon area (shoelace)
    let polyArea = 0;
    for (let i = 0; i < ring.length - 1; i++) {
      polyArea += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
    }
    polyArea = Math.abs(polyArea) / 2;

    const list = candidatesByLabel.get(label) ?? [];
    list.push({ feature, ring, aspectRatio, area: polyArea, angle, center });
    candidatesByLabel.set(label, list);
  }

  const roadLabelPointFeatures: GeoJSON.Feature[] = [];
  for (const [label, candidates] of candidatesByLabel) {
    // Pick the candidate with the highest aspect ratio (most road-shaped).
    // Skip if best aspect ratio < 1.5 (blob-like, not a real road strip).
    const best = candidates.reduce((a, b) => (b.aspectRatio > a.aspectRatio ? b : a));
    if (best.aspectRatio < 1.5) continue;

    let angleDeg = -(best.angle * 180) / Math.PI;
    if (angleDeg > 90) angleDeg -= 180;
    if (angleDeg < -90) angleDeg += 180;

    const props = (best.feature.properties ?? {}) as Record<string, unknown>;
    roadLabelPointFeatures.push({
      type: "Feature",
      id: `${best.feature.id ?? ""}-label`,
      geometry: { type: "Point", coordinates: best.center },
      properties: {
        ...props,
        rotation: angleDeg,
      },
    });
  }

  const blockLabelFeatures: GeoJSON.Feature[] = [];
  for (const feature of bundle.layers.blockLabels.features) {
    const mappedGeometry = mapGeometry(feature.geometry, toMapCoord);
    if (!mappedGeometry || mappedGeometry.type !== "Point") continue;
    blockLabelFeatures.push({
      type: "Feature",
      id: feature.id ?? undefined,
      geometry: mappedGeometry,
      properties: feature.properties ?? {},
    });
  }

  return {
    scopeKey: `${bundle.meta.tpScheme}|${bundle.meta.city ?? ""}`,
    bounds: [
      [lng0 - 0.002, lat0 - 0.002],
      [lng0 + spanLng + 0.002, lat0 + spanLat + 0.002],
    ],
    plots: { type: "FeatureCollection", features: plotFeatures },
    fpLabels: { type: "FeatureCollection", features: fpLabelFeatures },
    roadPolygons: { type: "FeatureCollection", features: roadPolygonFeatures },
    roadCenterlines: { type: "FeatureCollection", features: roadCenterlineFeatures },
    roadLabelPoints: { type: "FeatureCollection", features: roadLabelPointFeatures },
    blockLabels: { type: "FeatureCollection", features: blockLabelFeatures },
    plotById,
  };
}

function MapTooltip({ plot, x, y }: { plot: PlotMapRecord; x: number; y: number }) {
  return (
    <div
      className="fixed z-[60] min-w-[220px] max-w-[300px] rounded-xl border border-neutral-200 bg-white px-3.5 py-2.5 text-left shadow-xl pointer-events-none"
      style={{ left: x + 14, top: y + 10 }}
    >
      <div className="flex items-center justify-between border-b border-neutral-100 pb-1.5">
        <span className="font-bold text-sm text-neutral-900">{plot.name}</span>
      </div>
      <div className="mt-1.5 space-y-0.5 text-xs text-neutral-600">
        <div className="flex justify-between">
          <span>Area</span>
          <span className="font-semibold text-neutral-800">{formatArea(plot.areaSqm, "sqft")}</span>
        </div>
        {plot.roadWidthM != null && (
          <div className="flex justify-between">
            <span>Road</span>
            <span className="font-semibold text-neutral-800">{plot.roadWidthM} m</span>
          </div>
        )}
      </div>
      <div className="mt-2 text-[10px] text-center text-orange-500 font-semibold">Click to select</div>
    </div>
  );
}

export function PlannerTpMap() {
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const tpScheme = locationPreference.tpId;
  const city = locationPreference.districtName;

  const { data: bundle, isLoading, isError } = useTpMapBundle(tpScheme, city);
  const mapData = useMemo(() => normalizeMapData(bundle), [bundle]);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const lastFitScopeRef = useRef<string>("");
  const handlersRef = useRef<{
    onMove?: (e: maplibregl.MapMouseEvent) => void;
    onLeave?: () => void;
    onClick?: (e: maplibregl.MapMouseEvent) => void;
    onZoom?: () => void;
  }>({});

  const [hoveredPlot, setHoveredPlot] = useState<PlotMapRecord | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [mapZoom, setMapZoom] = useState<number>(0);
  const [labelVisibility, setLabelVisibility] = useState<LabelVisibility>(TP_LABEL_DEFAULT_VISIBILITY);

  // Track when the MapLibre Map is fully loaded and ready for sources/layers.
  // This state bridges the init effect ([] deps) with the data-setup effect
  // so the latter re-runs once the map is available.
  const [mapReady, setMapReady] = useState(false);

  // --- Map initialisation --------------------------------------------------
  // MapLibre overrides `position: absolute` on the container to `relative`,
  // which breaks `inset-0` height resolution (collapses to 0).
  // Fix: observe the WRAPPER (which keeps absolute positioning) and explicitly
  // set the container's pixel width/height from the wrapper dimensions.
  useEffect(() => {
    const wrapper = wrapperRef.current;
    const el = containerRef.current;
    if (!wrapper || !el) return;

    let disposed = false;

    // Sync container pixel size from the wrapper (which has correct CSS dims)
    const syncSize = () => {
      const w = wrapper.clientWidth;
      const h = wrapper.clientHeight;
      if (w > 0 && h > 0) {
        el.style.width = `${w}px`;
        el.style.height = `${h}px`;
      }
    };

    const createMap = () => {
      if (disposed || mapRef.current) return;
      syncSize();
      if (el.clientWidth === 0 || el.clientHeight === 0) return;

      const map = new maplibregl.Map({
        container: el,
        style: {
          version: 8,
          glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
          sources: {},
          layers: [{ id: "bg", type: "background", paint: { "background-color": "#ffffff" } }],
        },
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      mapRef.current = map;

      const markReady = () => {
        if (!disposed) {
          syncSize();
          map.resize();
          setMapReady(true);
        }
      };
      map.once("load", markReady);
      if (map.loaded()) markReady();

      map.on("error", (e) => {
        console.error("[PlannerTpMap] map error:", e);
      });
    };

    createMap();

    // Observe the WRAPPER (not the container) — it retains correct CSS dims
    const ro = new ResizeObserver(() => {
      syncSize();
      if (!mapRef.current) createMap();
      else mapRef.current.resize();
    });
    ro.observe(wrapper);

    return () => {
      disposed = true;
      ro.disconnect();
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
      setMapReady(false);
    };
  }, []);

  // --- Data setup ----------------------------------------------------------
  // Adds/updates sources, layers, event handlers and fits bounds.
  // Re-runs when data arrives OR when the map becomes ready (whichever is last).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapData || !mapReady) return;

    const plotSourceId = TP_MAP_SOURCE_IDS.plots;
    const fpLabelSourceId = TP_MAP_SOURCE_IDS.fpLabels;
    const roadPolySourceId = TP_MAP_SOURCE_IDS.roadPolygons;
    const roadCenterlineSourceId = TP_MAP_SOURCE_IDS.roadCenterlines;
    const roadLabelPtsSourceId = TP_MAP_SOURCE_IDS.roadLabelPoints;
    const blockLabelSourceId = TP_MAP_SOURCE_IDS.blockLabels;

    // Helper: safe addSource (skip if already exists)
    const ensureSource = (id: string, data: GeoJSON.FeatureCollection, opts?: { promoteId?: string }) => {
      const existing = map.getSource(id) as GeoJSONSource | undefined;
      if (existing) { existing.setData(data); return; }
      map.addSource(id, { type: "geojson", data, ...(opts ?? {}) });
    };

    ensureSource(plotSourceId, mapData.plots, { promoteId: "plotId" });
    ensureSource(fpLabelSourceId, mapData.fpLabels);
    ensureSource(roadPolySourceId, mapData.roadPolygons);
    ensureSource(roadCenterlineSourceId, mapData.roadCenterlines);
    ensureSource(roadLabelPtsSourceId, mapData.roadLabelPoints);
    ensureSource(blockLabelSourceId, mapData.blockLabels);

    // Helper: safe addLayer — swallow errors so one bad layer doesn't block the rest
    const safeAddLayer = (spec: Parameters<typeof map.addLayer>[0]) => {
      if (map.getLayer(spec.id)) return;
      try { map.addLayer(spec); }
      catch (err) { console.error(`[PlannerTpMap] addLayer "${spec.id}" failed:`, err); }
    };

    safeAddLayer({
      id: TP_MAP_LAYER_IDS.plotFill,
      type: "fill",
      source: plotSourceId,
      filter: ["!=", ["get", "kind"], "road"],
      paint: {
        "fill-color": [
          "match", ["get", "kind"],
          "residential", "#f8d7da",
          "commercial", "#fff3b0",
          "public", "#fde68a",
          "open_space", "#bbf7d0",
          "sewage", "#fde8c8",
          "#f5f5f4",
        ],
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0.48, 14, 0.58, 18, 0.66],
      },
    });
    safeAddLayer({
      id: TP_MAP_LAYER_IDS.plotOutline,
      type: "line",
      source: plotSourceId,
      filter: ["!=", ["get", "kind"], "road"],
      paint: {
        "line-color": "#9f1239",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.7, 16, 1.15],
        "line-opacity": 0.82,
      },
    });
    safeAddLayer({
      id: TP_MAP_LAYER_IDS.plotOutlineSelected,
      type: "line",
      source: plotSourceId,
      filter: ["==", ["get", "plotId"], selectedPlotId ?? ""],
      paint: { "line-color": "#ea580c", "line-width": 2.8 },
    });

    safeAddLayer({
      id: TP_MAP_LAYER_IDS.fpLabelMajor,
      type: "symbol",
      source: fpLabelSourceId,
      minzoom: TP_MAP_ZOOM_MATRIX.fpMajorMin,
      maxzoom: TP_MAP_ZOOM_MATRIX.fpAllMin,
      filter: [">=", ["coalesce", ["get", "areaSqm"], 0], TP_FP_MAJOR_AREA_SQM_MIN],
      layout: {
        "text-field": ["get", "fpLabel"],
        "text-size": ["interpolate", ["linear"], ["zoom"], TP_MAP_ZOOM_MATRIX.fpMajorMin, 9, 12, 10],
        "text-font": ["Open Sans Semibold"],
        "text-allow-overlap": false,
        "text-ignore-placement": false,
        "text-padding": 4,
        "symbol-sort-key": ["*", -1, ["coalesce", ["get", "areaSqm"], 0]],
      },
      paint: {
        "text-color": "#1f2937",
        "text-halo-color": "#ffffff",
        "text-halo-width": 2,
        "text-halo-blur": 0.35,
      },
    });

    safeAddLayer({
      id: TP_MAP_LAYER_IDS.fpLabelAll,
      type: "symbol",
      source: fpLabelSourceId,
      minzoom: TP_MAP_ZOOM_MATRIX.fpAllMin,
      layout: {
        "text-field": ["get", "fpLabel"],
        "text-size": ["interpolate", ["linear"], ["zoom"], TP_MAP_ZOOM_MATRIX.fpAllMin, 7, 15, 10, 18, 12],
        "text-font": ["Open Sans Semibold"],
        "text-allow-overlap": false,
        "text-ignore-placement": false,
        "text-padding": 4,
        "symbol-sort-key": ["*", -1, ["coalesce", ["get", "areaSqm"], 0]],
      },
      paint: {
        "text-color": "#1f2937",
        "text-halo-color": "#ffffff",
        "text-halo-width": 2,
        "text-halo-blur": 0.35,
      },
    });

    safeAddLayer({
      id: TP_MAP_LAYER_IDS.roadLabel,
      type: "symbol",
      source: roadLabelPtsSourceId,
      minzoom: TP_MAP_ZOOM_MATRIX.roadLabelsMin,
      filter: ["!=", ["coalesce", ["get", "label"], ""], ""],
      layout: {
        "symbol-placement": "point",
        "text-field": ["get", "label"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 11, 8, 13, 10, 16, 12, 18, 14],
        "text-font": ["Open Sans Semibold"],
        "text-rotate": ["get", "rotation"],
        "text-rotation-alignment": "map",
        "text-allow-overlap": true,
        "text-ignore-placement": true,
      },
      paint: {
        "text-color": "#7c2d12",
        "text-halo-color": "#ffffff",
        "text-halo-width": 2,
        "text-halo-blur": 0.5,
      },
    });

    safeAddLayer({
      id: TP_MAP_LAYER_IDS.blockLabel,
      type: "symbol",
      source: blockLabelSourceId,
      minzoom: TP_MAP_ZOOM_MATRIX.blockLabelsMin,
      layout: {
        "text-field": ["get", "text"],
        "text-size": ["interpolate", ["linear"], ["zoom"], TP_MAP_ZOOM_MATRIX.blockLabelsMin, 8, 18, 11],
        "text-font": ["Open Sans Semibold"],
        "text-allow-overlap": false,
        "text-ignore-placement": false,
        "text-padding": 4,
      },
      paint: { "text-color": "#4b5563", "text-halo-color": "#ffffff", "text-halo-width": 1.8 },
    });

    // Resize + fitBounds — use requestAnimationFrame to ensure the container
    // has its final CSS dimensions before MapLibre calculates the viewport.
    // This is the most common cause of blank maps in Next.js / React layouts
    // where the flex/absolute container may not be sized on the same tick.
    const scopeKey = mapData.scopeKey;
    const doFit = () => {
      if (!mapRef.current) return;
      // Re-sync container size from wrapper before fitting
      const w = wrapperRef.current;
      const c = containerRef.current;
      if (w && c) {
        c.style.width = `${w.clientWidth}px`;
        c.style.height = `${w.clientHeight}px`;
      }
      mapRef.current.resize();
      // Only re-fit bounds when the TP scope changes, not on every plot selection
      if (lastFitScopeRef.current !== scopeKey) {
        lastFitScopeRef.current = scopeKey;
        mapRef.current.fitBounds(mapData.bounds, { padding: 36, duration: 0, maxZoom: 18 });
      }
    };
    // Double-RAF ensures layout is flushed (React commit → browser paint → RAF → RAF)
    requestAnimationFrame(() => requestAnimationFrame(doFit));

    if (handlersRef.current.onMove) map.off("mousemove", handlersRef.current.onMove);
    if (handlersRef.current.onLeave) map.off("mouseleave", handlersRef.current.onLeave);
    if (handlersRef.current.onClick) map.off("click", handlersRef.current.onClick);
    if (handlersRef.current.onZoom) map.off("zoom", handlersRef.current.onZoom);

    const onMove = (e: maplibregl.MapMouseEvent) => {
      const feature = map.queryRenderedFeatures(e.point, { layers: [TP_MAP_LAYER_IDS.plotFill] })[0];
      const plotId = (feature?.properties?.plotId as string | undefined) ?? null;
      if (plotId && mapData.plotById.has(plotId)) {
        map.getCanvas().style.cursor = "pointer";
        setHoveredPlot(mapData.plotById.get(plotId) ?? null);
        setTooltipPos({ x: e.originalEvent.clientX, y: e.originalEvent.clientY });
      } else {
        map.getCanvas().style.cursor = "";
        setHoveredPlot(null);
      }
    };
    const onLeave = () => { map.getCanvas().style.cursor = ""; setHoveredPlot(null); };
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const feature = map.queryRenderedFeatures(e.point, { layers: [TP_MAP_LAYER_IDS.plotFill] })[0];
      const plotId = feature?.properties?.plotId as string | undefined;
      if (plotId) setSelectedPlotId(plotId);
    };
    const onZoom = () => setMapZoom(map.getZoom());

    handlersRef.current = { onMove, onLeave, onClick, onZoom };
    map.on("mousemove", onMove);
    map.on("mouseleave", onLeave);
    map.on("click", onClick);
    map.on("zoom", onZoom);
    setMapZoom(map.getZoom());
  }, [mapData, mapReady, selectedPlotId, setSelectedPlotId]);

  // --- Label visibility toggling -------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const setVis = (layer: string, vis: boolean) => {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", vis ? "visible" : "none");
    };
    setVis(TP_MAP_LAYER_IDS.fpLabelMajor, labelVisibility.fp);
    setVis(TP_MAP_LAYER_IDS.fpLabelAll, labelVisibility.fp);
    setVis(TP_MAP_LAYER_IDS.roadLabel, labelVisibility.road);
    setVis(TP_MAP_LAYER_IDS.blockLabel, labelVisibility.block);
  }, [labelVisibility, mapReady]);

  // --- Selected plot highlight ---------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.getLayer(TP_MAP_LAYER_IDS.plotOutlineSelected)) return;
    map.setFilter(TP_MAP_LAYER_IDS.plotOutlineSelected, ["==", ["get", "plotId"], selectedPlotId ?? ""]);
  }, [selectedPlotId, mapReady]);

  // Always render the map container so MapLibre can attach on first mount.
  // Loading / error states are shown as overlays on top of the canvas.
  return (
    <div ref={wrapperRef} className="absolute inset-0 overflow-hidden">
      {/* MapLibre canvas — explicitly sized from wrapper; do NOT use absolute inset-0
          because MapLibre overrides position:absolute to position:relative on the container */}
      <div ref={containerRef} />

      {/* Loading overlay */}
      {isLoading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-white">
          <div className="flex flex-col items-center gap-3">
            <span className="h-8 w-8 animate-spin rounded-full border-4 border-neutral-200 border-t-orange-500" />
            <span className="text-sm text-neutral-500">Loading TP map…</span>
          </div>
        </div>
      )}

      {/* Error overlay */}
      {!isLoading && (isError || !mapData) && (
        <div className="absolute inset-0 z-20 flex items-center justify-center text-sm text-neutral-500">
          No TP geometry available for {tpScheme}
        </div>
      )}

      {/* Map controls — only when data is ready */}
      {!isLoading && mapData && (
        <>
          <div className="absolute top-4 right-14 z-10">
            <div className="rounded-xl border border-neutral-200 bg-white/90 px-3 py-2 shadow-sm backdrop-blur-sm">
              <div className="mb-1.5 text-[9px] font-bold uppercase tracking-wider text-neutral-500">Labels</div>
              <div className="flex items-center gap-3 text-[10px] text-neutral-700">
                {[
                  { key: "fp", label: "FP" },
                  { key: "road", label: "Road" },
                  { key: "block", label: "Block" },
                ].map((item) => (
                  <label key={item.key} className="flex items-center gap-1 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={labelVisibility[item.key as keyof LabelVisibility]}
                      onChange={(e) =>
                        setLabelVisibility((prev) => ({
                          ...prev,
                          [item.key]: e.target.checked,
                        }))
                      }
                      className="h-3 w-3 accent-orange-500"
                    />
                    <span>{item.label}</span>
                  </label>
                ))}
              </div>
              <div className="mt-1 text-[9px] text-neutral-500">Zoom: {mapZoom.toFixed(1)}</div>
            </div>
          </div>

          <div className="absolute bottom-4 left-4 z-10">
            <div className="rounded-xl border border-neutral-200 bg-white/90 px-3 py-2 shadow-sm backdrop-blur-sm">
              <div className="mb-1.5 text-[9px] font-bold uppercase tracking-wider text-neutral-500">Legend</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {[
                  { label: "Residential", color: "#f8d7da" },
                  { label: "Commercial", color: "#fff3b0" },
                  { label: "Public Purpose", color: "#fde68a" },
                  { label: "Open Space", color: "#bbf7d0" },
                  { label: "Unspecified", color: "#f5f5f4" },
                ].map((item) => (
                  <div key={item.label} className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-2.5 w-4 rounded-sm border border-neutral-300"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-[10px] text-neutral-600">{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="absolute bottom-4 right-4 z-10">
            <div className="rounded-lg border border-neutral-200 bg-white/90 px-3 py-1.5 shadow-sm backdrop-blur-sm">
              <div className="flex items-center gap-2 text-[10px] text-neutral-600">
                <span className="font-medium">
                  {bundle?.stats.fpCount ?? mapData.plots.features.length} Final Plots
                </span>
              </div>
            </div>
          </div>
        </>
      )}

      {hoveredPlot && <MapTooltip plot={hoveredPlot} x={tooltipPos.x} y={tooltipPos.y} />}
    </div>
  );
}
