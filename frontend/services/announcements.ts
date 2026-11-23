import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/announcements.py` (ADR-067). */
export const announcementSchema = z.object({
  id: z.string(),
  title: z.string(),
  body: z.string(),
  important: z.boolean(),
  pinned: z.boolean(),
  department_id: z.string().nullable(),
  department_name: z.string().nullable(),
  author_name: z.string().nullable(),
  published_at: z.string(),
  expires_at: z.string().nullable(),
  expired: z.boolean(),
  edited: z.boolean(),
  is_read: z.boolean(),
  read_count: z.number().int().nullable().optional(),
  audience_count: z.number().int().nullable().optional(),
});

const listSchema = z.object({
  items: z.array(announcementSchema),
  unread_count: z.number().int().nonnegative(),
});
const unreadSchema = z.object({ unread_count: z.number().int().nonnegative() });

export type Announcement = z.infer<typeof announcementSchema>;

export interface AnnouncementInput {
  title: string;
  body: string;
  important: boolean;
  pinned: boolean;
  department_id: string | null;
  expires_at: string | null;
  notify?: boolean;
}

export const ANNOUNCEMENT_BODY_MAX_CHARS = 10000;

export const announcementQueryKeys = {
  all: ["announcements"] as const,
  list: (includeExpired: boolean) => ["announcements", "list", includeExpired] as const,
  unread: ["announcements", "unread"] as const,
};

export function listAnnouncements(includeExpired: boolean, signal?: AbortSignal) {
  return apiRequest("/announcements", {
    schema: listSchema,
    signal,
    query: { include_expired: includeExpired || undefined },
  });
}

export function getAnnouncementUnread(signal?: AbortSignal) {
  return apiRequest("/announcements/unread-count", { schema: unreadSchema, signal });
}

export function markAnnouncementRead(id: string) {
  return apiRequest(`/announcements/${encodeURIComponent(id)}/read`, {
    method: "POST",
    schema: unreadSchema,
  });
}

export function markAllAnnouncementsRead() {
  return apiRequest("/announcements/read-all", { method: "POST", schema: z.null() });
}

export function createAnnouncement(input: AnnouncementInput): Promise<Announcement> {
  return apiRequest("/announcements", { method: "POST", schema: announcementSchema, body: input });
}

export function updateAnnouncement(id: string, input: AnnouncementInput): Promise<Announcement> {
  const { title, body, important, pinned, department_id, expires_at } = input;
  return apiRequest(`/announcements/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: announcementSchema,
    body: {
      title,
      body,
      important,
      pinned,
      ...(department_id ? { department_id } : { whole_company: true }),
      ...(expires_at ? { expires_at } : { clear_expiry: true }),
    },
  });
}

export function deleteAnnouncement(id: string) {
  return apiRequest(`/announcements/${encodeURIComponent(id)}`, {
    method: "DELETE",
    schema: z.null(),
  });
}
