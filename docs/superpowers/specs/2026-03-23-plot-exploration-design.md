# Plot Exploration Step — Design Spec

## Goal

Add a foundational "Plot Exploration" step as the first step in the planner flow. When a user selects a plot, the system automatically analyzes it under GDCR rules and presents:
1. A **constraints dashboard** showing what's legally buildable (height, FSI, towers, setbacks, ground cover)
2. **3 AI-generated scenario cards** (High Density / Balanced / Premium) with sellable area estimates
3. The **plot on a TP map** with setback annotations and road edges

The user picks a scenario, optionally tweaks parameters, then proceeds to Site Plan generation with those parameters pre-filled.

## Flow

```
Step 1: Plot Exploration    →  Step 2: Site Plan    →  Step 3: AI Floor Plan
(auto on plot select)          (on scenario proceed)    (on tower select)
```

- **Step 1** triggers automatically when the user selects a plot.
- Single data fetch: `GET /api/development/explore/{plot_id}/` returns both constraints dashboard and AI scenario cards.
- Constraints section of the response is computed first (~2s) from existing feasibility service. AI scenarios take ~10-15s.
- Frontend renders constraints immediately; scenario cards show a loading skeleton until the full response arrives.
- If AI fails, the endpoint returns deterministic fallback scenarios computed from feasibility data alone.
- **Step 1 → Step 2:** User selects a scenario, optionally edits parameters, clicks "Proceed to Site Plan." Parameters pre-fill site plan inputs and generation starts automatically.

## State Machine

```
PlanningStep  |  PlannerStage      |  Meaning
------------- | ------------------ | -----------------------------------
"explore"     |  "input"           |  Analyzing plot, showing scenarios
"site"        |  "input"           |  User reviewing inputs before generation
"site"        |  "site-generating" |  Site plan computation in progress
"site"        |  "site-generated"  |  Site plan ready, user reviewing
"floor"       |  "floor-design"    |  AI floor plan for selected tower
```

```typescript
export type PlanningStep = "explore" | "site" | "floor";
```

Default step changes from `"site"` to `"explore"`.

---

## Backend

### New Endpoint: `GET /api/development/explore/{plot_id}/`

Read-only analysis endpoint. No request body. Uses `AllowAny` permission (same as existing feasibility endpoint).

**Internal pipeline:**
1. Fetch `Plot` from DB (geometry, road_width_m, designation, tp_scheme)
2. Check `plot.cached_feasibility_json` — if present, use cached feasibility; otherwise call `compute_feasibility_map(plot, storey_height_m=3.0)` and cache result
3. Call `resolve_fsi_policy(plot=plot, road_width_m=plot.road_width_m)` for FSI policy
4. Call `detect_road_edges_with_meta(plot.geometry, None)` for road edge geometry
5. Compute setback annotations per edge (using edge indices, not cardinal directions)
6. Build structured context from feasibility + FSI policy results
7. Call GPT-4o to generate 3 scenarios
8. Apply sellable area estimation using ratio logic
9. Validate AI scenarios against constraints (clamp towers/floors to feasibility limits)
10. Fall back to deterministic scenarios if AI fails
11. Return combined response

**Response shape:**
```json
{
  "plotSummary": {
    "plotId": "FP82",
    "areaSqm": 2500.0,
    "roadWidthM": 18.0,
    "zone": "R1",
    "authority": "SUDA",
    "designation": "DW3"
  },
  "constraints": {
    "maxHeightM": 30.0,
    "maxFloors": 10,
    "maxFSI": 4.0,
    "baseFSI": 1.8,
    "corridorEligible": false,
    "corridorReason": "Road width < 36m and no wide road within 200m",
    "maxGroundCoverPct": 40.0,
    "maxFeasibleTowers": 3,
    "setbacks": {
      "road": 4.5,
      "side": 3.0,
      "rear": 3.0
    },
    "premiumTiers": [
      {"fromFSI": 1.8, "toFSI": 2.5, "rate": 0.25},
      {"fromFSI": 2.5, "toFSI": 4.0, "rate": 0.40}
    ],
    "permissibleBuildingTypes": [
      {"id": 1, "label": "Low-Rise", "maxHeightM": 10.0},
      {"id": 2, "label": "Mid-Rise", "maxHeightM": 15.0},
      {"id": 3, "label": "High-Rise", "maxHeightM": 45.0}
    ]
  },
  "unitCompatibility": {
    "1BHK": true,
    "2BHK": true,
    "3BHK": true,
    "4BHK": false
  },
  "scenarios": [
    {
      "id": "high_density",
      "label": "High Density",
      "description": "Maximize sellable area with compact units",
      "towers": 3,
      "floors": 10,
      "buildingType": 2,
      "segment": "budget",
      "unitMix": ["1BHK", "2BHK"],
      "unitsPerCore": 6,
      "estimatedFSI": 3.6,
      "estimatedSellableAreaSqm": 9720,
      "sellablePerSqYd": 54,
      "estimatedTotalUnits": 180,
      "tradeoffNote": "Maximum unit count, smaller open spaces"
    },
    {
      "id": "balanced",
      "label": "Balanced",
      "description": "Good mix of density and livability",
      "towers": 2,
      "floors": 10,
      "buildingType": 2,
      "segment": "mid",
      "unitMix": ["2BHK", "3BHK"],
      "unitsPerCore": 4,
      "estimatedFSI": 2.7,
      "estimatedSellableAreaSqm": 7560,
      "sellablePerSqYd": 42,
      "estimatedTotalUnits": 80,
      "tradeoffNote": "Balanced density and open space"
    },
    {
      "id": "premium",
      "label": "Premium",
      "description": "Fewer towers, larger units, premium positioning",
      "towers": 1,
      "floors": 10,
      "buildingType": 3,
      "segment": "luxury",
      "unitMix": ["3BHK", "4BHK"],
      "unitsPerCore": 4,
      "estimatedFSI": 1.8,
      "estimatedSellableAreaSqm": 5400,
      "sellablePerSqYd": 30,
      "estimatedTotalUnits": 40,
      "tradeoffNote": "Maximum value per unit, large open spaces"
    }
  ],
  "plotAnnotations": {
    "roadEdges": [
      {"edgeIndex": 0, "roadWidthM": 18.0, "setbackM": 4.5}
    ],
    "setbackDistances": [
      {"edgeIndex": 0, "distanceM": 4.5, "type": "road"},
      {"edgeIndex": 1, "distanceM": 3.0, "type": "side"},
      {"edgeIndex": 2, "distanceM": 3.0, "type": "rear"},
      {"edgeIndex": 3, "distanceM": 3.0, "type": "side"}
    ],
    "envelopeCoords": [[...]]
  }
}
```

**Notes:**
- `unitCompatibility` is derived from the recommended tower option's `FloorPlanCompatibility` (feasibility.floor_plan_compat for the recommended tower count).
- `buildingType` in scenarios must be one of the `permissibleBuildingTypes` IDs. The AI prompt includes the list of permissible types.
- `setbackDistances` uses edge indices (matching plot geometry ring order), not cardinal directions. Frontend labels edges based on their orientation.
- `sellablePerSqYd` is the sellable area ratio: sellable sq.yd per sq.yd of plot area. This is the client's quick-estimation metric.

### New File: `backend/services/plot_exploration_service.py`

**Function:** `explore_plot(plot_id: str) -> dict`

Orchestrator that:
1. Loads `Plot` object
2. Checks `plot.cached_feasibility_json` — reuses if present, otherwise calls `compute_feasibility_map()` and caches
3. Calls `resolve_fsi_policy()` for FSI policy
4. Calls `detect_road_edges_with_meta()` for road edge geometry
5. Computes setback annotations per edge (edge index + distance + type)
6. Builds prompt context and calls GPT-4o for scenarios
7. Applies sellable area estimation using ratio logic (see Sellable Area section)
8. Validates AI scenarios against constraints (clamp towers/floors to feasibility limits, ensure buildingType is permissible)
9. Falls back to deterministic scenarios if AI fails

### New File: `backend/services/plot_exploration_prompt.py`

**Function:** `build_exploration_prompt(context: dict) -> tuple[str, str]`

Returns (system_prompt, user_prompt) for GPT-4o.

System prompt instructs the LLM to act as a development feasibility consultant, generate 3 scenarios (high_density, balanced, premium) as JSON, each respecting the GDCR constraints provided. The AI must select `buildingType` from the provided `permissibleBuildingTypes` list.

User prompt includes: plot area, road width, max height, max FSI, max towers, setbacks, corridor eligibility, unit compatibility, permissible building types, and the sellable ratio table.

**Config:** Uses existing `call_openai()` with model `gpt-4o`, temperature 0.3, max_tokens 2048.

### New File: `backend/api/views/plot_exploration.py`

Thin DRF APIView wrapping `explore_plot()`. Uses `permission_classes = [AllowAny]`.

### Modified: `backend/api/urls/development.py`

Add: `path("explore/<str:plot_id>/", PlotExplorationAPIView.as_view(), name="plot-exploration")`

---

## Frontend

### TypeScript Types

In `plannerService.ts`:

```typescript
export interface ExplorationScenario {
  id: string;
  label: string;
  description: string;
  towers: number;
  floors: number;
  buildingType: number;
  segment: string;
  unitMix: string[];
  unitsPerCore: number;
  estimatedFSI: number;
  estimatedSellableAreaSqm: number;
  sellablePerSqYd: number;
  estimatedTotalUnits: number;
  tradeoffNote: string;
}

export interface PremiumTier {
  fromFSI: number;
  toFSI: number;
  rate: number;
}

export interface BuildingTypeOption {
  id: number;
  label: string;
  maxHeightM: number;
}

export interface SetbackAnnotation {
  edgeIndex: number;
  distanceM: number;
  type: "road" | "side" | "rear";
}

export interface RoadEdgeAnnotation {
  edgeIndex: number;
  roadWidthM: number;
  setbackM: number;
}

export interface ExplorationConstraints {
  maxHeightM: number;
  maxFloors: number;
  maxFSI: number;
  baseFSI: number;
  corridorEligible: boolean;
  corridorReason: string;
  maxGroundCoverPct: number;
  maxFeasibleTowers: number;
  setbacks: { road: number; side: number; rear: number };
  premiumTiers: PremiumTier[];
  permissibleBuildingTypes: BuildingTypeOption[];
}

export interface PlotAnnotations {
  roadEdges: RoadEdgeAnnotation[];
  setbackDistances: SetbackAnnotation[];
  envelopeCoords: number[][];
}

export interface UnitCompatibility {
  "1BHK": boolean;
  "2BHK": boolean;
  "3BHK": boolean;
  "4BHK": boolean;
}

export interface ExplorationResponse {
  plotSummary: {
    plotId: string;
    areaSqm: number;
    roadWidthM: number;
    zone: string;
    authority: string;
    designation: string;
  };
  constraints: ExplorationConstraints;
  unitCompatibility: UnitCompatibility;
  scenarios: ExplorationScenario[];
  plotAnnotations: PlotAnnotations;
}
```

### New Component: `PlotExplorationView.tsx`

**Layout:** Split view in the main content area.

**Left panel (60%):** Plot on TP map
- Uses existing MapLibre-based component
- Plot boundary highlighted in orange
- Setback lines drawn as dashed lines with distance labels (per edge index)
- Road edges marked with road width labels
- Buildable envelope shown as semi-transparent shaded polygon

**Right panel (40%):** Stacked sections

**Section 1 — Constraints Dashboard (`ConstraintsDashboard.tsx`):**
- Plot: area, road width, zone, authority
- Height: max height, max floors
- FSI: base FSI, max FSI, corridor eligibility
- Coverage: max ground cover %
- Setbacks: road / side / rear margins
- Premium tiers table (from FSI → to FSI → rate)

Renders from the `constraints` field of `ExplorationResponse`. While the explore API is loading, a skeleton shimmer is shown.

**Section 2 — Scenario Cards (`ScenarioCards.tsx`):**
3 cards in a vertical stack, each showing:
- Label (bold) + description (one line)
- Grid of key numbers: towers, floors, est. FSI, sellable area, total units, sellable/sq.yd
- Trade-off note (italic, small)
- "Select" button

Loading state: 3 skeleton cards while AI generates.
Error state: 3 deterministic fallback cards (computed from feasibility data).

**Section 3 — Parameter Editor (appears when a scenario is selected):**
- Towers: number input (1 to maxFeasibleTowers)
- Floors: number input (1 to maxFloors)
- Segment: dropdown (budget / mid / premium / luxury)
- Unit mix: checkboxes (1BHK, 2BHK, 3BHK, 4BHK) — disabled if not compatible per `unitCompatibility`
- Units per core: radio (2 / 4 / 6)

**Bottom bar:**
- "Proceed to Site Plan →" button (disabled until a scenario is selected)
- On click: writes selected/edited parameters into `plannerStore.inputs`, sets `planningStep = "site"`, triggers site plan generation

### New Hook: `usePlotExploration(plotId)`

In `usePlannerData.ts`:
```typescript
export function usePlotExploration(plotId: string | null) {
  return useQuery<ExplorationResponse | null>({
    queryKey: plotId ? queryKeys.planner.exploration(plotId) : ["planner", "exploration", "none"],
    queryFn: () => plotId ? getPlotExploration(plotId) : Promise.resolve(null),
    enabled: Boolean(plotId),
    staleTime: 5 * 60 * 1000,
  });
}
```

### New Service Function: `getPlotExploration(plotId)`

In `plannerService.ts`:
```typescript
export async function getPlotExploration(plotId: string): Promise<ExplorationResponse> {
  return get(`/api/development/explore/${plotId}/`);
}
```

### Modified: `plannerStore.ts`

- `PlanningStep = "explore" | "site" | "floor"`
- Default `planningStep: "explore"` (was `"site"`)
- Add `selectedScenario: ExplorationScenario | null` state
- Add `setSelectedScenario` action
- `resetForPlot` resets to `planningStep: "explore"`, `selectedScenario: null`

### Modified: `StepNavigation.tsx`

Steps become:
```typescript
[
  { id: "explore", label: "Plot Exploration" },
  { id: "site",    label: "Site Plan" },
  { id: "floor",   label: "AI Floor Plan" },
]
```

"Site Plan" disabled until `selectedScenario` is not null. "AI Floor Plan" disabled until `selectedTowerIndex` is not null.

### Modified: `planner/page.tsx`

Add routing:
```typescript
planningStep === "explore" ? (
  <PlotExplorationView />
) : planningStep === "site" ? (
  <PlannerCanvas ... />
) : (
  <FloorPlanningView ... />
)
```

### Modified: `frontend/src/lib/queryKeys.ts`

Add exploration key factory:
```typescript
exploration: (plotId: string | number) => ["planner", "exploration", { plotId }] as const,
```

---

## Sellable Area Estimation Logic

Based on client's mental math ratios:

| Achieved FSI | Sellable per sq.yd of plot |
|-------------|---------------------------|
| 1.8         | 28 (interpolated)         |
| 2.7         | 42                        |
| 3.6         | 54                        |
| 4.0         | 60                        |

Linear interpolation between known points. `sellablePerSqYd` is the ratio of sellable sq.yd per sq.yd of plot area.

**Calculation:**
```
plot_area_sqyd = plot_area_sqm / 0.8361        # sqm to sqyd
sellable_sqyd = plot_area_sqyd * sellable_per_sqyd_ratio
sellable_sqm = sellable_sqyd * 0.8361           # sqyd back to sqm
```

**Unit carpet area estimation:**
```
avg_unit_area = segment_avg_carpet[segment]  # budget=45, mid=65, premium=85, luxury=110 sqm
carpet_area = avg_unit_area * 0.55           # RERA efficiency ratio
estimated_total_units = sellable_sqm / avg_unit_area
```

This is an estimate for comparison only — actual numbers come from the optimizer in Step 2.

---

## Fallback (No AI)

If GPT-4o fails or API key is not set, generate 3 deterministic scenarios:

1. **High Density:** max towers from feasibility, max floors, budget segment, smallest compatible units, 6 units/core
2. **Balanced:** recommended towers from feasibility, recommended floors, mid segment, 2BHK+3BHK mix, 4 units/core
3. **Premium:** 1 tower, recommended floors, luxury segment, largest compatible units, 4 units/core

FSI estimates come from feasibility `towerOptions[n].estimatedFsiAtMax`.

---

## Caching

The explore endpoint reuses `plot.cached_feasibility_json` for the feasibility portion (same cache as the existing feasibility endpoint). AI-generated scenarios are not cached — each plot selection triggers a fresh AI call (~10-15s). This is acceptable because:
- Users typically explore a plot once before proceeding
- AI scenarios may vary based on model updates
- The 5-minute `staleTime` on the frontend query prevents re-fetching during the same session

---

## Files Summary

### New Files (6)
| File | Purpose |
|------|---------|
| `backend/services/plot_exploration_service.py` | Orchestrator: feasibility + FSI policy + AI scenarios |
| `backend/services/plot_exploration_prompt.py` | GPT-4o prompt construction |
| `backend/api/views/plot_exploration.py` | DRF API endpoint |
| `frontend/src/modules/planner/components/PlotExplorationView.tsx` | Main exploration view |
| `frontend/src/modules/planner/components/ScenarioCards.tsx` | 3 scenario cards with select/edit |
| `frontend/src/modules/planner/components/ConstraintsDashboard.tsx` | GDCR constraints display |

### Modified Files (7)
| File | Change |
|------|--------|
| `backend/api/urls/development.py` | Add `explore/<plot_id>/` route |
| `frontend/src/state/plannerStore.ts` | PlanningStep type, selectedScenario state, default step |
| `frontend/src/modules/planner/components/StepNavigation.tsx` | 3 steps with proper disable logic |
| `frontend/src/app/(protected)/planner/page.tsx` | Route "explore" to PlotExplorationView |
| `frontend/src/services/plannerService.ts` | ExplorationResponse types + getPlotExploration() |
| `frontend/src/modules/planner/hooks/usePlannerData.ts` | usePlotExploration() hook |
| `frontend/src/lib/queryKeys.ts` | Add exploration query key factory |

### Reused (no changes)
- `architecture/services/feasibility_advisor.py`
- `architecture/regulatory/fsi_policy.py`
- `architecture/spatial/road_edge_detector.py`
- `ai_layer/client.py`
- `GDCR.yaml`
