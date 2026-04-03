"use client";

import { useEffect, useMemo, useCallback, useRef } from "react";
import { Country, State, City } from "country-state-city";
import { usePlannerStore } from "@/state/plannerStore";
import { usePlotsQuery } from "@/modules/plots/hooks/usePlotsQuery";
import { TP_LIST } from "./tpData";

export type LocationLevel = "country" | "state" | "district" | "tp" | "fp";

export type BreadcrumbItem = {
  level: LocationLevel;
  id: string;
  label: string;
};

const LOCATION_PREFERENCE_KEY = "planner_location_preference";
const DEFAULT_TP_ID = "TP14";
const DEFAULT_DISTRICT = "Surat";

function normalizeTpId(value: unknown): string {
  if (typeof value !== "string") return DEFAULT_TP_ID;
  const cleaned = value.trim();
  if (!cleaned) return DEFAULT_TP_ID;
  return cleaned.toUpperCase();
}

function normalizeDistrictName(value: unknown): string {
  if (typeof value !== "string") return DEFAULT_DISTRICT;
  const cleaned = value.trim();
  return cleaned || DEFAULT_DISTRICT;
}

/** Only India → Gujarat → Surat has TP/FP data; hide TP/FP for other locations. */
function isSuratLocation(pref: {
  countryCode: string;
  stateCode: string;
  districtName: string;
}): boolean {
  return (
    pref.countryCode === "IN" &&
    pref.stateCode === "GJ" &&
    pref.districtName.toLowerCase() === "surat"
  );
}

function loadLocationPreference(): {
  countryCode: string;
  stateCode: string;
  districtName: string;
  tpId: string;
} {
  if (typeof window === "undefined") {
    return { countryCode: "IN", stateCode: "GJ", districtName: DEFAULT_DISTRICT, tpId: DEFAULT_TP_ID };
  }
  try {
    const raw = localStorage.getItem(LOCATION_PREFERENCE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        countryCode: parsed.countryCode ?? "IN",
        stateCode: parsed.stateCode ?? "GJ",
        districtName: normalizeDistrictName(parsed.districtName),
        tpId: normalizeTpId(parsed.tpId),
      };
    }
  } catch {
    // ignore
  }
  return { countryCode: "IN", stateCode: "GJ", districtName: DEFAULT_DISTRICT, tpId: DEFAULT_TP_ID };
}

export function useLocationHierarchy() {
  const locationPreference = usePlannerStore((s) => s.locationPreference);
  const setLocationPreference = usePlannerStore((s) => s.setLocationPreference);
  const selectedPlotId = usePlannerStore((s) => s.selectedPlotId);
  const setSelectedPlotId = usePlannerStore((s) => s.setSelectedPlotId);
  const setPlannerStage = usePlannerStore((s) => s.setPlannerStage);
  const showTpFp = useMemo(
    () => isSuratLocation(locationPreference),
    [locationPreference],
  );
  const { data: plots = [] } = usePlotsQuery(
    showTpFp
      ? {
          tpScheme: locationPreference.tpId,
          city: locationPreference.districtName,
        }
      : {},
  );
  const lastScopeRef = useRef<string>("");

  // Hydrate location from localStorage on mount (client-only)
  useEffect(() => {
    const loaded = loadLocationPreference();
    usePlannerStore.setState((s) => {
      const cur = s.locationPreference;
      if (
        cur.countryCode !== loaded.countryCode ||
        cur.stateCode !== loaded.stateCode ||
        cur.districtName !== loaded.districtName ||
        cur.tpId !== loaded.tpId
      ) {
        return { locationPreference: loaded };
      }
      return s;
    });
  }, []);

  // Clear stale FP selection when TP/city scope changes.
  useEffect(() => {
    if (!selectedPlotId) return;
    const stillVisible = plots.some((p) => p.id === selectedPlotId);
    if (!stillVisible) {
      setSelectedPlotId(null);
    }
  }, [plots, selectedPlotId, setSelectedPlotId]);

  // As soon as TP/city scope changes, force FP reset so the map is shown first.
  useEffect(() => {
    const scopeKey = `${locationPreference.districtName}|${locationPreference.tpId}`;
    if (lastScopeRef.current === "") {
      lastScopeRef.current = scopeKey;
      return;
    }
    if (lastScopeRef.current !== scopeKey) {
      setSelectedPlotId(null);
      lastScopeRef.current = scopeKey;
      return;
    }
    lastScopeRef.current = scopeKey;
  }, [locationPreference.districtName, locationPreference.tpId, setSelectedPlotId]);

  // Guard rail: if selected plot id does not belong to current TP, clear it.
  useEffect(() => {
    if (!selectedPlotId) return;
    const tpPrefix = `${locationPreference.tpId}-`;
    if (!selectedPlotId.startsWith(tpPrefix)) {
      setSelectedPlotId(null);
    }
  }, [selectedPlotId, locationPreference.tpId, setSelectedPlotId]);

  const countries = useMemo(() => Country.getAllCountries(), []);
  const states = useMemo(
    () => State.getStatesOfCountry(locationPreference.countryCode),
    [locationPreference.countryCode],
  );
  const districts = useMemo(
    () =>
      City.getCitiesOfState(
        locationPreference.countryCode,
        locationPreference.stateCode,
      ),
    [locationPreference.countryCode, locationPreference.stateCode],
  );

  const country = useMemo(
    () => countries.find((c) => c.isoCode === locationPreference.countryCode),
    [countries, locationPreference.countryCode],
  );
  const state = useMemo(
    () => states.find((s) => s.isoCode === locationPreference.stateCode),
    [states, locationPreference.stateCode],
  );
  const district = useMemo(
    () =>
      districts.find((d) => d.name === locationPreference.districtName),
    [districts, locationPreference.districtName],
  );

  const tpList = TP_LIST;

  function formatFpArea(p: { areaSqft?: number; areaSqm: number }): string {
    if (p.areaSqft != null && p.areaSqft > 0) {
      return `${Math.round(p.areaSqft).toLocaleString()} sq.ft`;
    }
    return `${Math.round(p.areaSqm)} m²`;
  }

  const fpList = useMemo(
    () =>
      plots.map((p) => ({
        id: p.id,
        name: p.name,
        areaSqm: p.areaSqm,
        areaSqft: p.areaSqft,
      })),
    [plots],
  );

  const selectedFp = useMemo(
    () => fpList.find((f) => f.id === selectedPlotId),
    [fpList, selectedPlotId],
  );

  const breadcrumbs: BreadcrumbItem[] = useMemo(() => {
    const items: BreadcrumbItem[] = [
      {
        level: "country",
        id: locationPreference.countryCode,
        label: country?.name ?? locationPreference.countryCode,
      },
      {
        level: "state",
        id: locationPreference.stateCode,
        label: state?.name ?? locationPreference.stateCode,
      },
      {
        level: "district",
        id: locationPreference.districtName,
        label: district?.name ?? locationPreference.districtName,
      },
    ];
    if (showTpFp) {
      items.push({
        level: "tp",
        id: locationPreference.tpId,
        label: locationPreference.tpId,
      });
      items.push({
        level: "fp",
        id: selectedFp?.id ?? "fp-select",
        label: selectedFp
          ? `${selectedFp.name} (${formatFpArea(selectedFp)})`
          : "Select FP",
      });
    }
    return items;
  }, [
    locationPreference,
    country,
    state,
    district,
    selectedFp,
    showTpFp,
  ]);

  const selectFp = useCallback(
    (fpId: string) => {
      setSelectedPlotId(fpId);
    },
    [setSelectedPlotId],
  );

  const selectLevel = useCallback(
    (level: LocationLevel, valueId: string) => {
      switch (level) {
        case "country": {
          const nextStates = State.getStatesOfCountry(valueId);
          const firstState = nextStates[0]?.isoCode ?? "";
          const nextDistricts = City.getCitiesOfState(valueId, firstState);
          const firstDistrict = nextDistricts[0]?.name ?? "";
          setSelectedPlotId(null);
          setPlannerStage("input");
          setLocationPreference({
            countryCode: valueId,
            stateCode: firstState,
            districtName: firstDistrict,
            tpId: "TP14",
          });
          break;
        }
        case "state": {
          const nextDistricts = City.getCitiesOfState(
            locationPreference.countryCode,
            valueId,
          );
          const firstDistrict = nextDistricts[0]?.name ?? "";
          setSelectedPlotId(null);
          setPlannerStage("input");
          setLocationPreference({
            stateCode: valueId,
            districtName: firstDistrict,
            tpId: "TP14",
          });
          break;
        }
        case "district":
          setSelectedPlotId(null);
          setPlannerStage("input");
          setLocationPreference({ districtName: valueId });
          break;
        case "tp":
          setSelectedPlotId(null);
          setPlannerStage("input");
          setLocationPreference({ tpId: valueId });
          break;
        default:
          break;
      }
    },
    [setLocationPreference, locationPreference.countryCode, setSelectedPlotId, setPlannerStage],
  );

  const getOptionsForLevel = useCallback(
    (level: LocationLevel) => {
      if ((level === "tp" || level === "fp") && !showTpFp) return [];
      switch (level) {
        case "country":
          return countries.map((c) => ({ id: c.isoCode, label: c.name }));
        case "state":
          return states.map((s) => ({ id: s.isoCode, label: s.name }));
        case "district":
          return districts.map((d) => ({ id: d.name, label: d.name }));
        case "tp":
          return tpList.map((t) => ({ id: t.id, label: t.name }));
        case "fp":
          return fpList.map((f) => ({
            id: f.id,
            label: `${f.name} (${formatFpArea(f)})`,
          }));
        default:
          return [];
      }
    },
    [countries, states, districts, tpList, fpList, showTpFp],
  );

  return {
    breadcrumbs,
    selectFp,
    selectLevel,
    getOptionsForLevel,
    selectedPlotId,
  };
}
