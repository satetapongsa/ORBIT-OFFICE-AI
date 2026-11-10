# AURA OFFICE AI — API Conventions

## Base

- All endpoints live under **`/api/v1`**. Breaking changes require `/api/v2`.
- JSON only (`application/json; charset=utf-8`), except file upload
  (`multipart/form-data`) and file download/export (binary streams).
- OpenAPI docs: `/api/docs` (Swagger UI), `/api/redoc`, schema at
  `/api/openapi.json`. Disabled in production unless `API_DOCS_ENABLED=true`.

## Naming

| Item            | Convention                                         | Example                         |
| --------------- | -------------------------------------------------- | ------------------------------- |
| Paths           | plural nouns, kebab-case                           | `/api/v1/document-versions`     |
| Path params     | UUIDs                                              | `/api/v1/tasks/{task_id}`       |
| JSON fields     | `snake_case`                                       | `due_at`, `department_id`       |
| Enum values     | `UPPER_SNAKE_CASE`                                 | `IN_PROGRESS`                   |
| Actions         | sub-resource verbs only when not CRUD              | `POST /tasks/{id}/status`       |
| Timestamps      | ISO 8601 with timezone, always UTC on output       | `2026-11-10T08:30:00Z`          |
| IDs             | UUID strings                                       |                                 |

## Methods and status codes

| Method   | Use                         | Success          |
| -------- | --------------------------- | ---------------- |
| `GET`    | read (safe, idempotent)     | `200`            |
| `POST`   | create / non-idempotent act | `201` (+ `Location`) or `200`/`202` for actions |
| `PATCH`  | partial update              | `200`            |
| `PUT`    | full replace (rare)         | `200`            |
| `DELETE` | delete / soft delete        | `204`            |

Error codes: `400` malformed, `401` not authenticated, `403` authenticated but
not permitted, `404` not found **or not visible to this user** (do not leak the
existence of records the user cannot see), `409` conflict, `413` payload too
large, `415` unsupported media type, `422` validation failed, `429` rate
limited, `503` dependency unavailable (e.g. AI provider), `500` unexpected.

## Error envelope

Every error response uses this shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "ข้อมูลไม่ถูกต้อง",
    "details": [{ "field": "due_at", "message": "must be in the future" }],
    "request_id": "6f1c0c0e9a7b4f3e"
  }
}
```

- `code`: stable machine-readable string (frontend switches on it).
- `message`: safe, user-facing text (Thai by default for user-facing errors).
- `details`: optional list (field errors).
- `request_id`: matches the `X-Request-ID` response header and backend logs.
- Never include stack traces, SQL, file paths, tokens or provider error bodies.

Standard codes: `bad_request`, `unauthenticated`, `permission_denied`,
`not_found`, `conflict`, `validation_error`, `payload_too_large`,
`unsupported_media_type`, `rate_limited`, `csrf_failed`, `service_unavailable`,
`ai_not_configured`, `ai_provider_error`, `internal_error`.

## Pagination, filtering, sorting

- Query: `?page=1&page_size=20` (`page_size` max 100).
- Response:
  ```json
  { "items": [...], "total": 132, "page": 1, "page_size": 20 }
  ```
- Filters are explicit query params (`?status=TODO&priority=HIGH&department_id=…`);
  free-text search uses `q`.
- Sorting: `?sort=-created_at,title` (`-` = descending); only whitelisted
  fields are accepted.

## Headers

| Header           | Direction | Purpose                                             |
| ---------------- | --------- | --------------------------------------------------- |
| `X-Request-ID`   | both      | correlation id (client may send; server always returns) |
| `X-CSRF-Token`   | request   | required on `POST/PUT/PATCH/DELETE` with cookie auth (Phase 2) |
| `Retry-After`    | response  | with `429` / `503`                                  |

## Authentication (Phase 2)

Browser clients authenticate with HttpOnly cookies set by `POST /api/v1/auth/login`
(`aura_access`, `aura_refresh`) and a readable `aura_csrf` cookie for the
double-submit CSRF check. Details in `SECURITY.md`.

## Health endpoints (Phase 1)

| Endpoint                   | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| `GET /api/v1/health/live`  | liveness — process is up; no dependency checks      |
| `GET /api/v1/health`       | readiness — checks database (+ pgvector), Redis, object storage; reports AI configuration status. `200` when all required components are `ok`, else `503`. |

## Versioning and compatibility

Additive changes (new fields, new endpoints) are allowed within `v1`. Removing or
renaming fields, or changing their meaning, is a breaking change. Frontend
types/Zod schemas must be updated in the same change as backend schemas.
