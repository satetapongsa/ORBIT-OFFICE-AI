import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `RoleOut` / `PermissionOut` (`app/schemas/identity.py`). */
export const permissionSchema = z.object({ code: z.string(), description: z.string() });

export const roleDetailSchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  description: z.string(),
  is_system: z.boolean(),
  /** Permissions fixed by code (ADMIN). */
  is_locked: z.boolean(),
  permissions: z.array(z.string()),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Permission = z.infer<typeof permissionSchema>;
export type RoleDetail = z.infer<typeof roleDetailSchema>;

export interface RoleInput {
  code: string;
  name: string;
  description: string;
  permissions: string[];
}

export const roleQueryKeys = {
  all: ["roles"] as const,
  list: ["roles", "list"] as const,
  permissions: ["roles", "permissions"] as const,
};

const path = (id: string) => `/roles/${encodeURIComponent(id)}`;

export function listRoleDetails(signal?: AbortSignal) {
  return apiRequest("/roles", { schema: z.array(roleDetailSchema), signal });
}

export function listPermissions(signal?: AbortSignal) {
  return apiRequest("/permissions", { schema: z.array(permissionSchema), signal });
}

export function createRole(input: RoleInput) {
  return apiRequest("/roles", { method: "POST", schema: roleDetailSchema, body: input });
}

export function updateRole(id: string, input: { name: string; description: string }) {
  return apiRequest(path(id), { method: "PATCH", schema: roleDetailSchema, body: input });
}

export function setRolePermissions(id: string, permissions: string[]) {
  return apiRequest(`${path(id)}/permissions`, {
    method: "PUT",
    schema: roleDetailSchema,
    body: { permissions },
  });
}

export function deleteRole(id: string) {
  return apiRequest(path(id), { method: "DELETE", schema: z.null() });
}
