"use client";

import { useQuery } from "@tanstack/react-query";

import { dashboardQueryKeys, getDashboardSummary } from "@/services/dashboard";

export function useDashboardSummary() {
  return useQuery({
    queryKey: dashboardQueryKeys.summary,
    queryFn: ({ signal }) => getDashboardSummary(signal),
    staleTime: 30_000,
    refetchInterval: 120_000,
  });
}
