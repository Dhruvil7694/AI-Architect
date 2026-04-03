/**
 * TP (Town Planning) data for the location hierarchy.
 * Currently we only support India / Gujarat / Surat / TP14 and FPs from the existing dataset (API).
 */

export type TpItem = {
  id: string;
  name: string;
};

/** Supported TP(s). FPs (plots) for each TP come from the API (usePlotsQuery). */
export const TP_LIST: TpItem[] = [
  { id: "TP14", name: "TP14" },
];

/** Default TP when only one is supported. */
export const DEFAULT_TP_ID = "TP14";
