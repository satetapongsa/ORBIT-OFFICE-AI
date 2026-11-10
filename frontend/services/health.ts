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
  environment: z.string(),
  checked_at: z.string(),
  components: z.array(componentHealthSchema),
});

export type ComponentStatus = z.infer<typeof componentStatusSchema>;
export type ComponentHealth = z.infer<typeof componentHealthSchema>;
export type Readiness = z.infer<typeof readinessSchema>;

/** GET /api/v1/health — a 503 still carries a full readiness report, so it is accepted. */
export function getReadiness(signal?: AbortSignal): Promise<Readiness> {
  return apiRequest("/health", { schema: readinessSchema, signal, acceptStatuses: [503] });
}

export const healthQueryKeys = {
  readiness: ["health", "readiness"] as const,
};
