import { z } from "zod";

import { apiDownload, apiRequest } from "@/services/api-client";
import { refSchema } from "@/services/auth";

/** Mirrors backend `app/schemas/documents.py`. */
export const categorySchema = z.enum([
  "POLICY",
  "PROCEDURE",
  "FORM",
  "REPORT",
  "CONTRACT",
  "MANUAL",
  "OTHER",
]);
export const visibilitySchema = z.enum(["PRIVATE", "DEPARTMENT", "COMPANY", "RESTRICTED"]);
export const documentStatusSchema = z.enum(["DRAFT", "ACTIVE", "ARCHIVED"]);
export const fileTypeSchema = z.enum(["PDF", "DOCX", "XLSX", "TXT"]);
export const processingStatusSchema = z.enum(["PENDING", "PROCESSING", "READY", "FAILED"]);
export const accessLevelSchema = z.enum(["VIEW", "EDIT", "MANAGE"]);
export const principalTypeSchema = z.enum(["USER", "DEPARTMENT", "ROLE"]);

const userRefSchema = z.object({ id: z.string(), display_name: z.string() });

const versionSummarySchema = z.object({
  id: z.string(),
  version_number: z.number().int().positive(),
  original_filename: z.string(),
  file_type: fileTypeSchema,
  size_bytes: z.number().int().nonnegative(),
  processing_status: processingStatusSchema,
});

export const versionSchema = versionSummarySchema.extend({
  mime_type: z.string(),
  sha256: z.string(),
  uploaded_by: userRefSchema.nullable(),
  processing_error: z.string().nullable(),
  page_count: z.number().int().nullable(),
  char_count: z.number().int().nullable(),
  processed_at: z.string().nullable(),
  created_at: z.string(),
});

export const documentListItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  category: categorySchema,
  visibility: visibilitySchema,
  status: documentStatusSchema,
  owner: userRefSchema,
  department: refSchema.nullable(),
  current_version: versionSummarySchema.nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const documentDetailSchema = documentListItemSchema.extend({
  access_level: accessLevelSchema,
  capabilities: z.object({
    can_edit: z.boolean(),
    can_manage: z.boolean(),
    can_delete: z.boolean(),
    can_manage_access: z.boolean(),
    can_upload_version: z.boolean(),
    can_view_history: z.boolean(),
  }),
  versions: z.array(versionSchema),
});

export const documentPageSchema = z.object({
  items: z.array(documentListItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
});

export const aclEntrySchema = z.object({
  id: z.string(),
  principal_type: principalTypeSchema,
  principal_id: z.string(),
  principal_name: z.string(),
  access_level: accessLevelSchema,
  granted_by: userRefSchema.nullable(),
  created_at: z.string(),
});

export const aclSchema = z.object({
  visibility: visibilitySchema,
  owner: userRefSchema,
  entries: z.array(aclEntrySchema),
});

export const documentTextSchema = z.object({
  version_id: z.string(),
  version_number: z.number().int(),
  content: z.string(),
  char_count: z.number().int().nonnegative(),
  truncated: z.boolean(),
});

export const historyItemSchema = z.object({
  id: z.string(),
  action: z.string(),
  occurred_at: z.string(),
  actor: userRefSchema.nullable(),
  details: z.record(z.string(), z.unknown()),
});

export const directoryUserSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  job_title: z.string().nullable(),
  department: refSchema.nullable(),
});

const departmentSchema = refSchema.passthrough();
const roleSchema = refSchema.passthrough();

export type DocumentCategory = z.infer<typeof categorySchema>;
export type DocumentVisibility = z.infer<typeof visibilitySchema>;
export type DocumentStatus = z.infer<typeof documentStatusSchema>;
export type ProcessingStatus = z.infer<typeof processingStatusSchema>;
export type AccessLevel = z.infer<typeof accessLevelSchema>;
export type PrincipalType = z.infer<typeof principalTypeSchema>;
export type DocumentListItem = z.infer<typeof documentListItemSchema>;
export type DocumentDetail = z.infer<typeof documentDetailSchema>;
export type DocumentPage = z.infer<typeof documentPageSchema>;
export type DocumentVersion = z.infer<typeof versionSchema>;
export type AclEntry = z.infer<typeof aclEntrySchema>;
export type DocumentAcl = z.infer<typeof aclSchema>;
export type DocumentText = z.infer<typeof documentTextSchema>;
export type HistoryItem = z.infer<typeof historyItemSchema>;
export type DirectoryUser = z.infer<typeof directoryUserSchema>;

export interface DocumentListParams {
  q?: string;
  category?: DocumentCategory;
  visibility?: DocumentVisibility;
  status?: DocumentStatus;
  mine?: boolean;
  sort?: "updated" | "created" | "title";
  page?: number;
  pageSize?: number;
}

export interface DocumentUploadInput {
  file: File;
  title: string;
  description?: string;
  category: DocumentCategory;
  visibility: DocumentVisibility;
}

export interface DocumentUpdateInput {
  title?: string;
  description?: string | null;
  category?: DocumentCategory;
  status?: DocumentStatus;
  visibility?: DocumentVisibility;
}

export interface AclEntryInput {
  principal_type: PrincipalType;
  principal_id: string;
  access_level: AccessLevel;
}

export const documentQueryKeys = {
  all: ["documents"] as const,
  list: (params: DocumentListParams) => ["documents", "list", params] as const,
  detail: (id: string) => ["documents", "detail", id] as const,
  text: (id: string, versionId: string | null) => ["documents", "text", id, versionId] as const,
  acl: (id: string) => ["documents", "acl", id] as const,
  history: (id: string) => ["documents", "history", id] as const,
};

export function listDocuments(params: DocumentListParams, signal?: AbortSignal) {
  return apiRequest("/documents", {
    schema: documentPageSchema,
    signal,
    query: {
      q: params.q || undefined,
      category: params.category,
      visibility: params.visibility,
      status: params.status,
      mine: params.mine || undefined,
      sort: params.sort,
      page: params.page ?? 1,
      page_size: params.pageSize ?? 20,
    },
  });
}

export function getDocument(id: string, signal?: AbortSignal) {
  return apiRequest(`/documents/${encodeURIComponent(id)}`, {
    schema: documentDetailSchema,
    signal,
  });
}

export function uploadDocument(input: DocumentUploadInput) {
  const form = new FormData();
  form.set("file", input.file);
  form.set("title", input.title);
  if (input.description) form.set("description", input.description);
  form.set("category", input.category);
  form.set("visibility", input.visibility);
  return apiRequest("/documents", { method: "POST", schema: documentDetailSchema, body: form });
}

export function uploadVersion(id: string, file: File) {
  const form = new FormData();
  form.set("file", file);
  return apiRequest(`/documents/${encodeURIComponent(id)}/versions`, {
    method: "POST",
    schema: documentDetailSchema,
    body: form,
  });
}

export function updateDocument(id: string, input: DocumentUpdateInput) {
  return apiRequest(`/documents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: documentDetailSchema,
    body: input,
  });
}

export function deleteDocument(id: string) {
  return apiRequest(`/documents/${encodeURIComponent(id)}`, {
    method: "DELETE",
    schema: z.null(),
  });
}

export function reprocessVersion(id: string, versionId: string) {
  return apiRequest(
    `/documents/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/reprocess`,
    { method: "POST", schema: documentDetailSchema },
  );
}

export function getDocumentText(id: string, versionId: string | null, signal?: AbortSignal) {
  return apiRequest(`/documents/${encodeURIComponent(id)}/text`, {
    schema: documentTextSchema,
    signal,
    query: { version_id: versionId ?? undefined },
  });
}

export function getDocumentAcl(id: string, signal?: AbortSignal) {
  return apiRequest(`/documents/${encodeURIComponent(id)}/acl`, { schema: aclSchema, signal });
}

export function replaceDocumentAcl(id: string, entries: AclEntryInput[]) {
  return apiRequest(`/documents/${encodeURIComponent(id)}/acl`, {
    method: "PUT",
    schema: aclSchema,
    body: { entries },
  });
}

export function getDocumentHistory(id: string, signal?: AbortSignal) {
  return apiRequest(`/documents/${encodeURIComponent(id)}/history`, {
    schema: z.array(historyItemSchema),
    signal,
  });
}

export function downloadDocument(id: string, versionId?: string, fallbackName?: string) {
  return apiDownload(`/documents/${encodeURIComponent(id)}/download`, {
    query: { version_id: versionId },
    fallbackName,
  });
}

export function searchDirectory(q: string, signal?: AbortSignal) {
  return apiRequest("/directory/users", {
    schema: z.array(directoryUserSchema),
    signal,
    query: { q: q || undefined, limit: 10 },
  });
}

export function listDepartments(signal?: AbortSignal) {
  return apiRequest("/departments", { schema: z.array(departmentSchema), signal });
}

export function listRoles(signal?: AbortSignal) {
  return apiRequest("/roles", { schema: z.array(roleSchema), signal });
}
