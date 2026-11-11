import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/identity.py` / `app/schemas/auth.py`. */
export const refSchema = z.object({ id: z.string(), code: z.string(), name: z.string() });

export const userSchema = z.object({
  id: z.string(),
  employee_code: z.string(),
  email: z.string(),
  first_name: z.string(),
  last_name: z.string(),
  display_name: z.string(),
  department: refSchema.nullable(),
  job_title: z.string().nullable(),
  phone_work: z.string().nullable(),
  employment_status: z.enum(["ACTIVE", "ON_LEAVE", "SUSPENDED", "TERMINATED"]),
  is_active: z.boolean(),
  roles: z.array(refSchema),
  last_login_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const meSchema = z.object({
  user: userSchema,
  permissions: z.array(z.string()),
  session: z.object({ access_expires_at: z.string() }).nullable().optional(),
});

const messageSchema = z.object({ message: z.string() });
const emptySchema = z.null();

export type User = z.infer<typeof userSchema>;
export type Me = z.infer<typeof meSchema>;

export const authQueryKeys = { me: ["auth", "me"] as const };

export function getMe(signal?: AbortSignal): Promise<Me> {
  return apiRequest("/auth/me", { schema: meSchema, signal });
}

export function login(email: string, password: string): Promise<Me> {
  return apiRequest("/auth/login", { method: "POST", schema: meSchema, body: { email, password } });
}

export function logout(): Promise<null> {
  return apiRequest("/auth/logout", { method: "POST", schema: emptySchema });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<Me> {
  return apiRequest("/auth/change-password", {
    method: "POST",
    schema: meSchema,
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export function requestPasswordReset(email: string): Promise<{ message: string }> {
  return apiRequest("/auth/password-reset/request", {
    method: "POST",
    schema: messageSchema,
    body: { email },
  });
}

export function confirmPasswordReset(
  token: string,
  newPassword: string,
): Promise<{ message: string }> {
  return apiRequest("/auth/password-reset/confirm", {
    method: "POST",
    schema: messageSchema,
    body: { token, new_password: newPassword },
  });
}

/** Only allow same-site relative redirects (blocks `//evil.com` and `javascript:` URLs). */
export function safeRedirectPath(next: string | null | undefined, fallback = "/"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}
