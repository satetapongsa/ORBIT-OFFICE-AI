import { z } from "zod";

import { ApiError, apiDownload, apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/messaging.py` (chat part). */
export const chatPersonSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  job_title: z.string().nullable(),
  department_name: z.string().nullable(),
  is_active: z.boolean(),
});

/** A file or image in a chat (ADR-072). */
export const chatAttachmentSchema = z.object({
  id: z.string(),
  original_filename: z.string(),
  file_type: z.string(),
  mime_type: z.string(),
  size_bytes: z.number().int(),
  is_image: z.boolean(),
});
export type ChatAttachment = z.infer<typeof chatAttachmentSchema>;

export const chatMessageSchema = z.object({
  id: z.string(),
  conversation_id: z.string(),
  sender_id: z.string(),
  body: z.string(),
  created_at: z.string(),
  edited_at: z.string().nullable().default(null),
  attachment: chatAttachmentSchema.nullable().default(null),
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

/** I can edit my own messages, at any time. */
export function canEditMessage(message: ChatMessage, myId: string | undefined): boolean {
  return message.sender_id === myId;
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

// --- Group chats (ADR-071) --------------------------------------------------------------

export const groupMemberSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  department_name: z.string().nullable(),
  role: z.enum(["ADMIN", "MEMBER"]),
  last_read_at: z.string().nullable(),
});

export const groupMessageSchema = z.object({
  id: z.string(),
  group_id: z.string(),
  sender_id: z.string().nullable(),
  sender_name: z.string().nullable(),
  kind: z.enum(["TEXT", "SYSTEM"]),
  body: z.string(),
  created_at: z.string(),
  edited_at: z.string().nullable().default(null),
  attachment: chatAttachmentSchema.nullable().default(null),
});

export const groupSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  member_count: z.number().int(),
  my_role: z.enum(["ADMIN", "MEMBER"]),
  last_message: groupMessageSchema.nullable(),
  last_message_at: z.string().nullable(),
  unread_count: z.number().int().nonnegative(),
  typing_names: z.array(z.string()).default([]),
});

export const groupDetailSchema = groupSummarySchema.extend({ members: z.array(groupMemberSchema) });

const groupMessagePageSchema = z.object({
  items: z.array(groupMessageSchema),
  has_more: z.boolean(),
  reads: z.array(groupMemberSchema).default([]),
  typing_names: z.array(z.string()).default([]),
});

export type GroupMember = z.infer<typeof groupMemberSchema>;
export type GroupMessage = z.infer<typeof groupMessageSchema>;
export type GroupSummary = z.infer<typeof groupSummarySchema>;
export type GroupDetail = z.infer<typeof groupDetailSchema>;
export type GroupMessagePage = z.infer<typeof groupMessagePageSchema>;

export const groupQueryKeys = {
  list: ["chat", "groups"] as const,
  detail: (id: string) => ["chat", "groups", id] as const,
  messages: (id: string) => ["chat", "group-messages", id] as const,
};

const groupPath = (id: string) => `/chat/groups/${encodeURIComponent(id)}`;

export function listGroups(signal?: AbortSignal) {
  return apiRequest("/chat/groups", { schema: z.array(groupSummarySchema), signal });
}

export function getGroup(id: string, signal?: AbortSignal) {
  return apiRequest(groupPath(id), { schema: groupDetailSchema, signal });
}

export function createGroup(input: {
  name: string;
  member_ids: string[];
  include_department_id?: string | null;
}): Promise<GroupDetail> {
  return apiRequest("/chat/groups", { method: "POST", schema: groupDetailSchema, body: input });
}

export function renameGroup(id: string, name: string): Promise<GroupDetail> {
  return apiRequest(groupPath(id), { method: "PATCH", schema: groupDetailSchema, body: { name } });
}

export function addGroupMembers(id: string, userIds: string[]): Promise<GroupDetail> {
  return apiRequest(`${groupPath(id)}/members`, {
    method: "POST",
    schema: groupDetailSchema,
    body: { user_ids: userIds },
  });
}

/** Remove someone (admin), or leave when `userId` is me. */
export function removeGroupMember(id: string, userId: string): Promise<null> {
  return apiRequest(`${groupPath(id)}/members/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    schema: z.null(),
  });
}

export function listGroupMessages(
  id: string,
  params: { before?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<GroupMessagePage> {
  const query = new URLSearchParams();
  if (params.before) query.set("before", params.before);
  if (params.limit) query.set("limit", String(params.limit));
  const suffix = query.size ? `?${query}` : "";
  return apiRequest(`${groupPath(id)}/messages${suffix}`, {
    schema: groupMessagePageSchema,
    signal,
  });
}

export function sendGroupMessage(id: string, body: string): Promise<GroupMessage> {
  return apiRequest(`${groupPath(id)}/messages`, {
    method: "POST",
    schema: groupMessageSchema,
    body: { body },
  });
}

export function editGroupMessage(id: string, messageId: string, body: string) {
  return apiRequest(`${groupPath(id)}/messages/${encodeURIComponent(messageId)}`, {
    method: "PATCH",
    schema: groupMessageSchema,
    body: { body },
  });
}

export function markGroupRead(id: string) {
  return apiRequest(`${groupPath(id)}/read`, { method: "POST", schema: unreadSchema });
}

export function sendGroupTyping(id: string): Promise<null> {
  return apiRequest(`${groupPath(id)}/typing`, { method: "POST", schema: z.null() });
}

// --- Files and images (ADR-072) ---------------------------------------------------------

export const CHAT_ACCEPTED_FILES = ".pdf,.docx,.xlsx,.txt,.png,.jpg,.jpeg";
const CHAT_EXTENSIONS = ["pdf", "docx", "xlsx", "txt", "png", "jpg", "jpeg"];
export const CHAT_MAX_FILE_BYTES = 25 * 1024 * 1024;

/** Quick check before uploading (the server checks the real content again). */
export function checkChatFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!CHAT_EXTENSIONS.includes(ext)) return "ส่งได้เฉพาะรูป PNG/JPG และไฟล์ PDF, DOCX, XLSX, TXT";
  if (file.size === 0) return "ไฟล์ว่างเปล่า";
  if (file.size > CHAT_MAX_FILE_BYTES) return "ไฟล์มีขนาดใหญ่เกิน 25 MB";
  return null;
}

function fileForm(file: File, caption: string): FormData {
  const form = new FormData();
  form.set("file", file);
  if (caption) form.set("body", caption);
  return form;
}

export function sendFile(conversationId: string, file: File, caption = ""): Promise<ChatMessage> {
  return apiRequest(`/chat/conversations/${encodeURIComponent(conversationId)}/files`, {
    method: "POST",
    schema: chatMessageSchema,
    body: fileForm(file, caption),
  });
}

export function sendGroupFile(groupId: string, file: File, caption = ""): Promise<GroupMessage> {
  return apiRequest(`${groupPath(groupId)}/files`, {
    method: "POST",
    schema: groupMessageSchema,
    body: fileForm(file, caption),
  });
}

const attachmentPath = (id: string) => `/chat/attachments/${encodeURIComponent(id)}`;

export function downloadChatFile(attachment: ChatAttachment) {
  return apiDownload(attachmentPath(attachment.id), {
    fallbackName: attachment.original_filename,
  });
}

/** Image bytes for an in-chat preview (shown only through a blob: URL in an <img>). */
export async function fetchChatImage(id: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`/api/v1${attachmentPath(id)}`, {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: "preview_failed",
      message: "แสดงรูปไม่สำเร็จ",
    });
  }
  return response.blob();
}

/** One line for chat lists: the caption, or what was sent. */
export function messagePreview(m: { body: string; attachment: ChatAttachment | null }): string {
  if (m.body) return m.body;
  if (m.attachment)
    return m.attachment.is_image ? "📷 ส่งรูปภาพ" : `📎 ${m.attachment.original_filename}`;
  return "";
}
