"use client";

import { useQuery } from "@tanstack/react-query";

import { useSession } from "@/features/auth/hooks/use-session";
import { getReadiness, healthQueryKeys } from "@/services/health";

const REFRESH_INTERVAL_MS = 30_000;

/** Administrators get component details; everyone else the public summary. */
export function useReadiness() {
  const { has } = useSession();
  const details = has("system:configure");
  return useQuery({
    queryKey: healthQueryKeys.readiness(details),
    queryFn: ({ signal }) => getReadiness(signal, details),
    refetchInterval: REFRESH_INTERVAL_MS,
    staleTime: 10_000,
  });
}
