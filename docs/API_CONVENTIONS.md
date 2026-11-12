# ORBIT OFFICE AI — API Conventions

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

## Authentication (implemented in Phase 2)

Browser clients authenticate with HttpOnly cookies set by `POST /api/v1/auth/login`
(`orbit_access`, `orbit_refresh`) plus a readable `orbit_csrf` cookie whose value must be
echoed in `X-CSRF-Token` on every cookie-authenticated `POST/PUT/PATCH/DELETE`
(including refresh and logout). API clients may send `Authorization: Bearer <access token>`
instead (no CSRF needed). Details in `SECURITY.md`.

Extra error codes: `csrf_failed` (403), `session_refresh_conflict` (401 — another tab
rotated the session a moment ago; retry), `invalid_reset_token` (400).

## Endpoint index (v1)

| Method & path | Permission | Notes |
| --- | --- | --- |
| `POST /auth/login` | — | sets session cookies; returns `{user, permissions, session}`; rate limited |
| `POST /auth/refresh` | refresh cookie + CSRF | rotates tokens; `401` if there is no session |
| `POST /auth/logout` | CSRF (when cookies are present) | revokes the session family; `204` |
| `GET /auth/me` | signed in | current user and permission codes |
| `POST /auth/change-password` | signed in | revokes other sessions |
| `POST /auth/password-reset/request` | — | always `202` with the same message |
| `POST /auth/password-reset/confirm` | — | single-use token |
| `GET /users` | `users:read` | `page`, `page_size`, `q`, `department_id`, `is_active`, `role` |
| `POST /users` | `users:create` (+ `roles:assign` for non-default roles) | `201` |
| `GET /users/{id}` | `users:read` | |
| `PATCH /users/{id}` | `users:update` | |
| `POST /users/{id}/deactivate`, `POST /users/{id}/activate` | `users:deactivate` | deactivation revokes sessions |
| `PUT /users/{id}/roles` | `roles:assign` | escalation and last-admin guards |
| `GET /departments`, `GET /departments/{id}` | `departments:read` | includes `member_count` |
| `POST /departments`, `PATCH`/`DELETE /departments/{id}` | `departments:manage` | delete is a soft delete; `409` while members remain |
| `GET /permissions` | `roles:read` | catalogue with Thai descriptions |
| `GET /roles`, `GET /roles/{id}` | `roles:read` | |
| `POST /roles`, `PATCH /roles/{id}` | `roles:manage` | |
| `PUT /roles/{id}/permissions` | `roles:manage` | cannot grant what you do not hold; `ADMIN` is locked |
| `DELETE /roles/{id}` | `roles:manage` | custom, unassigned roles only |
| `GET /audit-logs` | `audit:read` | filters `action`, `actor_id`, `entity_type`, `entity_id`, `occurred_from`, `occurred_to` |
| `GET /dashboard/summary` | signed in | personal sections always; `documents` needs `documents:read` (ACL-counted), `tasks` needs `tasks:read_own` (my open assigned tasks: counts + 5 earliest due), `organization` needs `users:read`, `security` needs `audit:read` — otherwise `null`. Days are grouped in `APP_TIMEZONE` (Phase 3) |
| `GET /documents` | VIEW (ACL predicate) | `q` (title/description, wildcards escaped), `category`, `visibility`, `status`, `processing_status`, `department_id`, `mine`, `sort` = `updated`/`created`/`title`, `page`, `page_size` |
| `GET /documents/search` | `documents:read` (ACL in SQL) | `q` (1–500), `limit` ≤ 50 (default 10); best passage per document: `{query, mode: hybrid|keyword, degraded, results[{document_id, title, category, version_number, page, snippet, score}]}` — only current versions of documents the caller may read (Phase 7) |
| `POST /documents` | `documents:upload` | multipart: `file` + `title`, `description`, `category`, `visibility`, `department_id` (own department unless `documents:manage`); `201` detail; `413` too large, `415` unsupported/mismatched type, `422` empty/unsafe file, `503` storage down |
| `GET /documents/{id}` | VIEW | detail + `access_level`, `capabilities`, `versions` (each with `index_status` PENDING/INDEXING/READY/FAILED/SKIPPED, `index_error`, `chunk_count`, `indexed_at`); `404` for unknown **and** inaccessible |
| `PATCH /documents/{id}` | EDIT (visibility/department: MANAGE) | title, description, category, status (`ARCHIVED` = owner's "remove") |
| `DELETE /documents/{id}` | MANAGE + `documents:delete` | soft delete; `204` |
| `POST /documents/{id}/versions` | EDIT + `documents:upload` | multipart `file`; becomes current |
| `POST /documents/{id}/versions/{vid}/reprocess` | EDIT | `202`; `409` if READY/PROCESSING |
| `GET /documents/{id}/download` | VIEW | `?version_id=`; streams; `Content-Disposition: attachment` (RFC 5987), `nosniff`, `no-store`; audited |
| `GET /documents/{id}/text` | VIEW | extracted text preview (first 50,000 chars, `truncated`); `409` until READY |
| `GET /documents/{id}/acl`, `PUT /documents/{id}/acl` | MANAGE, or VIEW + `documents:manage_access` | replace explicit grants (USER/DEPARTMENT/ROLE × VIEW/EDIT/MANAGE); `422` duplicates/owner/unknown principal |
| `GET /documents/{id}/history` | MANAGE, or VIEW + `audit:read` | last 100 audit events of the document |
| `GET /directory/users` | `employees:read_directory` | `q`, `limit` ≤ 50; id, display name, job title, department only |
| `GET /tasks` | any of `tasks:read_own`/`read_department`/`manage_department`/`manage_all` | visibility predicate (ADR-033); `scope` = `all`/`assigned`/`created`/`department` (department needs a department permission), `q`, `status`, `open_only`, `priority`, `assignee_id`, `overdue`, `sort` = `due`/`priority`/`updated`/`created`, `page`, `page_size` |
| `POST /tasks` | `tasks:create` | `title`, `description`, `priority`, `due_at` (timezone required), `assignee_ids` (empty = creator; others need `tasks:assign`; same department unless `tasks:manage_all`), `department_id` (own unless `manage_all`); `201` detail |
| `GET /tasks/assignable-users` | task reader | `q`, `limit` ≤ 50; everyone (`manage_all`), own department (`tasks:assign`), otherwise only yourself |
| `GET /tasks/{id}` | visible | detail + `capabilities`; `404` for unknown **and** invisible |
| `PATCH /tasks/{id}` | creator or manager | title, description, priority, `due_at` (null clears); `department_id` needs `tasks:manage_all` |
| `POST /tasks/{id}/status` | creator, assignee or manager (`CANCELLED`: creator or manager) | sets/clears `completed_at`; notifies creator + assignees |
| `PUT /tasks/{id}/assignees` | manager, or creator with `tasks:assign` | replace; added people are notified |
| `DELETE /tasks/{id}` | creator or manager | soft delete; `204` |
| `GET`/`POST /tasks/{id}/comments`, `PATCH`/`DELETE …/comments/{cid}` | visible (edit: author; delete: author or manager) | body 1–5000 chars; returns the thread; new comments notify creator + assignees |
| `GET`/`POST /tasks/{id}/attachments`, `GET …/{aid}/download`, `DELETE …/{aid}` | visible (upload: creator/assignee/manager; delete: uploader/creator/manager) | same upload pipeline as documents (ADR-029), max 20 per task, downloads audited |
| `GET /tasks/{id}/history` | visible | task timeline (`task_events`, newest first, ≤ 200) |
| `GET /employees` | `employees:read_directory` | active people; `q` (name/title/e-mail/code), `department_id`, `include_inactive` (needs `users:read`), `page`, `page_size` (default 24) — work contact fields only |
| `GET /employees/{id}` | `employees:read_directory` | directory fields + department manager + `account` (with `users:read`, else `null`) + `capabilities`; inactive people `404` without `users:read` |
| `GET /employees/{id}/hr` | yourself, or `employees:read_sensitive` | HR record (`exists: false` when empty); reads by others are audited |
| `PUT /employees/{id}/hr` | `employees:manage` + `employees:read_sensitive` | full replacement; national ID last 4 digits only; audit keeps field names, never values |
| `GET /ai/status` | `ai:chat` | `{enabled, provider, model, tools[{name, label, requires_confirmation}], max_message_chars}` — tools are those the caller may use (`ai:use_tools` + each tool's permission) |
| `GET /ai/sessions`, `POST /ai/sessions` | `ai:chat` (own only) | newest first; `page`, `page_size` ≤ 100 |
| `GET`/`PATCH`/`DELETE /ai/sessions/{id}` | `ai:chat` (own only) | detail = messages (tool messages carry a Thai label and `tool_ok`, never raw tool data) + actions; delete is soft; others' sessions `404` |
| `POST /ai/sessions/{id}/messages` | `ai:chat` (+ `ai:use_tools` for tools) | body `{content}` (1–4000 chars); answer is `text/event-stream` with events `start`, `delta`, `tool`, `action`, `done` (with `citations` [{n, document_id, version_id, chunk_id, title, page}]), `error`; stored assistant messages return `citations` [{n, document_id, title, page}]; `503 ai_not_configured` without a provider; `429` above `AI_CHAT_RATE_LIMIT_MESSAGES` per window |
| `POST /ai/actions/{id}/confirm` | `ai:chat` + `ai:use_tools` + the tool's permission (own only) | re-validates and runs the proposed change as the user; `EXECUTED` / `FAILED`; `409` if already decided or expired |
| `POST /ai/actions/{id}/reject` | `ai:chat` (own only) | `REJECTED`; nothing changes |
| `GET /notifications` | signed in (own only) | `page`, `page_size` (≤100, default 20), `unread_only`; response adds `unread_count` |
| `GET /notifications/unread-count` | signed in (own only) | `{unread_count}` |
| `POST /notifications/{id}/read` | signed in + CSRF | idempotent; `404` for someone else's notification |
| `POST /notifications/read-all` | signed in + CSRF | `{updated, unread_count}` |
| `GET /health/live`, `GET /health` | — | see below |

## Health endpoints (Phase 1)

| Endpoint                   | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| `GET /api/v1/health/live`  | liveness — process is up; no dependency checks      |
| `GET /api/v1/health`       | readiness — checks database (+ pgvector), Redis, object storage; reports AI configuration status. `200` when all required components are `ok`, else `503`. |

## Versioning and compatibility

Additive changes (new fields, new endpoints) are allowed within `v1`. Removing or
renaming fields, or changing their meaning, is a breaking change. Frontend
types/Zod schemas must be updated in the same change as backend schemas.
