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
  edited_at: z.string().nullable().default(null),
  /** Unsent by the sender: `body` is empty. */
  deleted_at: z.string().nullable().default(null),
});

export const conversationSchema = z.object({
  id: z.string(),
  other: chatPersonSchema,
  last_message: chatMessageSchema.nullable(),
  last_message_at: z.string().nullable(),
  unread_count: z.number().int().nonnegative(),
  /** My messages up to this time have been seen by the other person. */
  other_last_read_at: z.string().nullable(),
  other_typing: z.boolean(),
});

const conversationListSchema = z.object({
  items: z.array(conversationSchema),
  unread_total: z.number().int().nonnegative(),
});
const messagePageSchema = z.object({
  items: z.array(chatMessageSchema),
  has_more: z.boolean(),
  other_last_read_at: z.string().nullable().default(null),
  other_typing: z.boolean().default(false),
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

/** "I am typing" — the other person sees it for a few seconds; call again while typing. */
export function sendTyping(conversationId: string): Promise<null> {
  return apiRequest(`/chat/conversations/${encodeURIComponent(conversationId)}/typing`, {
    method: "POST",
    schema: z.null(),
  });
}

/** True when the other person has read up to (and including) a message sent at `sentAt`. */
export function isSeen(otherLastReadAt: string | null, sentAt: string): boolean {
  return otherLastReadAt !== null && new Date(otherLastReadAt) >= new Date(sentAt);
}

const chatEventsSchema = z.object({ version: z.number().int() });

/** Seconds the server holds `/chat/events` open when nothing changes. */
export const CHAT_EVENTS_WAIT_SECONDS = 25;

/**
 * Long poll: resolves as soon as anything changes in my conversations (a new message, a read
 * receipt, typing), or after ~25 s. Pass the returned `version` back as `since`.
 */
export function waitForChatEvents(since: number, signal?: AbortSignal) {
  return apiRequest(`/chat/events?since=${since}&wait=${CHAT_EVENTS_WAIT_SECONDS}`, {
    schema: chatEventsSchema,
    signal,
  });
}

/** I can edit or unsend my own messages (any time) unless already unsent. */
export function canChangeMessage(message: ChatMessage, myId: string | undefined): boolean {
  return message.sender_id === myId && message.deleted_at === null;
}

export function editMessage(
  conversationId: string,
  messageId: string,
  body: string,
): Promise<ChatMessage> {
  return apiRequest(
    `/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
    { method: "PATCH", schema: chatMessageSchema, body: { body } },
  );
}

/** Unsend for everyone; the server erases the text and returns the marker. */
export function unsendMessage(conversationId: string, messageId: string): Promise<ChatMessage> {
  return apiRequest(
    `/chat/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
    { method: "DELETE", schema: chatMessageSchema },
  );
}
