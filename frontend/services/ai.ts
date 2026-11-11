import { z } from "zod";

import { apiRequest, apiStream } from "@/services/api-client";

/** Mirrors backend `app/schemas/ai.py`. */
export const actionStatusSchema = z.enum(["PENDING", "REJECTED", "EXECUTED", "FAILED", "EXPIRED"]);

export const aiStatusSchema = z.object({
  enabled: z.boolean(),
  provider: z.string().nullable(),
  model: z.string().nullable(),
  tools: z.array(
    z.object({ name: z.string(), label: z.string(), requires_confirmation: z.boolean() }),
  ),
  max_message_chars: z.number().int().positive(),
});

export const chatSessionSchema = z.object({
  id: z.string(),
  title: z.string(),
  created_at: z.string(),
  last_message_at: z.string(),
});

export const chatSessionPageSchema = z.object({
  items: z.array(chatSessionSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});

export const actionSchema = z.object({
  id: z.string(),
  tool_name: z.string(),
  summary: z.string(),
  status: actionStatusSchema,
  result: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
  expires_at: z.string(),
  decided_at: z.string().nullable(),
  created_at: z.string(),
});

export const chatMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant", "tool", "system"]),
  content: z.string(),
  tool_name: z.string().nullable().optional(),
  tool_label: z.string().nullable().optional(),
  tool_ok: z.boolean().nullable().optional(),
  action_id: z.string().nullable().optional(),
  created_at: z.string(),
});

export const chatSessionDetailSchema = chatSessionSchema.extend({
  messages: z.array(chatMessageSchema),
  actions: z.array(actionSchema),
});

export type AiStatus = z.infer<typeof aiStatusSchema>;
export type ChatSession = z.infer<typeof chatSessionSchema>;
export type ChatSessionDetail = z.infer<typeof chatSessionDetailSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type AiAction = z.infer<typeof actionSchema>;
export type ActionStatus = z.infer<typeof actionStatusSchema>;

/** Events of `POST /ai/sessions/{id}/messages` (server-sent events). */
export const streamEventSchema = z.discriminatedUnion("event", [
  z.object({
    event: z.literal("start"),
    data: z.object({ user_message_id: z.string(), title: z.string() }),
  }),
  z.object({ event: z.literal("delta"), data: z.object({ text: z.string() }) }),
  z.object({
    event: z.literal("tool"),
    data: z.object({
      message_id: z.string(),
      name: z.string(),
      label: z.string(),
      ok: z.boolean(),
      action_id: z.string().nullable(),
    }),
  }),
  z.object({ event: z.literal("action"), data: actionSchema }),
  z.object({
    event: z.literal("done"),
    data: z.object({ message_id: z.string(), truncated: z.boolean() }),
  }),
  z.object({
    event: z.literal("error"),
    data: z.object({ code: z.string(), message: z.string() }),
  }),
]);
export type StreamEvent = z.infer<typeof streamEventSchema>;

export const aiQueryKeys = {
  all: ["ai"] as const,
  status: ["ai", "status"] as const,
  sessions: ["ai", "sessions"] as const,
  session: (id: string) => ["ai", "session", id] as const,
};

const sessionPath = (id: string) => `/ai/sessions/${encodeURIComponent(id)}`;

export function getAiStatus(signal?: AbortSignal) {
  return apiRequest("/ai/status", { schema: aiStatusSchema, signal });
}

export function listChatSessions(signal?: AbortSignal) {
  return apiRequest("/ai/sessions", {
    schema: chatSessionPageSchema,
    signal,
    query: { page: 1, page_size: 50 },
  });
}

export function getChatSession(id: string, signal?: AbortSignal) {
  return apiRequest(sessionPath(id), { schema: chatSessionDetailSchema, signal });
}

export function createChatSession() {
  return apiRequest("/ai/sessions", { method: "POST", schema: chatSessionSchema, body: {} });
}

export function renameChatSession(id: string, title: string) {
  return apiRequest(sessionPath(id), {
    method: "PATCH",
    schema: chatSessionSchema,
    body: { title },
  });
}

export function deleteChatSession(id: string) {
  return apiRequest(sessionPath(id), { method: "DELETE", schema: z.null() });
}

export function confirmAction(id: string) {
  return apiRequest(`/ai/actions/${encodeURIComponent(id)}/confirm`, {
    method: "POST",
    schema: actionSchema,
  });
}

export function rejectAction(id: string) {
  return apiRequest(`/ai/actions/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    schema: actionSchema,
  });
}

/** Parse one SSE block (`event:` + `data:` lines). Unknown or malformed events are skipped. */
export function parseSseBlock(block: string): StreamEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  try {
    const parsed = streamEventSchema.safeParse({ event, data: JSON.parse(data.join("\n")) });
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** Send a message and call `onEvent` for every streamed event until the answer ends. */
export async function streamChatMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await apiStream(`${sessionPath(sessionId)}/messages`, { content }, signal);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const event = parseSseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  }
  const tail = parseSseBlock(buffer);
  if (tail) onEvent(tail);
}
