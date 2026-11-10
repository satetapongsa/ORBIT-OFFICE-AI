import { z } from "zod";

import { errorResponseSchema, type ApiErrorBody } from "@/types/api";

/** Same-origin API base. Requests are proxied to the backend (Next.js rewrites / Nginx). */
export const API_BASE_PATH = "/api/v1";

const NETWORK_ERROR_MESSAGE =
  "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้ กรุณาตรวจสอบการเชื่อมต่อแล้วลองใหม่";
const GENERIC_ERROR_MESSAGE = "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง";
const INVALID_RESPONSE_MESSAGE = "ได้รับข้อมูลจากเซิร์ฟเวอร์ในรูปแบบที่ไม่ถูกต้อง";

/** Error thrown for any failed API call. `code` matches the backend error envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ApiErrorBody["details"];
  readonly requestId: string | null;
  /** Parsed response body, when the server answered with JSON (e.g. a 503 health report). */
  readonly body: unknown;

  constructor(params: {
    status: number;
    code: string;
    message: string;
    details?: ApiErrorBody["details"];
    requestId?: string | null;
    body?: unknown;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.details = params.details ?? [];
    this.requestId = params.requestId ?? null;
    this.body = params.body;
  }
}

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ApiRequestOptions<TSchema extends z.ZodType> {
  method?: HttpMethod;
  /** Zod schema used to validate the success response. */
  schema: TSchema;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Treat these non-2xx statuses as successful responses (validated with `schema`). */
  acceptStatuses?: number[];
}

function buildUrl(path: string, query?: ApiRequestOptions<z.ZodType>["query"]): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE_PATH}${normalized}${qs ? `?${qs}` : ""}`;
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/**
 * Typed fetch wrapper for the AURA backend.
 * - Sends cookies (same-origin) for authentication.
 * - Parses the standard error envelope into `ApiError`.
 * - Validates successful responses with the given Zod schema.
 */
export async function apiRequest<TSchema extends z.ZodType>(
  path: string,
  options: ApiRequestOptions<TSchema>,
): Promise<z.infer<TSchema>> {
  const { method = "GET", schema, body, query, signal, acceptStatuses = [] } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ status: 0, code: "network_error", message: NETWORK_ERROR_MESSAGE });
  }

  const requestId = response.headers.get("X-Request-ID");
  const payload = await readJson(response);

  if (!response.ok && !acceptStatuses.includes(response.status)) {
    const envelope = errorResponseSchema.safeParse(payload);
    if (envelope.success) {
      const { code, message, details, request_id } = envelope.data.error;
      throw new ApiError({
        status: response.status,
        code,
        message,
        details,
        requestId: request_id ?? requestId,
        body: payload,
      });
    }
    throw new ApiError({
      status: response.status,
      code: response.status >= 500 ? "service_unavailable" : "error",
      message: GENERIC_ERROR_MESSAGE,
      requestId,
      body: payload,
    });
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError({
      status: response.status,
      code: "invalid_response",
      message: INVALID_RESPONSE_MESSAGE,
      requestId,
      body: payload,
    });
  }
  return parsed.data;
}
