# AURA OFFICE AI — Security Principles

Security is enforced in the **backend**. The frontend may hide actions the user
cannot perform, but every API independently authenticates and authorises.

## 1. Authentication (Phase 2)

| Item               | Design                                                                 |
| ------------------ | ---------------------------------------------------------------------- |
| Password hashing   | Argon2id (`argon2-cffi`), parameters from library defaults (≥ OWASP minimum), rehash on login when parameters change |
| Access token       | JWT (HS256, secret `JWT_SECRET_KEY`), lifetime 15 min, claims `sub`, `sid`, `iat`, `exp`, `jti`, `type=access`. Permissions are **not** embedded — they are loaded per request so revocations apply immediately |
| Refresh token      | 256-bit opaque random value, stored only as SHA-256 hash in `user_sessions`, lifetime 7 days (sliding up to an absolute 30-day cap) |
| Rotation           | each refresh issues a new refresh token and marks the old one rotated; presenting a rotated token revokes the whole session family (theft detection) |
| Cookie storage     | `aura_access` (path `/api`), `aura_refresh` (path `/api/v1/auth`), both `HttpOnly`, `Secure` (non-dev), `SameSite=Lax`. Nothing long-lived in `localStorage` |
| CSRF               | double-submit: readable `aura_csrf` cookie + `X-CSRF-Token` header must match on every unsafe method; plus `SameSite=Lax` and same-origin deployment |
| Logout             | revokes the session family, clears cookies, audit-logged              |
| Session expiry     | access 15 min; refresh 7 days idle; password change / deactivation revokes all sessions |
| Password reset     | single-use random token (hashed in DB, 30 min expiry), delivered by an email adapter (dev: logged to console only in `development`) |
| Brute force        | per-account and per-IP login rate limits in Redis; generic error message (`อีเมลหรือรหัสผ่านไม่ถูกต้อง`) to avoid account enumeration |

## 2. Authorisation (RBAC)

- Permission codes follow `domain:action`. The catalogue lives in code
  (`app/core/permissions.py`) and is synced to the `permissions` table.
- Roles are database rows mapping to permission sets; new roles need no code.
- Route guard: `Depends(require_permissions("tasks:assign"))`.
- Record guard: services check ownership/scope (e.g. a manager may only manage
  tasks of their own department unless they hold `tasks:manage_all`).
- Unknown/absent permission ⇒ deny. Deny by default everywhere.

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

Default role mapping is defined in the Phase 2 seed and documented in
`DECISIONS.md` when implemented.

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
each call site (Phase 4/7/9).

## 4. File upload security (Phase 4)

- Allow-list of extensions **and** sniffed MIME types (PDF, DOCX, XLSX, TXT).
- Max size `UPLOAD_MAX_BYTES` (default 25 MB), enforced while streaming.
- Storage keys are server-generated (`documents/{document_id}/{version_id}`);
  user filenames are sanitised and stored only as metadata.
- Downloads stream through the backend after an ACL check (or short-lived
  presigned URLs generated only after the check). Bucket is private.
- `Content-Disposition: attachment` with RFC 5987 filename encoding;
  `X-Content-Type-Options: nosniff`.
- Parsers run in the worker with timeouts and size limits (zip-bomb guard for
  DOCX/XLSX).

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

Events (Phase 2 onward): login success/failure, logout, refresh-token reuse,
user create/update/deactivate, role and permission changes, document upload /
download / delete / ACL change, task updates, ticket status changes, AI action
confirmations, system configuration changes. Stored in `audit_logs`
(append-only) with actor, IP, user agent and request ID.

## 9. Reporting a vulnerability

Report internally to the system administrator. Do not open public issues for
security problems.
