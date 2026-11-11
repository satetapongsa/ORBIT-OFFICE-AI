import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/notifications.py`. */
export const notificationTypeSchema = z.enum(["SECURITY", "ACCOUNT", "SYSTEM", "DOCUMENT", "TASK"]);

export const notificationSchema = z.object({
  id: z.string(),
  type: notificationTypeSchema,
  title: z.string(),
  body: z.string(),
  link_url: z.string().nullable(),
  entity_type: z.string().nullable(),
  entity_id: z.string().nullable(),
  read_at: z.string().nullable(),
  created_at: z.string(),
});

export const notificationPageSchema = z.object({
  items: z.array(notificationSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  unread_count: z.number().int().nonnegative(),
});

const unreadCountSchema = z.object({ unread_count: z.number().int().nonnegative() });
const markAllSchema = z.object({
  updated: z.number().int().nonnegative(),
  unread_count: z.number().int().nonnegative(),
});

export type NotificationType = z.infer<typeof notificationTypeSchema>;
export type AppNotification = z.infer<typeof notificationSchema>;
export type NotificationPage = z.infer<typeof notificationPageSchema>;

export interface NotificationListParams {
  page?: number;
  pageSize?: number;
  unreadOnly?: boolean;
}

export const notificationQueryKeys = {
  all: ["notifications"] as const,
  unreadCount: ["notifications", "unread-count"] as const,
  list: (params: NotificationListParams) => ["notifications", "list", params] as const,
};

export function listNotifications(
  { page = 1, pageSize = 20, unreadOnly = false }: NotificationListParams,
  signal?: AbortSignal,
): Promise<NotificationPage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (unreadOnly) query.set("unread_only", "true");
  return apiRequest(`/notifications?${query.toString()}`, {
    schema: notificationPageSchema,
    signal,
  });
}

export async function getUnreadCount(signal?: AbortSignal): Promise<number> {
  const result = await apiRequest("/notifications/unread-count", {
    schema: unreadCountSchema,
    signal,
  });
  return result.unread_count;
}

export function markNotificationRead(id: string): Promise<AppNotification> {
  return apiRequest(`/notifications/${encodeURIComponent(id)}/read`, {
    method: "POST",
    schema: notificationSchema,
  });
}

export function markAllNotificationsRead(): Promise<z.infer<typeof markAllSchema>> {
  return apiRequest("/notifications/read-all", { method: "POST", schema: markAllSchema });
}
