export const queryKeys = {
  plots: {
    all: ["plots"] as const,
    list: (filters?: unknown) => ["plots", "list", filters] as const,
    detail: (id: string | number) => ["plots", "detail", id] as const,
  },
  planner: {
    root: ["planner"] as const,
    metrics: (plotId: string | number) =>
      ["planner", "metrics", { plotId }] as const,
    baseGeometry: (plotId: string | number) =>
      ["planner", "geometry", { plotId }] as const,
    plan: (plotId: string | number, scenarioId: string | number) =>
      ["planner", "plan", { plotId, scenarioId }] as const,
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
  | typeof queryKeys.planner.metrics
  | typeof queryKeys.planner.baseGeometry
  | typeof queryKeys.planner.plan
  | typeof queryKeys.admin.users.list
  | typeof queryKeys.admin.users.detail
>;

