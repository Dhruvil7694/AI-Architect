export const queryKeys = {
  plots: {
    all: ["plots"] as const,
    list: (filters?: unknown) => ["plots", "list", filters] as const,
    detail: (id: string | number) => ["plots", "detail", id] as const,
  },
  roads: {
    all: ["roads"] as const,
    list: (tpScheme?: string) => ["roads", "list", tpScheme] as const,
  },
  blockLabels: {
    all: ["block-labels"] as const,
    list: (tpScheme?: string) => ["block-labels", "list", tpScheme] as const,
  },
  tpMap: {
    bundle: (tpScheme?: string, city?: string) =>
      ["tp-map", "bundle", { tpScheme, city }] as const,
  },
  planner: {
    root: ["planner"] as const,
    metrics: (plotId: string | number) =>
      ["planner", "metrics", { plotId }] as const,
    baseGeometry: (plotId: string | number) =>
      ["planner", "geometry", { plotId }] as const,
    plan: (plotId: string | number, scenarioId: string | number) =>
      ["planner", "plan", { plotId, scenarioId }] as const,
    aiScenarios: (plotId: string | number) =>
      ["planner", "ai-scenarios", { plotId }] as const,
    feasibility: (plotId: string | number) =>
      ["planner", "feasibility", { plotId }] as const,
    exploration: (plotId: string | number) =>
      ["planner", "exploration", { plotId }] as const,
  },
  admin: {
    users: {
      list: (filters?: unknown) => ["admin", "users", "list", filters] as const,
      detail: (id: string | number) =>
        ["admin", "users", "detail", id] as const,
    },
  },
};

export type QueryKey = ReturnType<
  | typeof queryKeys.plots.list
  | typeof queryKeys.plots.detail
  | typeof queryKeys.roads.list
  | typeof queryKeys.blockLabels.list
  | typeof queryKeys.tpMap.bundle
  | typeof queryKeys.planner.metrics
  | typeof queryKeys.planner.baseGeometry
  | typeof queryKeys.planner.plan
  | typeof queryKeys.planner.exploration
  | typeof queryKeys.admin.users.list
  | typeof queryKeys.admin.users.detail
>;
