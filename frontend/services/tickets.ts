import { z } from "zod";

import { apiDownload, apiRequest, ApiError } from "@/services/api-client";
import { assignableUserSchema, taskPrioritySchema, type TaskPriority } from "@/services/tasks";

/** Mirrors backend `app/schemas/tickets.py`. */
export const ticketStatusSchema = z.enum([
  "OPEN",
  "IN_PROGRESS",
  "WAITING_FOR_USER",
  "RESOLVED",
  "CLOSED",
  "CANCELLED",
]);
export const ticketCategorySchema = z.enum([
  "COMPUTER",
  "NETWORK",
  "PRINTER",
  "SOFTWARE",
  "ACCOUNT_ACCESS",
  "OTHER",
]);
export const ticketEventTypeSchema = z.enum([
  "CREATED",
  "STATUS_CHANGED",
  "ASSIGNED",
  "UNASSIGNED",
  "PRIORITY_CHANGED",
  "CATEGORY_CHANGED",
  "COMMENTED",
  "ATTACHMENT_ADDED",
  "ATTACHMENT_REMOVED",
]);
export const ticketAttachmentTypeSchema = z.enum(["PDF", "DOCX", "XLSX", "TXT", "PNG", "JPEG"]);

const userRefSchema = z.object({ id: z.string(), display_name: z.string() });

export const ticketListItemSchema = z.object({
  id: z.string(),
  ticket_number: z.string(),
  title: z.string(),
  category: ticketCategorySchema,
  priority: taskPrioritySchema,
  status: ticketStatusSchema,
  requester: userRefSchema,
  assignee: userRefSchema.nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  resolved_at: z.string().nullable(),
  closed_at: z.string().nullable(),
});

export const ticketCapabilitiesSchema = z.object({
  can_manage: z.boolean(),
  can_assign: z.boolean(),
  can_comment: z.boolean(),
  can_comment_internal: z.boolean(),
  can_attach: z.boolean(),
  can_attach_internal: z.boolean(),
  allowed_statuses: z.array(ticketStatusSchema),
});

export const ticketDetailSchema = ticketListItemSchema.extend({
  description: z.string(),
  capabilities: ticketCapabilitiesSchema,
});

export const ticketPageSchema = z.object({
  items: z.array(ticketListItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});

export const ticketCommentSchema = z.object({
  id: z.string(),
  author: userRefSchema.nullable(),
  body: z.string(),
  is_internal: z.boolean(),
  created_at: z.string(),
});

export const ticketAttachmentSchema = z.object({
  id: z.string(),
  original_filename: z.string(),
  file_type: ticketAttachmentTypeSchema,
  size_bytes: z.number().int().nonnegative(),
  is_internal: z.boolean(),
  uploaded_by: userRefSchema.nullable(),
  created_at: z.string(),
  can_delete: z.boolean(),
});

export const ticketEventSchema = z.object({
  id: z.string(),
  event_type: ticketEventTypeSchema,
  actor: userRefSchema.nullable(),
  from_value: z.string().nullable(),
  to_value: z.string().nullable(),
  is_internal: z.boolean(),
  created_at: z.string(),
});

export type TicketStatus = z.infer<typeof ticketStatusSchema>;
export type TicketCategory = z.infer<typeof ticketCategorySchema>;
export type TicketEventType = z.infer<typeof ticketEventTypeSchema>;
export type TicketListItem = z.infer<typeof ticketListItemSchema>;
export type TicketDetail = z.infer<typeof ticketDetailSchema>;
export type TicketPage = z.infer<typeof ticketPageSchema>;
export type TicketComment = z.infer<typeof ticketCommentSchema>;
export type TicketEvent = z.infer<typeof ticketEventSchema>;
export type TicketAttachment = z.infer<typeof ticketAttachmentSchema>;
export type TicketAttachmentType = z.infer<typeof ticketAttachmentTypeSchema>;
export type TicketScope = "mine" | "assigned" | "unassigned" | "all";
export type TicketSort = "updated" | "created" | "priority";

export interface TicketListParams {
  scope?: TicketScope;
  q?: string;
  status?: TicketStatus;
  openOnly?: boolean;
  category?: TicketCategory;
  priority?: TaskPriority;
  sort?: TicketSort;
  page?: number;
  pageSize?: number;
}

export interface TicketInput {
  title: string;
  description: string;
  category: TicketCategory;
  priority: TaskPriority;
}

export const ticketQueryKeys = {
  all: ["tickets"] as const,
  list: (params: TicketListParams) => ["tickets", "list", params] as const,
  detail: (id: string) => ["tickets", "detail", id] as const,
  comments: (id: string) => ["tickets", "comments", id] as const,
  history: (id: string) => ["tickets", "history", id] as const,
  attachments: (id: string) => ["tickets", "attachments", id] as const,
  assignees: ["tickets", "assignees"] as const,
};

const path = (id: string) => `/tickets/${encodeURIComponent(id)}`;

export function listTickets(params: TicketListParams, signal?: AbortSignal) {
  return apiRequest("/tickets", {
    schema: ticketPageSchema,
    signal,
    query: {
      scope: params.scope ?? "mine",
      q: params.q || undefined,
      status: params.status,
      open_only: params.openOnly || undefined,
      category: params.category,
      priority: params.priority,
      sort: params.sort ?? "updated",
      page: params.page ?? 1,
      page_size: params.pageSize ?? 20,
    },
  });
}

export function getTicket(id: string, signal?: AbortSignal) {
  return apiRequest(path(id), { schema: ticketDetailSchema, signal });
}

export function createTicket(input: TicketInput) {
  return apiRequest("/tickets", { method: "POST", schema: ticketDetailSchema, body: input });
}

export function updateTicket(
  id: string,
  input: { category?: TicketCategory; priority?: TaskPriority },
) {
  return apiRequest(path(id), { method: "PATCH", schema: ticketDetailSchema, body: input });
}

export function changeTicketStatus(id: string, status: TicketStatus) {
  return apiRequest(`${path(id)}/status`, {
    method: "POST",
    schema: ticketDetailSchema,
    body: { status },
  });
}

export function assignTicket(id: string, assigneeId: string | null) {
  return apiRequest(`${path(id)}/assignee`, {
    method: "PUT",
    schema: ticketDetailSchema,
    body: { assignee_id: assigneeId },
  });
}

export function listTicketComments(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/comments`, { schema: z.array(ticketCommentSchema), signal });
}

export function addTicketComment(id: string, body: string, isInternal: boolean) {
  return apiRequest(`${path(id)}/comments`, {
    method: "POST",
    schema: z.array(ticketCommentSchema),
    body: { body, is_internal: isInternal },
  });
}

export function getTicketHistory(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/history`, { schema: z.array(ticketEventSchema), signal });
}

export function listTicketAssignees(signal?: AbortSignal) {
  return apiRequest("/tickets/assignees", { schema: z.array(assignableUserSchema), signal });
}

const attachmentPath = (id: string, attachmentId: string) =>
  `${path(id)}/attachments/${encodeURIComponent(attachmentId)}`;

export function listTicketAttachments(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/attachments`, {
    schema: z.array(ticketAttachmentSchema),
    signal,
  });
}

export function uploadTicketAttachment(id: string, file: File, isInternal = false) {
  const form = new FormData();
  form.set("file", file);
  form.set("is_internal", String(isInternal));
  return apiRequest(`${path(id)}/attachments`, {
    method: "POST",
    schema: z.array(ticketAttachmentSchema),
    body: form,
  });
}

export function deleteTicketAttachment(id: string, attachmentId: string) {
  return apiRequest(attachmentPath(id, attachmentId), { method: "DELETE", schema: z.null() });
}

export function downloadTicketAttachment(id: string, attachment: TicketAttachment) {
  return apiDownload(`${attachmentPath(id, attachment.id)}/download`, {
    fallbackName: attachment.original_filename,
  });
}

/** The image bytes for an in-page preview (shown only through a blob: URL in an <img>). */
export async function fetchTicketImage(id: string, attachmentId: string): Promise<Blob> {
  const response = await fetch(`/api/v1${attachmentPath(id, attachmentId)}/download`, {
    credentials: "same-origin",
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
