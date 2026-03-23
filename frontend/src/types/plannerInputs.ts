export interface PlannerInputs {
  // 1. Building Type
  buildingType: 1 | 2 | 3;

  // 2. Floors (null = auto/GDCR max)
  floors: number | null;

  // 3. Core (units per core)
  unitsPerCore: 2 | 4 | 6;

  // 4. Segment (drives RCA efficiency)
  segment: "budget" | "mid" | "premium" | "luxury";

  // 5. Number of buildings (null = auto)
  nBuildings: number | null;

  // Unit mix (optional)
  unitMix: string[];

  // Storey height (rarely changed)
  storeyHeightM: number;
}
