import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import { getPlots, type PlotSummary } from "@/services/plotsService";

export type UsePlotsQueryParams = {
  tpScheme?: string;
  city?: string;
};

export function usePlotsQuery(params: UsePlotsQueryParams = {}) {
  return useQuery<PlotSummary[]>({
    queryKey: queryKeys.plots.list(params),
    queryFn: () =>
      getPlots({
        tpScheme: params.tpScheme,
        city: params.city,
      }),
  });
}

