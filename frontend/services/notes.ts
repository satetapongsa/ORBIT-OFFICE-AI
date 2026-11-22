import { z } from "zod";

import { apiRequest } from "@/services/api-client";

/** Mirrors backend `app/schemas/messaging.py` (notes part). */
export const noteListItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  preview: z.string(),
  has_summary: z.boolean(),
  content_updated_at: z.string(),
  created_at: z.string(),
});

export const noteSchema = z.object({
  id: z.string(),
  title: z.string(),
  content: z.string(),
  ai_summary: z.string().nullable(),
  ai_summary_at: z.string().nullable(),
  summary_outdated: z.boolean(),
  content_updated_at: z.string(),
  created_at: z.string(),
});

export type NoteListItem = z.infer<typeof noteListItemSchema>;
export type Note = z.infer<typeof noteSchema>;

export const NOTE_MAX_CHARS = 20000;

export const noteQueryKeys = {
  all: ["notes"] as const,
  list: (q: string) => ["notes", "list", q] as const,
  detail: (id: string) => ["notes", "detail", id] as const,
};

export function listNotes(q: string, signal?: AbortSignal): Promise<NoteListItem[]> {
  const suffix = q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  return apiRequest(`/notes${suffix}`, { schema: z.array(noteListItemSchema), signal });
}

export function getNote(id: string, signal?: AbortSignal): Promise<Note> {
  return apiRequest(`/notes/${encodeURIComponent(id)}`, { schema: noteSchema, signal });
}

export function createNote(input: { title: string; content?: string }): Promise<Note> {
  return apiRequest("/notes", { method: "POST", schema: noteSchema, body: input });
}

export function updateNote(id: string, input: { title?: string; content?: string }): Promise<Note> {
  return apiRequest(`/notes/${encodeURIComponent(id)}`, {
    method: "PATCH",
    schema: noteSchema,
    body: input,
  });
}

export function deleteNote(id: string): Promise<null> {
  return apiRequest(`/notes/${encodeURIComponent(id)}`, { method: "DELETE", schema: z.null() });
}

export function summariseNote(id: string): Promise<Note> {
  return apiRequest(`/notes/${encodeURIComponent(id)}/summary`, {
    method: "POST",
    schema: noteSchema,
  });
}
