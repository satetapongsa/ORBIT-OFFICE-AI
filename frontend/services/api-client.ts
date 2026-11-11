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

export const CSRF_COOKIE = "aura_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set<HttpMethod>(["GET"]);
/** Auth endpoints never trigger the automatic refresh-and-retry. */
const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/logout", "/auth/password-reset"];

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length));
  }
  return null;
}

type SessionListener = () => void;
const sessionExpiredListeners = new Set<SessionListener>();

/** Notified when the session can no longer be refreshed (the user must sign in again). */
export function onSessionExpired(listener: SessionListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

let refreshInFlight: Promise<boolean> | null = null;

/** Rotate the refresh token once, even if many requests hit 401 at the same time. */
function refreshSession(): Promise<boolean> {
  // No CSRF cookie means there was never a session in this browser: nothing to refresh.
  if (!readCookie(CSRF_COOKIE)) return Promise.resolve(false);
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE_PATH}/auth/refresh`, {
        method: "POST",
        headers: { Accept: "application/json", [CSRF_HEADER]: readCookie(CSRF_COOKIE) ?? "" },
        credentials: "same-origin",
        cache: "no-store",
      });
      if (response.ok) return true;
      // Another tab rotated the session a moment ago; its new cookies are already ours.
      const payload = await readJson(response);
      const envelope = errorResponseSchema.safeParse(payload);
      return envelope.success && envelope.data.error.code === "session_refresh_conflict";
    } catch {
      return false;
    } finally {
      setTimeout(() => {
        refreshInFlight = null;
      }, 0);
    }
  })();
  return refreshInFlight;
}

async function send(
  path: string,
  method: HttpMethod,
  body: unknown,
  query: ApiRequestOptions<z.ZodType>["query"],
  signal: AbortSignal | undefined,
): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  // FormData sets its own multipart boundary header.
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }
  try {
    return await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ status: 0, code: "network_error", message: NETWORK_ERROR_MESSAGE });
  }
}

async function sendWithRefresh(
  path: string,
  method: HttpMethod,
  body: unknown,
  query: ApiRequestOptions<z.ZodType>["query"],
  signal: AbortSignal | undefined,
): Promise<Response> {
  let response = await send(path, method, body, query, signal);
  const mayRefresh = !NO_REFRESH_PATHS.some((p) => path.startsWith(p));
  if (response.status === 401 && mayRefresh) {
    if (await refreshSession()) {
      response = await send(path, method, body, query, signal);
    }
    if (response.status === 401) sessionExpiredListeners.forEach((listener) => listener());
  }
  return response;
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get("X-Request-ID");
  const payload = await readJson(response);
  const envelope = errorResponseSchema.safeParse(payload);
  if (envelope.success) {
    const { code, message, details, request_id } = envelope.data.error;
    return new ApiError({
      status: response.status,
      code,
      message,
      details,
      requestId: request_id ?? requestId,
      body: payload,
    });
  }
  return new ApiError({
    status: response.status,
    code: response.status >= 500 ? "service_unavailable" : "error",
    message: GENERIC_ERROR_MESSAGE,
    requestId,
    body: payload,
  });
}

/**
 * POST and return the raw streaming response (e.g. server-sent events), with the same CSRF,
 * refresh-and-retry and error-envelope handling as {@link apiRequest}.
 */
export async function apiStream(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await sendWithRefresh(path, "POST", body, undefined, signal);
  if (!response.ok) throw await toApiError(response);
  if (!response.body) {
    throw new ApiError({ status: 0, code: "network_error", message: NETWORK_ERROR_MESSAGE });
  }
  return response;
}

/** Filename from `Content-Disposition` (prefers the RFC 5987 UTF-8 form). */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* fall through */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? fallback;
}

/**
 * Download a file through the API (session cookies, refresh-and-retry, error envelope) and
 * hand it to the browser as a file save.
 */
export async function apiDownload(
  path: string,
  options: { query?: ApiRequestOptions<z.ZodType>["query"]; fallbackName?: string } = {},
): Promise<string> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const response = await sendWithRefresh(
    normalizedPath,
    "GET",
    undefined,
    options.query,
    undefined,
  );
  if (!response.ok) throw await toApiError(response);
  const name = filenameFromDisposition(
    response.headers.get("Content-Disposition"),
    options.fallbackName ?? "document",
  );
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  return name;
}

/**
 * Typed fetch wrapper for the AURA backend.
 * - Sends cookies (same-origin) and the CSRF header on state-changing requests.
 * - On 401, refreshes the session once and retries; notifies listeners if that fails.
 * - Parses the standard error envelope into `ApiError`.
 * - Validates successful responses with the given Zod schema.
 */
export async function apiRequest<TSchema extends z.ZodType>(
  path: string,
  options: ApiRequestOptions<TSchema>,
): Promise<z.infer<TSchema>> {
  const { method = "GET", schema, body, query, signal, acceptStatuses = [] } = options;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  const response = await sendWithRefresh(normalizedPath, method, body, query, signal);
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
