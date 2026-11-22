import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/messaging.py` (chat part). */
export const chatPersonSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  job_title: z.string().nullable(),
  department_name: z.string().nullable(),
  is_active: z.boolean(),
});

export const chatMessageSchema = z.object({
  id: z.string(),
  conversation_id: z.string(),
  sender_id: z.string(),
  body: z.string(),
  created_at: z.string(),
});

export const conversationSchema = z.object({
  id: z.string(),
  other: chatPersonSchema,
  last_message: chatMessageSchema.nullable(),
  last_message_at: z.string().nullable(),
  unread_count: z.number().int().nonnegative(),
});

const conversationListSchema = z.object({
  items: z.array(conversationSchema),
  unread_total: z.number().int().nonnegative(),
});
const messagePageSchema = z.object({
  items: z.array(chatMessageSchema),
  has_more: z.boolean(),
});
const unreadSchema = z.object({ unread_total: z.number().int().nonnegative() });

export type ChatPerson = z.infer<typeof chatPersonSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type Conversation = z.infer<typeof conversationSchema>;
export type MessagePage = z.infer<typeof messagePageSchema>;

export const chatQueryKeys = {
  all: ["chat"] as const,
  conversations: ["chat", "conversations"] as const,
  unread: ["chat", "unread"] as const,
  messages: (id: string) => ["chat", "messages", id] as const,
};

export const MESSAGE_MAX_CHARS = 4000;

export function listConversations(signal?: AbortSignal) {
  return apiRequest("/chat/conversations", { schema: conversationListSchema, signal });
}

export function getChatUnread(signal?: AbortSignal) {
  return apiRequest("/chat/unread-count", { schema: unreadSchema, signal });
}

export function startConversation(userId: string): Promise<Conversation> {
  return apiRequest("/chat/conversations", {
    method: "POST",
    schema: conversationSchema,
    body: { user_id: userId },
  });
}

export function listMessages(
  conversationId: string,
  params: { before?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<MessagePage> {
  const query = new URLSearchParams();
  if (params.before) query.set("before", params.before);
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.size ? `?${query}` : "";
  return apiRequest(`/chat/conversations/${encodeURIComponent(conversationId)}/messages${suffix}`, {
    schema: messagePageSchema,
    signal,
  });
}

export function sendMessage(conversationId: string, body: string): Promise<ChatMessage> {
  return apiRequest(`/chat/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    schema: chatMessageSchema,
    body: { body },
  });
}

export function markConversationRead(conversationId: string) {
  return apiRequest(`/chat/conversations/${encodeURIComponent(conversationId)}/read`, {
    method: "POST",
    schema: unreadSchema,
  });
}
