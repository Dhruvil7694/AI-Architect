import type { SiteMetrics } from "./plannerService";
import { httpRequest } from "./httpClient";

export async function getSiteMetricsOnly(
  plotId: string,
): Promise<SiteMetrics> {
  return httpRequest<SiteMetrics>(`/api/metrics/${plotId}/`, {
    method: "GET",
  });
}

