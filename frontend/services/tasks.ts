import { z } from "zod";

import { apiDownload, apiRequest } from "@/services/api-client";
import { refSchema } from "@/services/auth";
import { fileTypeSchema } from "@/services/documents";

/** Mirrors backend `app/schemas/tasks.py`. */
export const taskStatusSchema = z.enum(["TODO", "IN_PROGRESS", "REVIEW", "COMPLETED", "CANCELLED"]);
export const taskPrioritySchema = z.enum(["LOW", "MEDIUM", "HIGH", "URGENT"]);
export const taskEventTypeSchema = z.enum([
  "CREATED",
  "UPDATED",
  "STATUS_CHANGED",
  "ASSIGNED",
  "UNASSIGNED",
  "COMMENTED",
  "ATTACHMENT_ADDED",
  "ATTACHMENT_REMOVED",
]);

const userRefSchema = z.object({ id: z.string(), display_name: z.string() });

export const taskListItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: taskStatusSchema,
  priority: taskPrioritySchema,
  due_at: z.string().nullable(),
  is_overdue: z.boolean(),
  department: refSchema.nullable(),
  created_by: userRefSchema,
  assignees: z.array(userRefSchema),
  comment_count: z.number().int().nonnegative(),
  attachment_count: z.number().int().nonnegative(),
  completed_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const taskCapabilitiesSchema = z.object({
  can_edit: z.boolean(),
  can_change_status: z.boolean(),
  can_cancel: z.boolean(),
  can_assign: z.boolean(),
  can_delete: z.boolean(),
  can_comment: z.boolean(),
  can_attach: z.boolean(),
});

export const taskDetailSchema = taskListItemSchema.extend({
  description: z.string().nullable(),
  capabilities: taskCapabilitiesSchema,
});

export const taskPageSchema = z.object({
  items: z.array(taskListItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});

export const taskCommentSchema = z.object({
  id: z.string(),
  author: userRefSchema.nullable(),
  body: z.string(),
  created_at: z.string(),
  edited_at: z.string().nullable(),
  can_edit: z.boolean(),
  can_delete: z.boolean(),
});

export const taskAttachmentSchema = z.object({
  id: z.string(),
  original_filename: z.string(),
  file_type: fileTypeSchema,
  size_bytes: z.number().int().nonnegative(),
  uploaded_by: userRefSchema.nullable(),
  created_at: z.string(),
  can_delete: z.boolean(),
});

export const taskEventSchema = z.object({
  id: z.string(),
  event_type: taskEventTypeSchema,
  actor: userRefSchema.nullable(),
  from_value: z.string().nullable(),
  to_value: z.string().nullable(),
  created_at: z.string(),
});

export const assignableUserSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  job_title: z.string().nullable(),
  department: refSchema.nullable(),
});

export type TaskStatus = z.infer<typeof taskStatusSchema>;
export type TaskPriority = z.infer<typeof taskPrioritySchema>;
export type TaskEventType = z.infer<typeof taskEventTypeSchema>;
export type TaskListItem = z.infer<typeof taskListItemSchema>;
export type TaskDetail = z.infer<typeof taskDetailSchema>;
export type TaskPage = z.infer<typeof taskPageSchema>;
export type TaskComment = z.infer<typeof taskCommentSchema>;
export type TaskAttachment = z.infer<typeof taskAttachmentSchema>;
export type TaskEvent = z.infer<typeof taskEventSchema>;
export type AssignableUser = z.infer<typeof assignableUserSchema>;
export type TaskScope = "all" | "assigned" | "created" | "department";
export type TaskSort = "due" | "updated" | "created" | "priority";

export interface TaskListParams {
  scope?: TaskScope;
  q?: string;
  status?: TaskStatus;
  openOnly?: boolean;
  priority?: TaskPriority;
  overdue?: boolean;
  sort?: TaskSort;
  page?: number;
  pageSize?: number;
}

export interface TaskInput {
  title: string;
  description?: string | null;
  priority: TaskPriority;
  due_at?: string | null;
  assignee_ids?: string[];
}

export const taskQueryKeys = {
  all: ["tasks"] as const,
  list: (params: TaskListParams) => ["tasks", "list", params] as const,
  detail: (id: string) => ["tasks", "detail", id] as const,
  comments: (id: string) => ["tasks", "comments", id] as const,
  attachments: (id: string) => ["tasks", "attachments", id] as const,
  history: (id: string) => ["tasks", "history", id] as const,
  assignable: (q: string) => ["tasks", "assignable", q] as const,
};

const path = (id: string) => `/tasks/${encodeURIComponent(id)}`;

export function listTasks(params: TaskListParams, signal?: AbortSignal) {
  return apiRequest("/tasks", {
    schema: taskPageSchema,
    signal,
    query: {
      scope: params.scope ?? "all",
      q: params.q || undefined,
      status: params.status,
      open_only: params.openOnly || undefined,
      priority: params.priority,
      overdue: params.overdue || undefined,
      sort: params.sort ?? "due",
      page: params.page ?? 1,
      page_size: params.pageSize ?? 20,
    },
  });
}

export function getTask(id: string, signal?: AbortSignal) {
  return apiRequest(path(id), { schema: taskDetailSchema, signal });
}

export function createTask(input: TaskInput) {
  return apiRequest("/tasks", { method: "POST", schema: taskDetailSchema, body: input });
}

export function updateTask(id: string, input: Partial<Omit<TaskInput, "assignee_ids">>) {
  return apiRequest(path(id), { method: "PATCH", schema: taskDetailSchema, body: input });
}

export function changeTaskStatus(id: string, status: TaskStatus) {
  return apiRequest(`${path(id)}/status`, {
    method: "POST",
    schema: taskDetailSchema,
    body: { status },
  });
}

export function replaceAssignees(id: string, userIds: string[]) {
  return apiRequest(`${path(id)}/assignees`, {
    method: "PUT",
    schema: taskDetailSchema,
    body: { user_ids: userIds },
  });
}

export function deleteTask(id: string) {
  return apiRequest(path(id), { method: "DELETE", schema: z.null() });
}

export function listComments(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/comments`, { schema: z.array(taskCommentSchema), signal });
}

export function addComment(id: string, body: string) {
  return apiRequest(`${path(id)}/comments`, {
    method: "POST",
    schema: z.array(taskCommentSchema),
    body: { body },
  });
}

export function editComment(id: string, commentId: string, body: string) {
  return apiRequest(`${path(id)}/comments/${encodeURIComponent(commentId)}`, {
    method: "PATCH",
    schema: z.array(taskCommentSchema),
    body: { body },
  });
}

export function deleteComment(id: string, commentId: string) {
  return apiRequest(`${path(id)}/comments/${encodeURIComponent(commentId)}`, {
    method: "DELETE",
    schema: z.null(),
  });
}

export function listAttachments(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/attachments`, {
    schema: z.array(taskAttachmentSchema),
    signal,
  });
}

export function uploadAttachment(id: string, file: File) {
  const form = new FormData();
  form.set("file", file);
  return apiRequest(`${path(id)}/attachments`, {
    method: "POST",
    schema: z.array(taskAttachmentSchema),
    body: form,
  });
}

export function deleteAttachment(id: string, attachmentId: string) {
  return apiRequest(`${path(id)}/attachments/${encodeURIComponent(attachmentId)}`, {
    method: "DELETE",
    schema: z.null(),
  });
}

export function downloadAttachment(id: string, attachment: TaskAttachment) {
  return apiDownload(`${path(id)}/attachments/${encodeURIComponent(attachment.id)}/download`, {
    fallbackName: attachment.original_filename,
  });
}

export function getTaskHistory(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/history`, { schema: z.array(taskEventSchema), signal });
}

export function searchAssignable(q: string, signal?: AbortSignal) {
  return apiRequest("/tasks/assignable-users", {
    schema: z.array(assignableUserSchema),
    signal,
    query: { q: q || undefined, limit: 20 },
  });
}
