"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { useSession } from "@/features/auth/hooks/use-session";
import { ApiError } from "@/services/api-client";
import { chatQueryKeys, waitForChatEvents } from "@/services/chat";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Keeps one long-poll request open for the whole app (ADR-062). When the server reports a
 * change, every chat query on screen (open thread, list, menu badge) refetches at once, so
 * new messages, "อ่านแล้ว" and "กำลังพิมพ์…" appear within a fraction of a second.
 */
export function useChatRealtime() {
  const client = useQueryClient();
  const { has, isAuthenticated } = useSession();
  const enabled = isAuthenticated && has("chat:use");

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let since = -1;
    let backoff = 0;

    void (async () => {
      while (!controller.signal.aborted) {
        try {
          const { version } = await waitForChatEvents(since, controller.signal);
          if (since !== -1 && version !== since) {
            await client.invalidateQueries({ queryKey: chatQueryKeys.all });
          }
          since = version;
          backoff = 0;
        } catch (error) {
          if (controller.signal.aborted) return;
          // Signed out or no permission: stop. Network/server trouble: retry with backoff.
          if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return;
          backoff = Math.min(backoff ? backoff * 2 : 1_000, 15_000);
          await sleep(backoff);
        }
      }
    })();

    return () => controller.abort();
  }, [enabled, client]);
}
