import { z } from "zod";

import { categorySchema, visibilitySchema } from "@/services/documents";

/** Mirrors backend `DocumentCreate` / `DocumentUpdate` limits. */
export const documentMetaSchema = z.object({
  title: z.string().trim().min(1, "กรุณาระบุชื่อเอกสาร").max(300, "ชื่อเอกสารยาวเกิน 300 ตัวอักษร"),
  description: z.string().trim().max(4000, "คำอธิบายยาวเกิน 4,000 ตัวอักษร"),
  category: categorySchema,
  visibility: visibilitySchema,
});

export type DocumentMetaValues = z.infer<typeof documentMetaSchema>;

/** Default title from a filename: drop the extension, turn separators into spaces. */
export function titleFromFilename(name: string): string {
  const stem = name.replace(/\.[^.]+$/, "");
  return stem.replace(/[_]+/g, " ").trim().slice(0, 300);
}
