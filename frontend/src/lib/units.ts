/**
 * Area unit conversions used across the planner UI.
 *
 * VAR (વાર) is the local Surat unit — 1 VAR = 1 square yard = 9 sq.ft = 0.8361 sqm.
 */

export type AreaUnit = "sqm" | "sqft" | "var";

export const AREA_UNIT_LABELS: Record<AreaUnit, string> = {
  sqm: "sq.m",
  sqft: "sq.ft",
  var: "VAR (sq.yd)",
};

export const AREA_UNIT_SHORT: Record<AreaUnit, string> = {
  sqm: "m²",
  sqft: "ft²",
  var: "VAR",
};

const SQM_TO_SQFT = 10.7639;
const SQM_TO_SQYD = 1.19599; // 1 sqm = 1.19599 sq yard (VAR)

/** Convert area from sqm to the target unit. */
export function convertArea(sqm: number, to: AreaUnit): number {
  switch (to) {
    case "sqm":
      return sqm;
    case "sqft":
      return sqm * SQM_TO_SQFT;
    case "var":
      return sqm * SQM_TO_SQYD;
  }
}

/** Format area with unit suffix. */
export function formatArea(
  sqm: number,
  unit: AreaUnit,
  decimals = 0,
): string {
  const val = convertArea(sqm, unit);
  const formatted =
    decimals === 0
      ? Math.round(val).toLocaleString("en-IN")
      : val.toFixed(decimals);
  return `${formatted} ${AREA_UNIT_SHORT[unit]}`;
}

/** Convert length from metres to feet. */
export function metresToFeet(m: number): number {
  return m * 3.28084;
}
