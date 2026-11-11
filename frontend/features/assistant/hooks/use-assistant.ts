"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import {
  aiQueryKeys,
  confirmAction,
  createChatSession,
  deleteChatSession,
  getAiStatus,
  getChatSession,
  listChatSessions,
  rejectAction,
  renameChatSession,
  streamChatMessage,
  type AiAction,
} from "@/services/ai";
import { ApiError } from "@/services/api-client";
import { dashboardQueryKeys } from "@/services/dashboard";
import { notificationQueryKeys } from "@/services/notifications";
import { taskQueryKeys } from "@/services/tasks";

export function useAiStatus() {
  return useQuery({ queryKey: aiQueryKeys.status, queryFn: ({ signal }) => getAiStatus(signal) });
}

export function useChatSessions() {
  return useQuery({
    queryKey: aiQueryKeys.sessions,
    queryFn: ({ signal }) => listChatSessions(signal),
  });
}

export function useChatSession(id: string | null) {
  return useQuery({
    queryKey: aiQueryKeys.session(id ?? "none"),
    queryFn: ({ signal }) => getChatSession(id!, signal),
    enabled: id !== null,
  });
}

export function useRenameSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => renameChatSession(id, title),
    onSuccess: () => client.invalidateQueries({ queryKey: aiQueryKeys.all }),
  });
}

export function useDeleteSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteChatSession(id),
    onSuccess: () => client.invalidateQueries({ queryKey: aiQueryKeys.sessions }),
  });
}

/** Confirm or reject a proposed action; refreshes what it may have changed. */
export function useDecideAction(sessionId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, confirm }: { id: string; confirm: boolean }) =>
      confirm ? confirmAction(id) : rejectAction(id),
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: aiQueryKeys.session(sessionId ?? "none") }),
        client.invalidateQueries({ queryKey: taskQueryKeys.all }),
        client.invalidateQueries({ queryKey: dashboardQueryKeys.summary }),
        client.invalidateQueries({ queryKey: notificationQueryKeys.all }),
      ]),
  });
}

export interface PendingTool {
  id: string;
  label: string;
  ok: boolean;
  actionId: string | null;
}

/** The answer being streamed right now (shown until the stored history catches up). */
export interface PendingTurn {
  question: string;
  answer: string;
  tools: PendingTool[];
  actions: AiAction[];
  error: string | null;
  streaming: boolean;
}

/** Send messages, creating a conversation on first use, and follow the streamed answer. */
export function useChatStream(sessionId: string | null, onSessionCreated: (id: string) => void) {
  const client = useQueryClient();
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const abort = useRef<AbortController | null>(null);

  const send = useCallback(
    async (question: string) => {
      const controller = new AbortController();
      abort.current = controller;
      setPending({ question, answer: "", tools: [], actions: [], error: null, streaming: true });
      const update = (change: (turn: PendingTurn) => PendingTurn) =>
        setPending((turn) => (turn ? change(turn) : turn));
      let id = sessionId;
      try {
        if (id === null) {
          id = (await createChatSession()).id;
          onSessionCreated(id);
        }
        await streamChatMessage(
          id,
          question,
          (event) => {
            switch (event.event) {
              case "delta":
                update((t) => ({ ...t, answer: t.answer + event.data.text }));
                break;
              case "tool":
                update((t) => ({
                  ...t,
                  // Text before a tool call is a progress note; the final answer follows.
                  answer: t.answer ? `${t.answer}\n\n` : t.answer,
                  tools: [
                    ...t.tools,
                    {
                      id: event.data.message_id,
                      label: event.data.label,
                      ok: event.data.ok,
                      actionId: event.data.action_id,
                    },
                  ],
                }));
                break;
              case "action":
                update((t) => ({ ...t, actions: [...t.actions, event.data] }));
                break;
              case "error":
                update((t) => ({ ...t, error: event.data.message }));
                break;
              default:
                break;
            }
          },
          controller.signal,
        );
        update((t) => ({ ...t, streaming: false }));
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          update((t) => ({ ...t, streaming: false, error: t.error ?? "หยุดการตอบแล้ว" }));
        } else {
          update((t) => ({
            ...t,
            streaming: false,
            error: error instanceof ApiError ? error.message : "ส่งข้อความไม่สำเร็จ",
          }));
        }
      } finally {
        abort.current = null;
        if (id !== null) {
          await Promise.all([
            client.invalidateQueries({ queryKey: aiQueryKeys.session(id) }),
            client.invalidateQueries({ queryKey: aiQueryKeys.sessions }),
          ]);
        }
        // Keep an error visible; otherwise the stored history now shows the turn.
        setPending((turn) => (turn && turn.error ? turn : null));
      }
    },
    [client, onSessionCreated, sessionId],
  );

  return {
    pending,
    send,
    stop: () => abort.current?.abort(),
    clear: () => setPending(null),
  };
}
