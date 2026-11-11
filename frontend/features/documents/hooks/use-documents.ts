"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { dashboardQueryKeys } from "@/services/dashboard";
import {
  deleteDocument,
  documentQueryKeys,
  getDocument,
  getDocumentAcl,
  getDocumentHistory,
  getDocumentText,
  listDepartments,
  listDocuments,
  listRoles,
  replaceDocumentAcl,
  reprocessVersion,
  searchDirectory,
  updateDocument,
  uploadDocument,
  uploadVersion,
  type AclEntryInput,
  type DocumentDetail,
  type DocumentListParams,
  type DocumentUpdateInput,
  type DocumentUploadInput,
} from "@/services/documents";
import { notificationQueryKeys } from "@/services/notifications";

const POLL_MS = 3_000;

function isProcessing(detail: DocumentDetail | undefined): boolean {
  return Boolean(
    detail?.versions.some(
      (v) => v.processing_status === "PENDING" || v.processing_status === "PROCESSING",
    ),
  );
}

export function useDocumentList(params: DocumentListParams) {
  return useQuery({
    queryKey: documentQueryKeys.list(params),
    queryFn: ({ signal }) => listDocuments(params, signal),
    placeholderData: (previous) => previous,
    staleTime: 10_000,
    // Keep processing badges fresh while something in view is still being processed.
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (d) =>
          d.current_version?.processing_status === "PENDING" ||
          d.current_version?.processing_status === "PROCESSING",
      )
        ? POLL_MS
        : false,
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: documentQueryKeys.detail(id),
    queryFn: ({ signal }) => getDocument(id, signal),
    refetchInterval: (query) => (isProcessing(query.state.data) ? POLL_MS : false),
  });
}

export function useDocumentText(id: string, versionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: documentQueryKeys.text(id, versionId),
    queryFn: ({ signal }) => getDocumentText(id, versionId, signal),
    enabled,
    staleTime: 60_000,
  });
}

export function useDocumentAcl(id: string, enabled: boolean) {
  return useQuery({
    queryKey: documentQueryKeys.acl(id),
    queryFn: ({ signal }) => getDocumentAcl(id, signal),
    enabled,
  });
}

export function useDocumentHistory(id: string, enabled: boolean) {
  return useQuery({
    queryKey: documentQueryKeys.history(id),
    queryFn: ({ signal }) => getDocumentHistory(id, signal),
    enabled,
  });
}

export function useDirectorySearch(q: string, enabled: boolean) {
  return useQuery({
    queryKey: ["directory", "users", q],
    queryFn: ({ signal }) => searchDirectory(q, signal),
    enabled,
    staleTime: 30_000,
  });
}

export function useDepartments(enabled: boolean) {
  return useQuery({
    queryKey: ["departments"],
    queryFn: ({ signal }) => listDepartments(signal),
    enabled,
    staleTime: 300_000,
  });
}

export function useRoles(enabled: boolean) {
  return useQuery({
    queryKey: ["roles"],
    queryFn: ({ signal }) => listRoles(signal),
    enabled,
    staleTime: 300_000,
  });
}

function useInvalidateDocuments() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: documentQueryKeys.all }),
      client.invalidateQueries({ queryKey: dashboardQueryKeys.summary }),
      client.invalidateQueries({ queryKey: notificationQueryKeys.all }),
    ]);
}

export function useUploadDocument() {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (input: DocumentUploadInput) => uploadDocument(input),
    onSuccess: () => invalidate(),
  });
}

export function useUploadVersion(id: string) {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (file: File) => uploadVersion(id, file),
    onSuccess: () => invalidate(),
  });
}

export function useUpdateDocument(id: string) {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (input: DocumentUpdateInput) => updateDocument(id, input),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteDocument(id: string) {
  const client = useQueryClient();
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: () => deleteDocument(id),
    onSuccess: async () => {
      client.removeQueries({ queryKey: documentQueryKeys.detail(id) });
      await invalidate();
    },
  });
}

export function useReprocessVersion(id: string) {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (versionId: string) => reprocessVersion(id, versionId),
    onSuccess: () => invalidate(),
  });
}

export function useReplaceAcl(id: string) {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (entries: AclEntryInput[]) => replaceDocumentAcl(id, entries),
    onSuccess: () => invalidate(),
  });
}
