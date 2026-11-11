import { z } from "zod";

import { apiRequest } from "@/services/api-client";
import { refSchema, userSchema } from "@/services/auth";

/** Mirrors backend `app/schemas/employees.py` (+ `/users`, `/departments`, `/roles`). */
export const employmentStatusSchema = z.enum(["ACTIVE", "ON_LEAVE", "SUSPENDED", "TERMINATED"]);
export const employmentTypeSchema = z.enum(["FULL_TIME", "PART_TIME", "CONTRACT", "INTERN"]);

const userRefSchema = z.object({ id: z.string(), display_name: z.string() });

export const employeeSchema = z.object({
  id: z.string(),
  employee_code: z.string(),
  display_name: z.string(),
  first_name: z.string(),
  last_name: z.string(),
  job_title: z.string().nullable(),
  department: refSchema.nullable(),
  email: z.string(),
  phone_work: z.string().nullable(),
  is_active: z.boolean(),
});

export const employeePageSchema = z.object({
  items: z.array(employeeSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});

export const employeeProfileSchema = employeeSchema.extend({
  department_manager: userRefSchema.nullable(),
  account: z
    .object({
      employment_status: employmentStatusSchema,
      roles: z.array(refSchema),
      last_login_at: z.string().nullable(),
      created_at: z.string(),
    })
    .nullable(),
  capabilities: z.object({
    can_edit_account: z.boolean(),
    can_manage_roles: z.boolean(),
    can_change_active: z.boolean(),
    can_view_hr: z.boolean(),
    can_edit_hr: z.boolean(),
  }),
});

export const emergencyContactSchema = z.object({
  name: z.string(),
  relationship: z.string(),
  phone: z.string(),
});

export const hrProfileSchema = z.object({
  user_id: z.string(),
  exists: z.boolean(),
  date_of_birth: z.string().nullable(),
  national_id_last4: z.string().nullable(),
  personal_phone: z.string().nullable(),
  personal_email: z.string().nullable(),
  address: z.string().nullable(),
  hire_date: z.string().nullable(),
  employment_type: employmentTypeSchema.nullable(),
  emergency_contact: emergencyContactSchema.nullable(),
  updated_at: z.string().nullable(),
  updated_by: userRefSchema.nullable(),
});

export const departmentSchema = refSchema.extend({
  description: z.string().nullable(),
  parent_id: z.string().nullable(),
  manager_id: z.string().nullable(),
  member_count: z.number().int().nonnegative(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type EmploymentStatus = z.infer<typeof employmentStatusSchema>;
export type EmploymentType = z.infer<typeof employmentTypeSchema>;
export type Employee = z.infer<typeof employeeSchema>;
export type EmployeePage = z.infer<typeof employeePageSchema>;
export type EmployeeProfile = z.infer<typeof employeeProfileSchema>;
export type HrProfile = z.infer<typeof hrProfileSchema>;
export type Department = z.infer<typeof departmentSchema>;

export type HrProfileInput = Omit<HrProfile, "user_id" | "exists" | "updated_at" | "updated_by">;

export interface EmployeeListParams {
  q?: string;
  departmentId?: string;
  includeInactive?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AccountInput {
  employee_code: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name?: string | null;
  department_id: string | null;
  job_title: string | null;
  phone_work: string | null;
  employment_status: EmploymentStatus;
}

export interface CreateAccountInput extends AccountInput {
  password?: string;
}

export interface DepartmentInput {
  code: string;
  name: string;
  description: string | null;
  manager_id: string | null;
}

export const employeeQueryKeys = {
  all: ["employees"] as const,
  list: (params: EmployeeListParams) => ["employees", "list", params] as const,
  profile: (id: string) => ["employees", "profile", id] as const,
  hr: (id: string) => ["employees", "hr", id] as const,
  departments: ["departments", "full"] as const,
};

const path = (id: string) => `/employees/${encodeURIComponent(id)}`;

export function listEmployees(params: EmployeeListParams, signal?: AbortSignal) {
  return apiRequest("/employees", {
    schema: employeePageSchema,
    signal,
    query: {
      q: params.q || undefined,
      department_id: params.departmentId || undefined,
      include_inactive: params.includeInactive || undefined,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 24,
    },
  });
}

export function getEmployee(id: string, signal?: AbortSignal) {
  return apiRequest(path(id), { schema: employeeProfileSchema, signal });
}

export function getHrProfile(id: string, signal?: AbortSignal) {
  return apiRequest(`${path(id)}/hr`, { schema: hrProfileSchema, signal });
}

export function replaceHrProfile(id: string, input: HrProfileInput) {
  return apiRequest(`${path(id)}/hr`, { method: "PUT", schema: hrProfileSchema, body: input });
}

// --- Account administration (existing /users API) ---------------------------------------

export function createAccount(input: CreateAccountInput) {
  return apiRequest("/users", { method: "POST", schema: userSchema, body: input });
}

export function updateAccount(id: string, input: Partial<AccountInput>) {
  return apiRequest(`/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: userSchema,
    body: input,
  });
}

export function setAccountActive(id: string, active: boolean) {
  return apiRequest(`/users/${encodeURIComponent(id)}/${active ? "activate" : "deactivate"}`, {
    method: "POST",
    schema: userSchema,
  });
}

export function setAccountRoles(id: string, roleCodes: string[]) {
  return apiRequest(`/users/${encodeURIComponent(id)}/roles`, {
    method: "PUT",
    schema: userSchema,
    body: { role_codes: roleCodes },
  });
}

// --- Departments ------------------------------------------------------------------------

export function listDepartmentsFull(signal?: AbortSignal) {
  return apiRequest("/departments", { schema: z.array(departmentSchema), signal });
}

export function createDepartment(input: DepartmentInput) {
  return apiRequest("/departments", { method: "POST", schema: departmentSchema, body: input });
}

export function updateDepartment(id: string, input: Partial<DepartmentInput>) {
  return apiRequest(`/departments/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: departmentSchema,
    body: input,
  });
}
