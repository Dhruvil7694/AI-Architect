export interface PlannerInputs {
  unitMix: string[];
  segment: "budget" | "mid" | "premium" | "luxury";
  towerCount: "auto" | number;
  preferredFloors?: {
    min?: number;
    max?: number;
  };
  vastu?: boolean;
}

