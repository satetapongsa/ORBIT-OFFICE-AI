import { z } from "zod";

/** Mirrors backend `app/schemas/common.py`. */
export const errorDetailSchema = z.object({
  field: z.string().nullable().optional(),
  message: z.string(),
});

export const errorBodySchema = z.object({
  code: z.string(),
  message: z.string(),
  details: z.array(errorDetailSchema).default([]),
  request_id: z.string().nullable().optional(),
});

export const errorResponseSchema = z.object({ error: errorBodySchema });

export type ApiErrorBody = z.infer<typeof errorBodySchema>;

export const pageSchema = <T extends z.ZodType>(item: T) =>
  z.object({
    items: z.array(item),
    total: z.number().int().nonnegative(),
    page: z.number().int().positive(),
    page_size: z.number().int().positive(),
  });
