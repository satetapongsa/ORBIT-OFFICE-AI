import { z } from "zod";

import { apiRequest } from "@/services/api-client";
import { refSchema } from "@/services/auth";
import { notificationSchema } from "@/services/notifications";

/** Mirrors backend `app/schemas/dashboard.py`. Optional sections are `null` without permission. */
const dailyCountSchema = z.object({ date: z.string(), count: z.number().int().nonnegative() });

const activityItemSchema = z.object({
  id: z.string(),
  action: z.string(),
  occurred_at: z.string(),
  actor: z.object({ id: z.string(), display_name: z.string() }).nullable(),
  entity_type: z.string().nullable(),
});

export const dashboardSummarySchema = z.object({
  generated_at: z.string(),
  timezone: z.string(),
  period_days: z.number().int().positive(),
  account: z.object({
    display_name: z.string(),
    job_title: z.string().nullable(),
    department: refSchema.nullable(),
    roles: z.array(refSchema),
    last_login_at: z.string().nullable(),
    previous_login_at: z.string().nullable(),
    password_changed_at: z.string().nullable(),
    active_sessions: z.number().int().nonnegative(),
  }),
  notifications: z.object({
    unread_count: z.number().int().nonnegative(),
    latest: z.array(notificationSchema),
  }),
  my_activity: z.object({
    daily_sign_ins: z.array(dailyCountSchema),
    recent: z.array(activityItemSchema),
  }),
  documents: z
    .object({
      accessible_count: z.number().int().nonnegative(),
      my_documents: z.number().int().nonnegative(),
      my_processing: z.number().int().nonnegative(),
      my_failed: z.number().int().nonnegative(),
      recent: z.array(
        z.object({
          id: z.string(),
          title: z.string(),
          category: z.string(),
          file_type: z.string().nullable(),
          processing_status: z.string().nullable(),
          updated_at: z.string(),
        }),
      ),
    })
    .nullable(),
  organization: z
    .object({
      active_users: z.number().int().nonnegative(),
      inactive_users: z.number().int().nonnegative(),
      departments: z.number().int().nonnegative(),
      users_by_department: z.array(
        z.object({ department: refSchema.nullable(), count: z.number().int().nonnegative() }),
      ),
    })
    .nullable(),
  security: z
    .object({
      sign_ins: z.number().int().nonnegative(),
      failed_sign_ins: z.number().int().nonnegative(),
      rate_limited: z.number().int().nonnegative(),
      daily: z.array(
        z.object({
          date: z.string(),
          sign_ins: z.number().int().nonnegative(),
          failed_sign_ins: z.number().int().nonnegative(),
        }),
      ),
      recent: z.array(activityItemSchema),
    })
    .nullable(),
});

export type DashboardSummary = z.infer<typeof dashboardSummarySchema>;
export type ActivityItem = z.infer<typeof activityItemSchema>;

export const dashboardQueryKeys = { summary: ["dashboard", "summary"] as const };

export function getDashboardSummary(signal?: AbortSignal): Promise<DashboardSummary> {
  return apiRequest("/dashboard/summary", { schema: dashboardSummarySchema, signal });
}
