import { useQuery } from "@tanstack/react-query";
import { getTpMapBundle, type TpMapBundle } from "@/services/tpMapService";
import { queryKeys } from "@/lib/queryKeys";

export function useTpMapBundle(tpScheme?: string, city?: string) {
  return useQuery<TpMapBundle>({
    queryKey: queryKeys.tpMap.bundle(tpScheme, city),
    queryFn: () =>
      getTpMapBundle({
        tpScheme: tpScheme ?? "",
        city,
      }),
    enabled: Boolean(tpScheme),
  });
}
