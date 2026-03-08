import { create } from "zustand";
import type { PlannerInputs } from "@/types/plannerInputs";

export type PlannerLayerKey =
  | "plotBoundary"
  | "envelope"
  | "cop"
  | "copMargin"
  | "internalRoads"
  | "roadCorridors"
  | "towerZones"
  | "towerFootprints"
  | "spacingLines"
  | "labels"
  | "buildableEnvelope"
  | "copCandidateZones"
  | "roadNetwork";

export type PlannerLayerVisibility = Record<PlannerLayerKey, boolean>;

export type PlannerSelection = {
  layer: PlannerLayerKey;
  featureId: string;
} | null;

export type PlanningStep = "site" | "floor" | "unit";

export type SelectedUnitInfo = {
  id: string;
  unitType?: string;
  carpetArea?: number;
  builtUpArea?: number;
  reraCarpet?: number;
  efficiency?: number;
  /** Clear internal width (along corridor, L-axis) from floor plan service */
  unitWidthM?: number;
  /** Clear internal depth (away from corridor, S-axis) from floor plan service */
  unitDepthM?: number;
};

export type PlannerScenario = {
  id: string;
  label?: string;
  plotId: string;
  inputs: PlannerInputs;
  planResultSummary?: unknown;
  createdAt: string;
};

type PlannerState = {
  selectedPlotId: string | null;
  activeScenarioId: string | null;
  inputs: PlannerInputs;
  layerVisibility: PlannerLayerVisibility;
  selection: PlannerSelection;
  isInputsPanelOpen: boolean;
  scenarios: PlannerScenario[];
  planningStep: PlanningStep;
  selectedTowerIndex: number | null;
  selectedUnit: SelectedUnitInfo | null;
  debugMode: boolean;
};

type PlannerActions = {
  setSelectedPlotId: (plotId: string | null) => void;
  setActiveScenarioId: (scenarioId: string | null) => void;
  setInputs: (inputs: Partial<PlannerInputs>) => void;
  setLayerVisibility: (visibility: Partial<PlannerLayerVisibility>) => void;
  setSelection: (selection: PlannerSelection) => void;
  toggleInputsPanel: () => void;
  setInputsPanelOpen: (open: boolean) => void;
  addScenario: (scenario: PlannerScenario) => void;
  updateScenario: (id: string, partial: Partial<PlannerScenario>) => void;
  removeScenario: (id: string) => void;
  resetForPlot: (plotId: string | null) => void;
  setPlanningStep: (step: PlanningStep) => void;
  setSelectedTowerIndex: (index: number | null) => void;
  setSelectedUnit: (unit: SelectedUnitInfo | null) => void;
  setDebugMode: (enabled: boolean) => void;
  toggleDebugMode: () => void;
};

export type PlannerStore = PlannerState & PlannerActions;

const defaultLayerVisibility: PlannerLayerVisibility = {
  plotBoundary: true,
  envelope: true,
  cop: true,
  copMargin: true,
  internalRoads: true,
  // Road corridors and spacing lines are visual noise at default zoom —
  // show them only when the user explicitly enables them.
  roadCorridors: false,
  towerZones: true,
  towerFootprints: true,
  spacingLines: false,
  labels: true,
  buildableEnvelope: false,
  copCandidateZones: false,
  roadNetwork: false,
};

const defaultInputs: PlannerInputs = {
  unitMix: ["2BHK", "3BHK"],
  segment: "mid",
  towerCount: "auto",
  preferredFloors: {},
  vastu: false,
};

export const usePlannerStore = create<PlannerStore>((set) => ({
  selectedPlotId: null,
  activeScenarioId: null,
  inputs: defaultInputs,
  layerVisibility: defaultLayerVisibility,
  selection: null,
  isInputsPanelOpen: false,
  scenarios: [],
  planningStep: "site",
  selectedTowerIndex: null,
  selectedUnit: null,
  debugMode: false,

  setSelectedPlotId: (plotId) =>
    set((state) => ({
      selectedPlotId: plotId,
      activeScenarioId: null,
      scenarios:
        plotId === state.selectedPlotId ? state.scenarios : [],
      inputs: defaultInputs,
      selection: null,
    })),

  setActiveScenarioId: (scenarioId) =>
    set({
      activeScenarioId: scenarioId,
    }),

  setInputs: (partial) =>
    set((state) => ({
      inputs: {
        ...state.inputs,
        ...partial,
        preferredFloors: {
          ...(state.inputs.preferredFloors ?? {}),
          ...(partial.preferredFloors ?? {}),
        },
      },
    })),

  setLayerVisibility: (visibility) =>
    set((state) => ({
      layerVisibility: {
        ...state.layerVisibility,
        ...visibility,
      },
    })),

  setSelection: (selection) => set({ selection }),

  toggleInputsPanel: () =>
    set((state) => ({ isInputsPanelOpen: !state.isInputsPanelOpen })),

  setInputsPanelOpen: (open) => set({ isInputsPanelOpen: open }),

  addScenario: (scenario) =>
    set((state) => ({
      scenarios: [...state.scenarios, scenario],
      activeScenarioId: scenario.id,
    })),

  updateScenario: (id, partial) =>
    set((state) => ({
      scenarios: state.scenarios.map((scenario) =>
        scenario.id === id ? { ...scenario, ...partial } : scenario,
      ),
    })),

  removeScenario: (id) =>
    set((state) => ({
      scenarios: state.scenarios.filter((scenario) => scenario.id !== id),
      activeScenarioId:
        state.activeScenarioId === id ? null : state.activeScenarioId,
    })),

  resetForPlot: (plotId) =>
    set(() => ({
      selectedPlotId: plotId,
      activeScenarioId: null,
      inputs: defaultInputs,
      layerVisibility: defaultLayerVisibility,
      selection: null,
      scenarios: [],
      isInputsPanelOpen: true,
      planningStep: "site",
      selectedTowerIndex: null,
      selectedUnit: null,
    })),

  setPlanningStep: (step) => set({ planningStep: step }),
  setSelectedTowerIndex: (index) => set({ selectedTowerIndex: index, selectedUnit: null }),
  setSelectedUnit: (unit) => set({ selectedUnit: unit }),
  setDebugMode: (enabled) => set({ debugMode: enabled }),
  toggleDebugMode: () => set((s) => ({ debugMode: !s.debugMode })),
}));

