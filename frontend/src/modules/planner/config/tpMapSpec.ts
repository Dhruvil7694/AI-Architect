export const TP_MAP_COORD_SPACE = "LOCAL_DXF" as const;

export const TP_MAP_ANCHOR = {
  lng: 72.5,
  lat: 21.0,
  spanLng: 0.18,
} as const;

export const TP_MAP_LAYER_IDS = {
  roadFill: "road-fill",
  roadOutline: "road-outline",
  plotFill: "plot-fill",
  plotOutline: "plot-outline",
  plotOutlineSelected: "plot-outline-selected",
  fpLabelMajor: "fp-label-major",
  fpLabelAll: "fp-label-all",
  roadLabel: "road-label",
  blockLabel: "block-label",
} as const;

export const TP_MAP_SOURCE_IDS = {
  plots: "tp-plots",
  fpLabels: "tp-fp-labels",
  roadPolygons: "tp-road-polygons",
  roadCenterlines: "tp-road-lines",
  roadLabelPoints: "tp-road-label-pts",
  blockLabels: "tp-block-labels",
} as const;

export const TP_MAP_ZOOM_MATRIX = {
  fpMajorMin: 11,
  fpAllMin: 12,
  roadLabelsMin: 11,
  blockLabelsMin: 16,
} as const;

export const TP_LABEL_DEFAULT_VISIBILITY = {
  fp: true,
  road: true,
  block: false,
} as const;

export const TP_FP_MAJOR_AREA_SQM_MIN = 2400;
