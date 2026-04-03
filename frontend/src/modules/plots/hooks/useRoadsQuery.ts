import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import { getRoads, type RoadSummary } from "@/services/roadsService";

export function useRoadsQuery(tpScheme?: string) {
  return useQuery<RoadSummary[]>({
    queryKey: queryKeys.roads.list(tpScheme),
    queryFn: () => getRoads({ tp_scheme: tpScheme ?? "" }),
    enabled: Boolean(tpScheme),
  });
}

