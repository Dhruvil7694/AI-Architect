import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queryKeys";
import { getBlockLabels, type BlockLabelSummary } from "@/services/blockLabelsService";

export function useBlockLabelsQuery(tpScheme?: string) {
  return useQuery<BlockLabelSummary[]>({
    queryKey: queryKeys.blockLabels.list(tpScheme),
    queryFn: () => getBlockLabels({ tp_scheme: tpScheme }),
    enabled: Boolean(tpScheme),
  });
}

