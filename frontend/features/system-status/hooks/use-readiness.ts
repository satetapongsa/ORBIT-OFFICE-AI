"use client";

import { useQuery } from "@tanstack/react-query";

import { getReadiness, healthQueryKeys } from "@/services/health";

const REFRESH_INTERVAL_MS = 30_000;

export function useReadiness() {
  return useQuery({
    queryKey: healthQueryKeys.readiness,
    queryFn: ({ signal }) => getReadiness(signal),
    refetchInterval: REFRESH_INTERVAL_MS,
    staleTime: 10_000,
  });
}
