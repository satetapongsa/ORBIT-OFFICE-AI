import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/health.py`. */
export const componentStatusSchema = z.enum(["ok", "error", "configured", "not_configured"]);

export const componentHealthSchema = z.object({
  name: z.string(),
  status: componentStatusSchema,
  required: z.boolean(),
  latency_ms: z.number().nullable().optional(),
  detail: z.string().nullable().optional(),
});

export const readinessSchema = z.object({
  status: componentStatusSchema,
  service: z.string(),
  version: z.string(),
  environment: z.string().nullable(),
  checked_at: z.string(),
  components: z.array(componentHealthSchema),
  /** True when the public endpoint withholds component details (production). */
  details_hidden: z.boolean().default(false),
});

export type ComponentStatus = z.infer<typeof componentStatusSchema>;
export type ComponentHealth = z.infer<typeof componentHealthSchema>;
export type Readiness = z.infer<typeof readinessSchema>;

/**
 * GET /api/v1/health (or `/health/details` for administrators with `system:configure`).
 * A 503 still carries a readiness report, so it is accepted.
 */
export function getReadiness(signal?: AbortSignal, details = false): Promise<Readiness> {
  return apiRequest(details ? "/health/details" : "/health", {
    schema: readinessSchema,
    signal,
    acceptStatuses: [503],
  });
}

export const healthQueryKeys = {
  readiness: (details: boolean) => ["health", "readiness", details] as const,
};
