import { z } from "zod";

import { apiDownload, apiRequest } from "@/services/api-client";
import { refSchema } from "@/services/auth";

/** Mirrors backend `app/schemas/analytics.py`. */
export const analyticsScopeSchema = z.enum(["own", "department", "all"]);

const countSchema = z.object({ key: z.string(), count: z.number().int().nonnegative() });
const dailySchema = z.object({
  date: z.string(),
  opened: z.number().int().nonnegative(),
  closed: z.number().int().nonnegative(),
});
const userRefSchema = z.object({ id: z.string(), display_name: z.string() });

export const analyticsOverviewSchema = z.object({
  scope: analyticsScopeSchema,
  department: refSchema.nullable(),
  date_from: z.string(),
  date_to: z.string(),
  timezone: z.string(),
  generated_at: z.string(),
  available_scopes: z.array(analyticsScopeSchema),
  can_export: z.boolean(),
  tasks: z.object({
    open: z.number().int(),
    overdue: z.number().int(),
    created: z.number().int(),
    completed: z.number().int(),
    completion_rate: z.number().nullable(),
    avg_completion_hours: z.number().nullable(),
    by_status: z.array(countSchema),
    open_by_priority: z.array(countSchema),
    daily: z.array(dailySchema),
    workload: z.array(
      z.object({
        user: userRefSchema,
        open: z.number().int().nonnegative(),
        overdue: z.number().int().nonnegative(),
        completed: z.number().int().nonnegative(),
      }),
    ),
  }),
  tickets: z.object({
    open: z.number().int(),
    opened: z.number().int(),
    resolved: z.number().int(),
    avg_resolution_hours: z.number().nullable(),
    by_status: z.array(countSchema),
    by_category: z.array(countSchema),
    daily: z.array(dailySchema),
  }),
  documents: z.object({
    total: z.number().int(),
    uploaded: z.number().int(),
    by_category: z.array(countSchema),
  }),
});

export const analyticsSummarySchema = z.object({
  summary: z.string(),
  model: z.string(),
  generated_at: z.string(),
});

export type AnalyticsScope = z.infer<typeof analyticsScopeSchema>;
export type AnalyticsOverview = z.infer<typeof analyticsOverviewSchema>;
export type AnalyticsSummary = z.infer<typeof analyticsSummarySchema>;

export interface AnalyticsParams {
  scope: AnalyticsScope;
  /** `YYYY-MM-DD`; omitted = the last 30 days. */
  dateFrom?: string;
  dateTo?: string;
}

export const analyticsQueryKeys = {
  all: ["analytics"] as const,
  overview: (params: AnalyticsParams) => ["analytics", "overview", params] as const,
};

const query = (p: AnalyticsParams) => ({
  scope: p.scope,
  date_from: p.dateFrom || undefined,
  date_to: p.dateTo || undefined,
});

export function getAnalyticsOverview(params: AnalyticsParams, signal?: AbortSignal) {
  return apiRequest("/analytics/overview", {
    schema: analyticsOverviewSchema,
    signal,
    query: query(params),
  });
}

export function summarizeAnalytics(params: AnalyticsParams) {
  return apiRequest("/analytics/summary", {
    method: "POST",
    schema: analyticsSummarySchema,
    body: {
      scope: params.scope,
      date_from: params.dateFrom || null,
      date_to: params.dateTo || null,
    },
  });
}

export function downloadReport(params: AnalyticsParams, format: "xlsx" | "pdf") {
  return apiDownload(`/reports/overview.${format}`, {
    query: query(params),
    fallbackName: `aura-report.${format}`,
  });
}
