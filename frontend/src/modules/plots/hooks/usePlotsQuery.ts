import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import { getPlots, type PlotSummary } from "@/services/plotsService";

export function usePlotsQuery() {
  return useQuery<PlotSummary[]>({
    queryKey: queryKeys.plots.list(undefined),
    queryFn: () => getPlots(),
  });
}

