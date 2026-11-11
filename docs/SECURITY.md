# AURA OFFICE AI — Security Principles

Security is enforced in the **backend**. The frontend may hide actions the user
cannot perform, but every API independently authenticates and authorises.

## 1. Authentication (implemented in Phase 2)

| Item               | Implementation                                                         |
| ------------------ | ---------------------------------------------------------------------- |
| Password hashing   | Argon2id (`argon2-cffi`, library defaults ≥ OWASP minimum); rehash on login when parameters change; a dummy hash is verified for unknown e-mails so timing does not reveal accounts |
| Password policy    | ≥ `PASSWORD_MIN_LENGTH` (12) chars, ≤ 256, not a common/low-variety password, must not contain the e-mail local part (`app/services/passwords.py`) |
| Access token       | JWT HS256 (`JWT_SECRET_KEY`), 15 min, claims `iss`, `sub`, `sid` (session family), `iat`, `exp`, `jti`, `type=access`. Permissions are **not** embedded — they are loaded per request, so revocation is immediate |
| Per-request checks | token valid → user exists, active, not deleted → token issued after the last password change → session family not revoked/expired → permissions loaded fresh |
| Refresh token      | 256-bit opaque value, stored only as SHA-256 in `user_sessions`; idle lifetime 7 days, absolute cap 30 days per login |
| Rotation           | every refresh issues a new token and marks the old row rotated. A rotated token re-presented within `REFRESH_REUSE_GRACE_SECONDS` (10 s, parallel tabs) is rejected without revoking; later re-use revokes the whole family and is audit-logged (`auth.refresh_reuse_detected`) |
| Cookies            | `aura_access` (path `/api`) and `aura_refresh` (path `/api/v1/auth`) are `HttpOnly`; `aura_csrf` (path `/`) is readable; all `SameSite=Lax`, `Secure` except in development/test (`COOKIE_SECURE` overrides). Nothing is stored in `localStorage` |
| Bearer tokens      | `Authorization: Bearer <access token>` is accepted for API clients; such requests are not subject to CSRF (no ambient credentials) |
| CSRF               | double-submit: `X-CSRF-Token` must equal the `aura_csrf` cookie on every cookie-authenticated `POST/PUT/PATCH/DELETE`, including refresh and logout. Login and password-reset endpoints carry no session and are exempt |
| Logout             | revokes the session family (all rotations), clears cookies, audit-logged; the still-unexpired access token stops working immediately |
| Password change    | requires the current password; revokes every other session and issues fresh tokens for the current one |
| Password reset     | single-use token (SHA-256 in DB, 30 min), older tokens invalidated, all sessions revoked on success; the request endpoint always answers 202 with the same message (no enumeration). Delivery: no mail adapter yet — in `development` the link is logged, elsewhere it is **not** logged and a warning says delivery is not configured |
| Brute force        | Redis fixed-window limits: 10 attempts / 15 min per e-mail and 50 per IP; 429 with `Retry-After`; generic error `อีเมลหรือรหัสผ่านไม่ถูกต้อง` for wrong password, unknown e-mail and inactive accounts. The limiter **fails open** if Redis is down (logged; readiness reports Redis) — reviewed in Phase 9 |

## 2. Authorisation (RBAC)

- Permission codes follow `domain:action`. The catalogue lives in code
  (`app/core/permissions.py`) and is synced to the `permissions` table.
- Roles are database rows mapping to permission sets; new roles need no code.
- Route guard: `Depends(require_permissions("tasks:assign"))`.
- Record guard: services check ownership/scope (e.g. a manager may only manage
  tasks of their own department unless they hold `tasks:manage_all`).
- Unknown/absent permission ⇒ deny. Deny by default everywhere.
- Aggregates follow the same rules as the detailed data (Phase 3): `GET /dashboard/summary`
  returns a section only when the caller holds the permission that guards the equivalent
  detail API (`documents:read` + the ACL predicate, `users:read`, `audit:read`); otherwise
  the section is `null`. Activity feeds expose action, time, actor name and entity type only
  — never IP addresses, user agents or audit metadata.
- Notifications are owner-only: every query filters by the caller's id, other users'
  notifications answer `404` (administrators included). Links are relative in-app paths,
  enforced by a database `CHECK`, the service and the client.

### Initial permission catalogue

| Domain            | Permissions                                                                 |
| ----------------- | --------------------------------------------------------------------------- |
| Users             | `users:read`, `users:create`, `users:update`, `users:deactivate`            |
| Departments       | `departments:read`, `departments:manage`                                    |
| Roles             | `roles:read`, `roles:manage`, `roles:assign`                                |
| Documents         | `documents:read`, `documents:upload`, `documents:manage`, `documents:delete` |
| Document access   | `documents:manage_access`                                                   |
| Tasks             | `tasks:read_own`, `tasks:create`, `tasks:read_department`, `tasks:assign`, `tasks:manage_department`, `tasks:manage_all` |
| Employees         | `employees:read_directory`, `employees:read_sensitive`, `employees:manage`  |
| Helpdesk          | `tickets:create`, `tickets:read_own`, `tickets:read_all`, `tickets:assign`, `tickets:manage`, `tickets:comment_internal` |
| Analytics         | `analytics:read_own`, `analytics:read_department`, `analytics:read_all`, `reports:export` |
| AI                | `ai:chat`, `ai:use_tools`                                                   |
| System            | `system:configure`, `system:configure_ai`                                   |
| Audit             | `audit:read`                                                                |

### Default system roles (`app/core/permissions.py`, synced by `python -m app.cli sync-rbac`)

| Role | Permissions |
| --- | --- |
| `EMPLOYEE` | `departments:read`, `documents:read`, `documents:upload`, `tasks:read_own`, `tasks:create`, `employees:read_directory`, `tickets:create`, `tickets:read_own`, `analytics:read_own`, `ai:chat`, `ai:use_tools` |
| `MANAGER` | EMPLOYEE + `users:read`, `tasks:read_department`, `tasks:assign`, `tasks:manage_department`, `analytics:read_department`, `reports:export` |
| `HR` | EMPLOYEE + `users:read`, `users:create`, `users:update`, `departments:manage`, `employees:read_sensitive`, `employees:manage` |
| `IT_SUPPORT` | EMPLOYEE + `users:read`, `tickets:read_all`, `tickets:assign`, `tickets:manage`, `tickets:comment_internal` |
| `ADMIN` | every permission; its permission set is locked (cannot be edited through the API) |

### Privilege-escalation guards (`app/services/rbac.py`, `app/services/users.py`)

- Nobody can grant **or revoke** a permission they do not hold: creating/editing a role and
  assigning/removing a role to/from a user both require the actor to hold every affected permission.
- Creating a user with any role other than the default `EMPLOYEE` requires `roles:assign`.
- The last active `ADMIN` cannot be demoted or deactivated; users cannot deactivate themselves.
- System roles cannot be deleted; custom roles cannot be deleted while assigned.
- Deactivating a user revokes all of their sessions immediately.

## 3. Document ACL

A user may access a document if **any** of the following is true (and the
document is not soft-deleted):

1. user holds `documents:manage` (administrative override, audit-logged), or
2. user is the document owner, or
3. `visibility = COMPANY`, or
4. `visibility = DEPARTMENT` and the user is in `documents.department_id`, or
5. a `document_acl` row grants the user directly, via their department, or via
   one of their roles, with sufficient `access_level`.

This rule is implemented **once** as a SQLAlchemy predicate
(`repositories/document_access.py`) and reused by: listing, preview, download,
search, RAG retrieval, summarisation and report generation. Tests must cover
each call site (Phase 4/7/9). Phase 2 tests (`tests/api/test_document_access.py`) cover every
rule above against PostgreSQL, including VIEW vs EDIT levels and soft deletion.

### Capabilities on top of the access level (Phase 4, `app/services/documents/service.py`)
| operation | requires |
| --- | --- |
| list, detail, text preview, download | VIEW |
| upload a new document | `documents:upload` (department: own, unless `documents:manage`) |
| edit metadata, archive | EDIT |
| change visibility / department | MANAGE |
| upload a version | EDIT + `documents:upload` |
| reprocess a version | EDIT |
| delete (soft) | MANAGE + `documents:delete` (owners archive instead) |
| read/replace ACL | MANAGE, or VIEW + `documents:manage_access` |
| history | MANAGE, or VIEW + `audit:read` |

Unknown and inaccessible documents both return `404`. The effective level is computed with
the same predicate (`effective_access_level`), so it can never disagree with listings.
Granting a USER access (or raising it) sends that user a `DOCUMENT` notification.

## 3a. Task visibility and capabilities (Phase 5, implemented)

A user sees a live task when **any** of these holds (one SQL predicate,
`app/repositories/task_access.visible_tasks_condition`, used by every task query and the
dashboard): they hold `tasks:manage_all`; they hold `tasks:read_own` and created the task or
are assigned to it; they hold `tasks:read_department` or `tasks:manage_department` and the
task belongs to their department. A *manager* of a task holds `tasks:manage_all`, or
`tasks:manage_department` for a task of their own department.

| operation | requires |
| --- | --- |
| see, comment, download attachments | visible |
| create | `tasks:create`; another department needs `tasks:manage_all` |
| assign someone other than yourself | `tasks:assign` + (creator or manager); assignees must be active and in the task's department unless `tasks:manage_all` |
| edit, cancel, delete (soft) | creator or manager |
| move to another department | `tasks:manage_all` |
| change status (not cancel), attach files | creator, assignee or manager |
| edit a comment / delete a comment | author / author or manager |
| remove an attachment | uploader, creator or manager |

Unknown and invisible tasks both answer `404`. The assignee picker
(`GET /tasks/assignable-users`) only lists people the caller may assign. Comments and
descriptions are plain text in the UI (never HTML).

## 3b. Employee data (Phase 5, implemented)

- Directory (`employees:read_directory`): active people only, work contact fields (name,
  title, department, work e-mail/phone). Suspended accounts need `users:read`.
- Account fields (status, roles, last sign-in) are added only for `users:read`; account
  changes go through the existing `/users` API and its guards (§2).
- Sensitive HR data lives in `employee_hr_profiles` and has its own endpoint: readable by the
  employee themself or with `employees:read_sensitive`; every read by someone else writes
  `employee.hr_profile_viewed`. Writing needs `employees:manage` + `employees:read_sensitive`;
  `employee.hr_profile_updated` stores changed field names, never values. Only the last four
  digits of the national ID are accepted (DB `CHECK`). The UI loads someone else's record only
  after an explicit "แสดงข้อมูลบุคคล" click.

## 4. File upload security (Phase 4, implemented)

- Allow-list of extensions **and** content sniffing (PDF magic, OOXML archive layout —
  `word/document.xml` / `xl/workbook.xml` — or decodable text); the two must agree, so a
  renamed file is rejected (`415`). Client `Content-Type` is ignored.
- Max size `UPLOAD_MAX_BYTES` (default 25 MB) at four layers: Nginx `client_max_body_size 30m`,
  Next.js proxy `proxyClientMaxBodySize 30mb`, an ASGI middleware that rejects a too-large
  `Content-Length` before the body is read (`411` without a length), and the service which
  measures the real bytes while hashing.
- Zip-bomb / archive guard for DOCX/XLSX (entry count, total uncompressed size, per-entry
  ratio, encrypted entries, `..`/absolute paths) — at upload and again in the worker.
- Storage keys are server-generated (`documents/{document_id}/{version_id}`,
  `tasks/{task_id}/{attachment_id}` — task attachments share this pipeline);
  user filenames are sanitised and stored only as metadata.
- Downloads stream through the backend after an ACL check (or short-lived
  presigned URLs generated only after the check). Bucket is private.
- `Content-Disposition: attachment` with RFC 5987 filename encoding;
  `X-Content-Type-Options: nosniff`.
- Parsers run in the worker with timeouts and size limits (zip-bomb guard for
  DOCX/XLSX): 180 s soft limit per file, 2,000 PDF pages, 2,000,000 XLSX cells, 2,000,000
  output characters; openpyxl uses `defusedxml`. Failures become `FAILED` with a Thai reason
  and notify the uploader; editors can reprocess.
- Extracted text is untrusted: the UI renders it as plain text (never HTML), and Phase 7 will
  pass it to the model only inside delimited data sections after the ACL filter.
- Storage writes happen before the DB commit; a failed commit deletes the object again.
  Deleted documents are soft-deleted; their objects stay in the private bucket (purge job:
  Phase 9). No antivirus scanning yet (Phase 9).

## 5. AI and RAG security

- AI is called only from the backend; keys come from environment/secret store.
- **Permission filtering happens in SQL before retrieval results exist** — the
  vector query joins the ACL predicate from §3. Retrieving everything and asking
  the model to ignore unauthorised content is forbidden.
- Document text is untrusted: it is placed in clearly delimited data sections,
  the system prompt states that instructions inside documents must be ignored,
  and tool calls proposed after reading documents still go through permission
  checks and user confirmation.
- Tool calling uses a fixed whitelist. No arbitrary SQL, shell, filesystem or
  network access. Each tool validates the authenticated user and arguments
  (Pydantic) and never trusts model-supplied IDs without authorisation checks.
- Mutating tools create an `ai_action_requests` row; nothing executes until the
  user confirms in the UI. The AI cannot act as another employee.
- Provider errors are mapped to `ai_provider_error` without leaking provider
  response bodies or keys.

### Implemented in Phase 6
- Chats, messages and actions are owner-only (`404` for anyone else, administrators
  included). `ai:chat` is required for every `/ai` endpoint; tools are offered only with
  `ai:use_tools` **and** each tool's own permission, and an unoffered tool name is answered
  with an error.
- Tools (`app/services/ai/tools.py`): `get_my_tasks`, `get_task_details`, `find_colleagues`
  (read-only) and `create_task`, `update_task_status` (mutating). Arguments are validated with
  strict Pydantic models (`extra="forbid"`); tools call the same services and visibility
  predicates as the HTTP API **as the signed-in user**, so a hidden task is "not found" to the
  model as well.
- Mutating tools only create a `PENDING` `ai_action_requests` row (TTL
  `AI_ACTION_TTL_MINUTES`); the model is told nothing has changed. Confirmation re-checks the
  permissions and runs the service; the row is marked `EXECUTED` in the same transaction as
  the change, so it can never run twice. Events: `ai.action_confirmed`, `ai.action_rejected`
  (plus the normal `task.*` events with the user as actor).
- The system prompt states that tool results and stored text are data, not instructions; the
  UI renders model output as plain text (only standalone in-app `/tasks|/documents|/employees/<uuid>`
  paths become links). Tool results are never sent to the browser.
- Limits: 4,000 characters per message, `AI_CHAT_RATE_LIMIT_MESSAGES` per
  `AI_CHAT_RATE_LIMIT_WINDOW_SECONDS` per user, `AI_CHAT_MAX_TOOL_STEPS` tool rounds per
  message, 20,000 characters per tool result, last `AI_CHAT_HISTORY_MESSAGES` messages sent.
- Provider keys are read from settings only, never logged; provider errors log status and
  request id, never bodies.

## 6. Transport and HTTP hardening

- HTTPS terminated at Nginx in production (HSTS, TLS 1.2+).
- Security headers: `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive
  `Content-Security-Policy` (Phase 9 tuning).
- CORS: the main app is same-origin and needs no CORS. `CORS_ORIGINS` is an
  explicit allow-list (empty by default); wildcard with credentials is never used.
- Rate limiting (Redis): login, AI chat, upload, export endpoints (Phase 2/6/9).

## 7. Secrets

- No secrets in source code or images. `.env` is git-ignored; `.env.example`
  contains only placeholders and local-dev defaults.
- The backend refuses to start in `production` with default/weak
  `JWT_SECRET_KEY` or default storage credentials.
- Logs never include passwords, tokens, API keys, cookies or document content.

## 8. Audit logging

Implemented actions (`app/services/audit.py`): `auth.login`, `auth.login_failed` (reason +
hashed e-mail, never the password), `auth.login_rate_limited`, `auth.logout`,
`auth.refresh_reuse_detected`, `auth.password_changed`, `auth.password_reset_requested`,
`auth.password_reset_completed`, `user.created|updated|deactivated|activated|roles_changed`,
`role.created|updated|deleted|permissions_changed`, `department.created|updated|deleted`.
Entries are written in the same transaction as the change. A database trigger rejects
`UPDATE`/`DELETE` on `audit_logs`. Read access requires `audit:read`.

Document events (Phase 4): `document.uploaded`, `document.version_uploaded`,
`document.updated`, `document.deleted`, `document.downloaded` (every download),
`document.acl_changed`, `document.reprocess_requested`.

Task events (Phase 5): `task.created`, `task.updated`, `task.status_changed`,
`task.assignees_changed`, `task.deleted`, `task.attachment_added`, `task.attachment_removed`,
`task.attachment_downloaded`. Employee events: `employee.hr_profile_viewed`,
`employee.hr_profile_updated` (field names only).

AI events (Phase 6): `ai.action_confirmed` (including failed and no-op runs),
`ai.action_rejected`.

Planned events (later phases): ticket status changes, system configuration changes.
Every entry stores actor, IP, user agent and request ID.

## 9. Reporting a vulnerability

Report internally to the system administrator. Do not open public issues for
security problems.
