"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

import { ApiError } from "@/services/api-client";
import { authQueryKeys, getMe, type Me } from "@/services/auth";

export interface Session {
  me: Me | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  /** True when the server said "not signed in" (as opposed to a network/server failure). */
  isUnauthenticated: boolean;
  error: unknown;
  has: (permission: string) => boolean;
  refetch: () => void;
}

export function useSession(): Session {
  const query = useQuery({
    queryKey: authQueryKeys.me,
    queryFn: ({ signal }) => getMe(signal),
    staleTime: 60_000,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
  });
  const permissions = useMemo(() => new Set(query.data?.permissions ?? []), [query.data]);
  const has = useCallback((permission: string) => permissions.has(permission), [permissions]);
  const isUnauthenticated = query.error instanceof ApiError && query.error.status === 401;

  return {
    me: query.data,
    isLoading: query.isPending,
    isAuthenticated: Boolean(query.data),
    isUnauthenticated,
    error: query.error,
    has,
    refetch: () => void query.refetch(),
  };
}

/** Store the session returned by login/change-password without another round trip. */
export function useSetSession(): (me: Me | null) => void {
  const client = useQueryClient();
  return useCallback(
    (me: Me | null) => {
      if (me) {
        client.setQueryData(authQueryKeys.me, me);
      } else {
        client.clear();
      }
    },
    [client],
  );
}
