# ORBIT OFFICE AI — PROJECT STATUS

**Current Phase:** Phase 9 — Security, Testing & Deployment — ✅ **COMPLETE** (verified 2026-11-12). All phases 0–9 are complete; next: go-live on a server.
**Last Updated:** 2026-11-12

## Completed

### Phase 0 — Project initialization & architecture
- Workspace inspected (was empty); git repository initialised (`main`).
- Documentation: `PROJECT_OVERVIEW`, `ARCHITECTURE`, `DATABASE_DESIGN`, `API_CONVENTIONS`,
  `SECURITY`, `DEVELOPMENT_PHASES`, `PROJECT_STATUS`, `DECISIONS` (ADR-001…022), `RUNBOOK`,
  root `README.md`, session instructions file.

### Phase 1 — Foundation
- **Backend** (`backend/`): FastAPI app factory; `pydantic-settings` config with production
  safety checks (rejects default JWT/storage secrets, wildcard CORS, `debug` in prod);
  structlog JSON/console logging with secret redaction; request-ID middleware + security headers;
  global error envelope (Thai user-facing messages, no stack traces); async + sync SQLAlchemy
  engines (psycopg 3); Redis client; S3/MinIO client with dev bucket auto-create (bounded so it
  never blocks startup); Celery app with `default`/`documents` queues and `system.ping` task;
  ORM base with naming convention, UUID PK, timestamp and soft-delete mixins.
- **Alembic**: configured from app settings; migration `0001` enables `vector` and `pg_trgm`.
- **Health API**: `GET /api/v1/health/live` (liveness), `GET /api/v1/health` (readiness: DB +
  pgvector, Redis, object storage in parallel with timeout; AI chat/embedding configuration
  reported as optional without contacting providers; 503 when a required component fails).
- **AI configuration interface**: `AI_CHAT_*` / `AI_EMBEDDING_*` settings, providers
  `disabled | openai_compatible | anthropic` with validation (no provider calls yet).
- **Frontend** (`frontend/`): Next.js 16 + shadcn/ui (Radix); Thai UI with IBM Plex Sans Thai;
  application shell (desktop sidebar, mobile drawer, header with live system-status indicator,
  skip link); navigation config with required permission + delivery phase per module
  (unbuilt modules are shown disabled with "เร็วๆ นี้", not as links); typed API client with
  error-envelope parsing and Zod response validation; TanStack Query setup; System Status page
  showing real readiness data with loading skeleton, error state with retry, toast feedback;
  reusable `PageHeader`, `ErrorState`, `EmptyState`; Thai 404 page.
- **Infrastructure**: `docker-compose.yml` (postgres/pgvector 17, redis 7.4, minio, migrate,
  backend, worker, frontend, optional nginx profile), backend & frontend multi-stage Dockerfiles
  (dev + non-root prod), Nginx reverse-proxy config, `.env.example`, `.gitignore`,
  `.dockerignore`, `.editorconfig`, `.gitattributes`.
- **Scripts**: `scripts/check.sh` (all static checks + tests), `scripts/smoke-test.sh` (running stack).
- **Verification fixes (2026-11-11)**: object storage image switched to digest-pinned
  `pgsty/minio` (upstream `minio/minio` no longer published, ADR-013); selector event-loop
  factory + startup warning for native Windows runs (async psycopg, ADR-014); host defaults use
  `127.0.0.1` instead of `localhost` (ADR-015); Nginx de-duplicates security headers;
  integration tests extended (Redis round trip, S3 put/get/delete, Celery ping).

### Phase 2 — Authentication & Authorization
- **Data model** (migration `0002`): `departments`, `users`, `roles`, `permissions`,
  `user_roles`, `role_permissions`, `user_sessions`, `password_reset_tokens`, `audit_logs`
  (append-only via DB trigger), and the document ACL foundation (`documents` core + `document_acl`).
- **Security core**: Argon2id hashing with rehash-on-login, password policy, HS256 access JWT
  (15 min, `sid` = session family), opaque hashed refresh tokens with rotation, reuse detection
  (family revocation) and a 10 s parallel-tab grace window, HttpOnly/SameSite cookies,
  double-submit CSRF, Bearer support for API clients, Redis login rate limiting (per e-mail/IP).
- **RBAC**: 38-permission catalogue in code (`app/core/permissions.py`), 5 system roles,
  `python -m app.cli sync-rbac` (run by the Compose `migrate` service), custom roles,
  `require_permissions(...)` guards, permissions re-read every request (instant revocation),
  escalation guards (grant only what you hold), locked ADMIN role, last-admin protection.
- **APIs**: `/auth/*` (login, refresh, logout, me, change-password, password reset),
  `/users`, `/departments`, `/roles`, `/permissions`, `/audit-logs` — see `API_CONVENTIONS.md`.
- **Document ACL**: single SQL predicate `accessible_documents_condition` /
  `can_access_document` covering owner, COMPANY/DEPARTMENT visibility, user/department/role
  grants, VIEW/EDIT/MANAGE levels, `documents:manage` override, soft deletion.
- **Audit log**: 20 action types (auth, users, roles, departments), written in the same
  transaction; passwords/tokens never stored; `GET /audit-logs` with filters.
- **Dev seed**: `python -m app.cli seed-dev` (development only, idempotent): 5 departments and
  one account per role (`*@orbit.example.com`, password `SEED_DEV_PASSWORD`).
- **Frontend**: login, forgot-password, reset-password pages; account page with change-password;
  `AuthGate` redirecting to `/login?next=…` (open-redirect safe); API client with CSRF header and
  single-flight refresh-and-retry; user menu with logout; sidebar filtered by permissions;
  Thai validation messages (React Hook Form + Zod).
- **Fixes found while verifying**: Next.js dev server needed `allowedDevOrigins: ["127.0.0.1"]`
  (app never hydrated otherwise); `instant = false` on the client-gated `(app)` layout;
  `.local` e-mail domains rejected by the validator → `example.com` (ADR-022); refresh with no
  session now answers 401 instead of a CSRF 403, and the client skips that call.

### Phase 3 — Dashboard & Application UI
- **Notifications** (migration `0003`, ADR-023): `notifications` table (owner-only, relative
  links enforced by a DB `CHECK`); producers in the same transaction as the event — welcome
  (account created / dev seed), password changed, password reset, refresh-token reuse
  detected, roles changed (role names), account updated by someone else (field names),
  account re-activated. API: `GET /notifications` (+`unread_only`, `unread_count`),
  `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`.
- **Dashboard API** (ADR-024): `GET /dashboard/summary` — account (department, roles,
  previous sign-in, password changed, active sessions), notifications (unread + latest 5),
  my activity (14-day sign-ins, latest events by me or on my account); `documents`
  (`documents:read`, counted through `accessible_documents_condition`), `organization`
  (`users:read`: active/inactive users, departments, active headcount per department),
  `security` (`audit:read`: sign-ins / failures / rate limits per day, latest audit events).
  Sections without permission are `null`; activity items never include IP, user agent or metadata.
- **Business time zone** `APP_TIMEZONE` (default `Asia/Bangkok`, ADR-025) + `tzdata` dependency.
- **Frontend**: `/dashboard` (greeting, stat cards, "my sign-ins" chart, account & security
  card, notification preview, account activity; organisation and system-security sections
  only when returned), loading skeleton, error state with retry and request id, empty states;
  accessible HTML/CSS column chart with tooltip, legend, table view and a CVD-checked palette
  (ADR-026); header notification bell (unread badge polled every 60 s, latest 5, mark all
  read); `/notifications` page (all/unread filter, mark one/all read, pagination, empty
  state); `/` → `/dashboard`, system status moved to `/system-status`, login lands on the
  dashboard (ADR-027); 2-column stat cards on phones; nav: dashboard + notifications enabled
  (`CURRENT_PHASE = 3`).
- **Fixes found while verifying**: new pages under `app/(app)` need their own
  `instant = false`; the smoke test follows the new `/` redirect.

### Phase 4 — Document Center
- **Data model** (migration `0004`): `documents.category` (7 categories, CHECK) and
  `current_version_id`; `document_versions` (number per document, server-generated storage key,
  original filename, type, MIME, size, SHA-256, uploader, processing status/error, page and
  character counts); `document_version_texts` (extracted text, 1:1); trigram index on titles;
  notification type `DOCUMENT`.
- **Upload pipeline** (ADR-029): size enforced at Nginx (30 MB), the Next dev proxy, an ASGI
  `Content-Length` middleware and while hashing; content sniffing (PDF magic, OOXML parts,
  decodable text) must match the extension allow-list; zip-bomb, encrypted-entry and path
  checks; filenames sanitised; object stored first, DB committed second (object removed on
  failure), extraction queued after commit.
- **Extraction worker** (ADR-030): Celery task `documents.extract_text` on the `documents`
  queue — PDF (pypdf), DOCX (python-docx), XLSX (openpyxl + defusedxml), TXT (UTF-8/16,
  TIS-620); page/character/cell limits, soft/hard time limits, row lock, idempotent;
  failures become `FAILED` with a Thai message and a notification to the uploader; manual
  re-processing for failed/pending versions.
- **API**: list/search/filter/sort (`q`, category, file type, status, mine), create with first
  version, detail with capabilities, edit metadata, soft delete, new version, re-process,
  streamed download (RFC 5987 filename, `nosniff`, audited), text preview (first 50 000
  characters), ACL read/replace with share notifications, document history, directory lookup
  `GET /directory/users` (ADR-031). Every read goes through `accessible_documents_condition`;
  unknown and inaccessible documents both return 404. Capabilities (ADR-028) combine the
  ACL level with permissions.
- **Dashboard**: documents section now has my documents, processing/failed counts and the 5
  most recently updated accessible documents.
- **Frontend**: `/documents` (search, filters, sort, pagination, upload dialog with drag & drop,
  client-side type/size checks, auto title), `/documents/[id]` (metadata, versions with
  status polling every 3 s while processing, download, re-process, text preview, edit, new
  version, delete, sharing editor with directory search and level per principal, history);
  dashboard documents card; `DOCUMENT` notifications in the bell and inbox; nav
  `CURRENT_PHASE = 4`. Dynamic route pattern: server page awaits `params` + `loading.tsx` (ADR-032).
- **Fixes found while verifying**: the frontend notification schema rejected `DOCUMENT`
  (dashboard failed to load after a processing failure) → enum extended + regression test;
  the Next dev proxy cut request bodies at 10 MB (plain-text 500) →
  `experimental.proxyClientMaxBodySize: "30mb"`; `/documents/[id]` failed `next build`
  until params were awaited on the server.

### Phase 5 — Task Management & Employee Center
- **Data model** (migration `0005`): `tasks` (status, priority, due date, owning department,
  soft delete), `task_assignees`, `task_comments`, `task_attachments`, `task_events`
  (timeline), `employee_hr_profiles` (sensitive HR data, national ID last 4 digits only),
  trigram indexes on task titles and user display names, notification type `TASK`.
- **Task access** (ADR-033): one visibility predicate (`task_access.visible_tasks_condition`)
  for lists, details and the dashboard; per-task capabilities (edit, status, cancel, assign,
  delete, attach); department managers manage their department's tasks only; assignees must
  belong to the task's department unless `tasks:manage_all`; without `tasks:assign` people
  can only assign themselves; invisible tasks answer 404.
- **Task API**: list with scopes (all/assigned/created/department), search, status/open/
  priority/assignee/overdue filters, sorting by due date/priority/updated/created; create,
  edit, status changes (sets `completed_at`), replace assignees, soft delete; comments
  (edit own, managers moderate); attachments through the shared upload pipeline (ADR-036,
  max 20 per task, audited downloads); history; assignable-people lookup. Notifications:
  assigned, status changed, new comment (never to the actor).
- **Employee Center API** (ADR-034): directory of active people with work contacts (search,
  department filter, suspended accounts with `users:read`), profiles with department
  manager, account section (`users:read`) and capabilities; separate HR record endpoint —
  self or `employees:read_sensitive` (reads by others audited), writes with
  `employees:manage` + `employees:read_sensitive` (audit keeps field names only).
- **Dashboard**: `tasks` section (open assigned, overdue, due within 7 days, 5 earliest due).
- **Frontend**: `/tasks` (scope tabs, filters, overdue toggle, create dialog with assignee
  picker for people with `tasks:assign`), `/tasks/[id]` (status control, edit, delete,
  assignees dialog, comments, attachments with upload/download/delete, history);
  `/employees` (directory cards, department tab with member counts and department
  create/edit + manager choice for `departments:manage`, "เพิ่มพนักงาน" for `users:create`),
  `/employees/[id]` (work contacts, account card with edit/roles/suspend by capability, HR
  card loaded on demand with edit dialog); dashboard "งานของฉัน" card; `TASK` notifications;
  activity feeds label document/task/HR events; nav `CURRENT_PHASE = 5` (account
  administration lives in the Employee Center, ADR-035; `/settings` moved to Phase 8).
- **Fixes found while verifying**: avatar initials showed Thai leading vowels ("ไเ" →
  "อท"); activity feeds showed raw `document.*` codes (labels added).

### Phase 6 — AI Assistant & Tool Calling
- **Data model** (migration `0006`): `chat_sessions`, `chat_messages` (neutral tool calls,
  provider payload replayed unchanged, token counts), `ai_action_requests` (proposed changes
  with status and expiry).
- **Providers** (ADR-037): Anthropic via the official `anthropic` SDK (streaming, no sampling
  parameters, eager tool-input streaming, prompt caching, server-side refusal fallback on
  supported models) and OpenAI-compatible servers (Ollama, vLLM, LM Studio, OpenAI) over
  `httpx2` with streamed tool-call assembly; Thai, body-free error mapping
  (misconfigured / rate limited / unavailable / bad request / refused / truncated).
- **Tools** (ADR-038): `get_my_tasks`, `get_task_details`, `find_colleagues` (read-only) and
  `create_task`, `update_task_status` (proposals). Strict argument validation; tools run as the
  user through the task services and visibility predicate; offered only with `ai:use_tools`
  plus each tool's permission. Ticket tools move to Phase 8 (ADR-039).
- **Chat API** (ADR-040): status, sessions (list/create/rename/soft delete/detail), streaming
  messages over server-sent events, confirm/reject actions. Tool loop up to
  `AI_CHAT_MAX_TOOL_STEPS`; per-user rate limit; last `AI_CHAT_HISTORY_MESSAGES` messages
  sent; confirmations re-check permissions, run exactly once and append a system note.
- **Frontend**: `/assistant` — conversation list (collapsible on phones, delete with
  confirmation), streamed answers with a stop button, tool chips, action cards with
  ยืนยัน/ปฏิเสธ and a link to the result, plain-text rendering with in-app links only,
  "not configured" state that keeps history readable, suggestions; nav `CURRENT_PHASE = 6`.
- **Settings**: `AI_CHAT_REFUSAL_FALLBACK`, `AI_CHAT_RATE_LIMIT_MESSAGES`,
  `AI_CHAT_RATE_LIMIT_WINDOW_SECONDS`, `AI_CHAT_HISTORY_MESSAGES`, `AI_CHAT_MAX_TOOL_STEPS`,
  `AI_ACTION_TTL_MINUTES`; `AI_CHAT_MAX_TOKENS` default 16000.
- **Fixes found while verifying**: the Next.js proxy gzip-compressed the event stream and
  delivered it in one chunk (answers did not stream) → `Cache-Control: no-store, no-transform`;
  confirmation notes showed raw JSON → readable text with a link.

### Phase 7 — RAG Knowledge Base
- **Data model** (migration `0007`): `document_chunks` (passage text, page, `vector(1024)`
  embedding + model, HNSW and trigram indexes), version index status/error/count/time,
  `chat_messages.citations`.
- **Indexing** (ADR-042): after text extraction the worker chunks the text (≤ `RAG_CHUNK_SIZE`
  characters, `RAG_CHUNK_OVERLAP` overlap, cuts at page/paragraph/line/sentence boundaries,
  PDF page numbers from form feeds) and embeds it when an embedding provider is configured
  (OpenAI-compatible `/embeddings`, batches of 32, 1024 dimensions enforced). Embedding
  failures keep the chunks for keyword search and mark the version `FAILED`; text-less
  versions are `SKIPPED`; older versions' chunks are removed. `python -m app.cli
  reindex-documents [--all]` and Celery task `documents.index_version`.
- **Retrieval** (ADR-041): ACL predicate and current-version filter inside the ranking SQL;
  hybrid semantic + keyword ranking (reciprocal rank fusion), keyword-only without embeddings or
  when the query cannot be embedded (`degraded`).
- **API**: `GET /documents/search` (best passage per accessible document); version responses
  include index status; chat `done` events and stored answers carry citations.
- **Assistant** (ADR-043): tools `search_documents` (numbered passages) and `read_document`
  (12,000 characters, for summaries); answers cite `[n]`, only cited sources are stored; an
  empty search tells the model to report "no evidence"; prompt rules for untrusted passages.
- **Frontend**: Document Center "ค้นหาในเนื้อหา" mode (passages with page and category, plain
  text, mode note), index status per version, "สรุปด้วยผู้ช่วย AI" (pre-fills the assistant,
  nothing sent automatically), "แหล่งอ้างอิง" under assistant answers with links.
- **Fixes found while verifying**: overlapping passages started mid-paragraph or lost the
  overlap after a paragraph cut, and passages could straddle PDF pages → overlap starts at a
  line inside real content and never crosses a page break.

### Phase 8 — Helpdesk, Notifications & Analytics
- **Data model** (migration `0008`): `tickets` (sequence numbers `IT-2026-000001`),
  `ticket_comments`, `ticket_events` (both with `is_internal`), `notification_preferences`,
  notification type `TICKET`, `email_status`/`emailed_at`.
- **Helpdesk** (ADR-044): `/tickets` API (list with scopes mine/assigned/unassigned/all,
  filters, search; detail with capabilities; status; assignee; category/priority; comments
  incl. internal notes; history; IT assignee list). Notifications to dispatchers, assignee and
  requester. Assistant tools `get_my_tickets` and `create_ticket` (confirmed, ADR-039).
- **E-mail** (ADR-045): SMTP sender, worker task `notifications.send_emails` after commit,
  per-type preferences API + card on "บัญชีของฉัน", password-reset links by e-mail, Mailpit
  in Docker.
- **Analytics & reports** (ADR-046/047): `GET /analytics/overview`, `POST /analytics/summary`
  (AI, numbers only), `GET /reports/overview.xlsx|pdf` (audited). Page `/analytics`: scope tabs,
  periods, KPI cards, daily charts, breakdowns, workload table, exports, AI summary.
- **Settings** (ADR-048): `/settings` role list and permission editor (create/rename/delete
  custom roles, grant only what you hold, ADMIN locked).
- **Frontend**: `/helpdesk`, `/helpdesk/[id]` (requester actions in plain language, IT status
  / assignee / category / priority controls, internal notes highlighted), all modules enabled
  in the navigation (`CURRENT_PHASE = 8`).

### Phase 9 — Security, Testing & Deployment
- **Security review** (`docs/SECURITY.md` §9): automatic sweeps prove every one of the 95 API
  operations except 7 public ones needs a session, and every state-changing one needs the CSRF
  token; ACL/RAG/task/ticket isolation suites re-checked.
- **Hardening**: rate limiter fails closed in production; per-user limits for uploads, exports
  and AI summaries; Nginx login limit and non-spoofable `X-Forwarded-For` (ADR-049);
  Content-Security-Policy and Permissions-Policy for pages and API (ADR-050); public readiness
  shows only the overall status (`X-Health-Token` / `GET /health/details`); production refuses
  weak or placeholder secrets, development credentials, insecure cookies, `DEBUG`,
  `SEED_DEV_PASSWORD` and non-HTTPS URLs.
- **Retention** (ADR-051): Celery `beat` service + `maintenance.purge` daily and
  `python -m app.cli purge [--dry-run]` (soft-deleted documents and their files, orphaned files,
  old chats, expired sessions/reset tokens, read notifications).
- **Backups** (ADR-052): `scripts/backup.sh [--prod]` (pg_dump + all files + checksums),
  `scripts/restore.sh` (verification restore into a separate database/bucket, or full restore
  with `--yes`); import rejects unsafe archive names.
- **Production** (ADR-053, `docs/DEPLOYMENT.md`): `docker-compose.prod.yml` (prod images,
  non-root, only Nginx published, Redis password, log rotation, beat), HTTPS Nginx template
  (TLS 1.2/1.3, HSTS, ACME webroot), `.env.production.example`, `create-admin` for the first
  administrator, `ensure-bucket` in the migrate step.
- **Tests**: `test_security_review.py`, `test_maintenance.py`, `test_bootstrap.py`, stricter
  `test_config.py`, end-to-end workflows over real HTTP (`scripts/e2e-test.sh`), frontend CSP
  and status-page tests.

### After Phase 9 — Ticket attachments (2026-11-12)
- Migration `0009` `ticket_attachments`; `GET/POST /tickets/{id}/attachments`,
  `DELETE …/{attachment_id}`, `GET …/{attachment_id}/download` (ADR-054).
- Screenshots (PNG/JPEG by signature) plus PDF/DOCX/XLSX/TXT; internal files for IT; uploader or
  IT removes; closed/cancelled tickets accept files only from IT; notifications, audit, history.
- UI: "ไฟล์แนบ" card on the ticket page (image preview, download, delete, internal toggle for IT)
  and optional files in the "แจ้งปัญหาใหม่" dialog (uploaded right after the ticket is created).
- Verified: backend **328 passed**, frontend **97 passed**, e2e 6 passed; migration round trip
  on the test DB; browser: employee reported a ticket with a PNG screenshot from the dialog, IT
  previewed it and added an internal file, the employee saw only the screenshot and got 404 for
  the internal file.

### After Phase 9 — Front end on Vercel, API hosted separately (2026-11-12)
- The user deployed `frontend/` to Vercel from GitHub; the page stayed blank because no API was
  reachable (`BACKEND_INTERNAL_URL` unset). Chosen layout: front end on Vercel, API side on a
  container host (Railway + R2 documented in `docs/DEPLOYMENT.md` section 9, ADR-055).
- `PROXY_SHARED_SECRET` + `TrustedProxyMiddleware` (403 `proxy_required` without the header,
  visitor IP from `X-Vercel-Forwarded-For`), `frontend/vercel.json` adds the header, API
  responses default to `Cache-Control: no-store`, `postgres://` URLs accepted.
- Verified: backend **341 passed**, frontend **97 passed**, e2e 6 passed, smoke passed. Not yet
  verified on Vercel/Railway themselves (needs the user's accounts): the header transform,
  25 MB uploads and streamed answers through Vercel's proxy.

## In Progress
- Nothing. All phases (0–9) are complete.

## Remaining
- Go-live: the front end is on Vercel; the API side is not deployed yet. Chosen next: free
  Oracle Cloud Always Free VM + DuckDNS + Let's Encrypt running the single-host stack
  (`docs/DEPLOYMENT.md` section 10); nginx's login limit is keyed by the Vercel-reported
  visitor IP so all users do not share Vercel's addresses.
- Not built (possible next work): due-date reminders, settings UI for AI / SMTP, OCR for
  scanned PDFs, antivirus scanning, browser-driven UI tests (Playwright).

## Technical Decisions
See `docs/DECISIONS.md`. Key ones: same-origin API via proxy (ADR-002); psycopg 3 for async and
sync (ADR-003); permission-based RBAC with roles as data (ADR-005); ACL evaluated at query time
for RAG (ADR-006); provider-independent AI with separate chat/embedding config (ADR-007);
S3-generic storage code (ADR-009) with digest-pinned `pgsty/minio` (ADR-013); selector event
loop on native Windows (ADR-014); `127.0.0.1` host defaults (ADR-015); session model with
rotating refresh-token families (ADR-016); CSRF double-submit (ADR-017); grant-only-what-you-hold
(ADR-018); ACL foundation in Phase 2 (ADR-019); isolated test database (ADR-020); client-side
session gate (ADR-021); notification inbox in Phase 3 (ADR-023); permission-gated dashboard
summary (ADR-024); business time zone (ADR-025); charts without a library (ADR-026);
dashboard as home page (ADR-027); document capabilities = ACL level × permissions (ADR-028);
upload pipeline with content sniffing and store-then-commit (ADR-029); text extraction in the
worker (ADR-030); directory lookup for sharing (ADR-031); dynamic route pattern (ADR-032);
task visibility predicate + capabilities (ADR-033); HR data in its own audited endpoint
(ADR-034); account administration in the Employee Center (ADR-035); shared upload helpers and
business-day due dates (ADR-036); AI provider adapters (ADR-037); AI tools run as the user and
changes need confirmation (ADR-038); ticket tools deferred to Phase 8 (ADR-039); chat streaming
over server-sent events (ADR-040); retrieval with the ACL in SQL and hybrid ranking (ADR-041);
fixed 1024-dimension embeddings and re-indexing (ADR-042); RAG through tools with citations
(ADR-043); helpdesk visibility and internal notes (ADR-044); e-mail after commit with
preferences (ADR-045); permission-bound analytics scopes (ADR-046); Excel/PDF exports
(ADR-047); role editor on `/settings` (ADR-048); fail-closed rate limiting (ADR-049); CSP
without nonces (ADR-050); retention clean-up (ADR-051); backups with verified restore
(ADR-052); single-host production stack (ADR-053); ticket attachments (ADR-054); Vercel front end with a
separately hosted API (ADR-055).

## Tests
### Phase 9 verification — 2026-11-12
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (128 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **318 passed**, 7 skipped (6 end-to-end tests run separately, 1 Windows-only) |
| — `tests/api/test_security_review.py` | ✅ 12: inventory of 95 operations, **401 sweep** over every non-public route, **CSRF sweep** over every state-changing route, API security headers, readiness hidden/token/admin details, rate-limit guards on upload/export/summary routes, per-user export limit (429 + Retry-After), limiter fails closed (503) and open |
| — `tests/api/test_maintenance.py` | ✅ 5: dry run, purge removes only expired data (documents + files, orphans after grace, chats, sessions, reset tokens, read notifications), idempotent, storage failure keeps the row for retry, backup export/import round trip, unsafe archive entries rejected |
| — `tests/api/test_bootstrap.py` | ✅ 5: first admin can sign in with ADMIN+EMPLOYEE, audited, bad e-mail/weak passwords/duplicates refused |
| — `tests/unit/test_config.py` | ✅ 18: production accepts a complete strong config and refuses each unsafe value (9 cases) |
| `bash scripts/e2e-test.sh` (dev stack, through the Next.js proxy, real worker) | ✅ **6 passed** (twice): anonymous refusal + page CSP, task lifecycle + isolation, document upload → extraction/index → search, private document invisible to another department, download, admin-only delete; helpdesk with internal notes + notifications; report scopes + PDF; admin endpoints |
| Frontend `vitest` | ✅ **92 passed** (new: page CSP/headers, status page admin details vs hidden summary) |
| Frontend lint, typecheck, Prettier | ✅ |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Backup / restore (dev) | ✅ `backup.sh` → verification restore into `orbit_restore_check` + bucket: all table counts equal, migration `0008`, 4 files byte-identical; scratch database and bucket removed |
| Production stack on this machine (`docker-compose.prod.yml`, random secrets, self-signed TLS on :8443) | ✅ images built (backend + `next build`); migrate + sync-rbac + ensure-bucket; only Nginx published; containers non-root; HTTP→HTTPS 301; HSTS + CSP + Permissions-Policy; TLS ≤ 1.1 refused; `/api/docs` 404; public health without details, details with `X-Health-Token`; `create-admin` refuses a weak password then creates the admin; cookies Secure + HttpOnly (CSRF readable) + SameSite=Lax; upload processed and indexed by the prod worker and found by search; Thai PDF with Loma/Kinnari embedded; Nginx login burst → 429; `seed-dev` refused; purge dry run; `backup.sh --prod` + verification restore. The verification stack and its volumes were removed afterwards |

### Phase 9 acceptance criteria
| Criterion | Status |
| --- | --- |
| Critical workflows pass tests | ✅ unit/API/integration (318) + end-to-end over HTTP (6) + frontend (92) |
| No known cross-permission data leakage in the test suite | ✅ route-wide auth/CSRF sweeps; ACL, RAG, task, ticket, HR, analytics isolation suites |
| Deployment, environment configuration, backup and recovery documented | ✅ `docs/DEPLOYMENT.md`, `.env.production.example`, RUNBOOK §7a/§8, tested scripts |
| Known limitations disclosed | ✅ `docs/DEPLOYMENT.md` §8 and Known Issues below |

### Phase 8 verification — 2026-11-12
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (125 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **288 passed**, 1 skipped (Windows-only) |
| — `tests/api/test_tickets.py` | ✅ 14: numbering, dispatcher notifications, audit, requester-only visibility (404), IT scopes/filters/search, assignment rules, status transitions by role, internal notes hidden + not notified, requester reply resumes waiting ticket, IT-only category/priority, validation |
| — `tests/api/test_notification_email.py` | ✅ 8: preferences defaults/update/per-user/validation, queue only after commit (not on rollback), API events queue mail, delivery SENT/SKIPPED/FAILED + idempotent, no SMTP → skipped, SMTP STARTTLS/login, reset link by e-mail |
| — `tests/api/test_analytics.py` | ✅ 11: own/department/all metrics, scope permissions, period selection + validation, export permissions, Excel rows limited to visible records + formula guard + audit, PDF with embedded Thai font, AI summary (numbers only, 503 without a model) |
| — `tests/api/test_ai.py` | ✅ +3: `get_my_tickets` returns only my tickets, `create_ticket` only after confirmation, ticket tools follow permissions |
| `alembic check` / `downgrade 0007` + `upgrade` (**test** DB) | ✅ `0008 (head)`, no drift, round trip ok |
| Frontend `vitest` | ✅ **88 passed** (new: helpdesk list/create/detail for requester and IT, analytics scopes/periods/exports/summary, role editor, e-mail preferences, navigation) |
| Frontend lint, typecheck, Prettier | ✅ |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker stack, real worker, Mailpit) | ✅ employee reported "เครื่องพิมพ์ชั้น 3 พิมพ์ไม่ออก" → `IT-2026-000001`; Mailpit received the e-mails for IT and admin; IT assigned it (auto "กำลังดำเนินการ"), added an internal note (no e-mail) and a reply, resolved it; the requester got both e-mails, did not see the internal note or its history entry, and confirmed the fix ("ปิดเรื่อง"); manager `/analytics` department scope with Excel/PDF downloads (200) and 403 for `scope=all`; admin `/settings` permission editor |

### Phase 8 acceptance criteria
| Criterion | Status |
| --- | --- |
| Employees submit tickets; IT Support manages authorized tickets | ✅ API + UI + assistant tool; tests + browser |
| Notifications persisted | ✅ in-app + e-mail after commit with preferences; tests + Mailpit |
| Reports use real data and respect permissions; export works | ✅ SQL aggregates per scope, visible-rows-only exports, Excel + Thai PDF; tests + browser |
| Tests cover the complete workflows | ✅ backend 288, frontend 88 |

### Phase 7 verification — 2026-11-12
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (113 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **252 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/unit/test_rag_units.py` | ✅ 16: chunk sizes/overlap/paragraph cuts/no text lost, text without breaks, PDF page numbers, invalid settings, vector literal, embedding batching + request shape, async embedding, failures (status, bad body, wrong dimension, wrong count, connection), provider settings + 1024-dimension rule |
| — `tests/api/test_rag.py` | ✅ 12: upload indexed + keyword search (Thai), hybrid semantic search ranks the right document, embedding failure → keyword fallback + `degraded` + re-index recovers, text-less version SKIPPED, PDF pages, **isolation** (private/department documents invisible to others, `documents:manage` override, ACL grant and revoke apply immediately, deleted documents disappear), only the current version is searched, `documents:read` required, assistant answers only from permitted passages (private passage never in the model's input) with stored citations, "no evidence", `read_document` respects access, document tools need `documents:read` |
| `alembic upgrade head` / `alembic check` / `downgrade 0006` + `upgrade` (**test** DB) | ✅ `0007 (head)`, no drift (pgvector type not reflected — warning only), round trip ok |
| Frontend `vitest` | ✅ **70 passed** (new: content search results + plain-text snippets + empty/degraded states, index status label, cited sources under answers, `?prompt=` pre-fill without sending) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker stack, real Celery worker, verification stub for chat + embeddings) | ✅ `reindex-documents` indexed the existing "นโยบาย WFH 2569" through the worker with embeddings; employee: "ค้นหาในเนื้อหา" → "ทำงานที่บ้านได้กี่วัน" → the WFH policy, mode "ค้นหาตามความหมายและคำ"; assistant → tool "ค้นหาในเอกสาร" → answer ending in `[1]` with "แหล่งอ้างอิง [1] นโยบาย WFH 2569" linking to the document; **IT account (other department)**: content search 0 results, assistant "ไม่พบข้อมูล…" and no WFH text anywhere in the stream; 375 px no overflow; `.env` restored to `disabled` and documents re-indexed without the stub vectors |

### Phase 7 acceptance criteria
| Criterion | Status |
| --- | --- |
| Uploaded documents can be indexed | ✅ automatic after extraction (worker) + `reindex-documents`; tests + browser |
| Semantic search returns relevant authorized documents | ✅ hybrid ranking tests (deterministic test embeddings) + browser (stub embeddings). Not yet measured with a real embedding model (none available here) |
| Answers include source references; insufficient evidence reported | ✅ citations stored and shown; "no evidence" path tested |
| Unauthorized chunks are never passed to the LLM; tests verify cross-permission isolation | ✅ ACL in the retrieval SQL; isolation tests on search and on the model's input; browser check with a second department |

### Phase 6 verification — 2026-11-12
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (107 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **224 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/unit/test_ai_providers.py` | ✅ 16: OpenAI-compatible request shape (system first, tool calls, tool results, system notes), streamed text + tool-call fragments + usage, invalid tool JSON, truncation, error mapping 401/404/429/400/503 without leaking bodies, connection failure; Anthropic (SDK over a mock transport): headers, beta fallback + `fallbacks`, no temperature/thinking, prompt caching, eager tool streaming, raw content replayed unchanged, parallel tool results in one message, streamed text + tool use + usage, refusal flag, plain endpoint for models without fallbacks, error mapping; provider factory |
| — `tests/api/test_ai.py` | ✅ 17: 401/403 guards, disabled provider (status + 503), tools by permission (incl. a chat-only role with no tools), private sessions (404 for others; rename/delete), message validation, streamed answer + auto title + history replay, provider error (question kept, no half answer), refusal + step limit, rate limit 429, read tools see only the user's tasks (someone else's task is "not found", title never reaches the model, UI gets no raw tool data), unknown tool / bad JSON / invalid arguments answered with errors, create task only after confirmation (acted as the user, Bangkok due date, audit, never twice, system note reaches the model), reject + ownership, expiry, employees cannot propose assigning others, confirmation re-checks permissions (FAILED after reassignment), assignees cannot propose cancelling; stream sent with `no-transform` |
| `alembic upgrade head` / `alembic check` / `downgrade 0005` + `upgrade` (**test** DB) | ✅ `0006 (head)`, no drift, round trip ok |
| Frontend `vitest` | ✅ **66 passed** (new: SSE parsing, plain-text rendering + safe links, not-configured state, streaming + action confirmation with CSRF, stream errors, rate limit before streaming; nav test now uses a Phase 8 module) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ (`/assistant` prerendered) |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker stack, employee account, verification stub) | ✅ no real AI provider is available on this machine, so a temporary keyword-scripted OpenAI-compatible stub ran inside the worker container for this check only (`.env` restored to `disabled` afterwards). Page shows the model badge and suggestions; "สร้างงาน…" → tool chip "เตรียมสร้างงาน" + action card (summary with due date and "คุณเอง") → ยืนยัน → card "ดำเนินการแล้ว" with a link, task created; "งานของฉันมีอะไรบ้าง" → "ค้นหางานของคุณ" → answer listing the new task with a clickable `/tasks/<id>` link; stream timing through the Next proxy: 6 chunks ~50 ms apart after the `no-transform` fix (1 gzip chunk before); 375 px: no overflow, list behind "บทสนทนาทั้งหมด"; console clean; after restoring `.env`: "ยังไม่ได้ตั้งค่าผู้ให้บริการ AI", composer disabled, history still visible |

### Phase 6 acceptance criteria
| Criterion | Status |
| --- | --- |
| Chat requests reach the backend; backend talks to the configured provider | ✅ both adapters tested against their wire formats; end-to-end through the real stack with an OpenAI-compatible endpoint (stub). Not yet run against a live Claude or Ollama model (none available here) |
| Chat history persisted | ✅ API tests + browser (sessions, messages, actions, notes) |
| AI can call permitted tools; tool permissions enforced; mutating actions need confirmation | ✅ 17 API tests + browser |
| Provider errors handled safely; AI tests pass | ✅ error-mapping tests (no bodies or keys), 33 new backend + 6 new frontend tests |

### Phase 5 verification — 2026-11-11
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (97 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **191 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/api/test_tasks.py` | ✅ 22: 401/403 guards, personal task (self-assigned, own department, events, audit, no self-notification), employees cannot assign others or create in another department, managers assign within their department only (422 cross-department/unknown/inactive), replace assignees (notifications, access removed), visibility matrix for 6 users, 404 on every sub-resource for invisible tasks, department scope needs permission, assignee capabilities (status yes; edit/cancel/delete no), manager edit + `manage_all` department move + delete, clearing fields and no-op updates, time zone required, scopes/filters/search (`%` literal)/sorting/pagination/overdue, assignable-people scoping, comments (notifications, authorship, moderation, length), attachments (store, download headers + audit, spoofed file rejected, outsider 404, delete removes object), storage failure leaves no row, 413 before reading, dashboard task summary |
| — `tests/api/test_employees.py` | ✅ 6: directory permission + active-only + work fields only + search/department filter + suspended accounts need `users:read`, profile sections and capabilities per role, inactive profiles hidden, HR record (self read, others 403 for EMPLOYEE/MANAGER/IT, writes HR only, audit of reads, audit without values, full replacement), HR validation (no full national ID) |
| — `tests/api/test_dashboard.py` | ✅ section matrix now includes `tasks` |
| `alembic upgrade head` / `alembic check` / `downgrade 0004` + `upgrade` (test DB) | ✅ `0005 (head)`, no drift, round trip ok |
| Frontend `vitest` | ✅ **60 passed** (new: task list scopes/filters, create validation + self-assignment, assignee picker, detail capabilities, plain-text comments, not-found state, due-date conversion; directory/departments, HR record on demand + validation, Thai initials; dashboard tasks card) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ (`/tasks`, `/employees` prerendered; `/tasks/[id]`, `/employees/[id]` partial prerender) |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker stack, dev accounts) | ✅ manager: department tab visible, assignee picker lists only SALES people, created an overdue HIGH task for the employee, attached a Thai-named TXT, commented, downloaded (200); employee: two `TASK` notifications + "งานของฉัน" card (1 open, 1 overdue), task page without edit/delete/assign/cancel, status → รอตรวจสอบ recorded in history; employee directory shows work contacts only, `GET /employees/{manager}/hr` 403, own HR 200, `include_inactive` 403; HR: account card with edit only (no roles/suspend), HR card hidden until clicked, record saved (ID shown as `•••• •••• 4321`); audit log has `employee.hr_profile_viewed` and `employee.hr_profile_updated` with field names only; HR opening the SALES task gets "ไม่พบงาน"; 375 px: no horizontal overflow on `/tasks`, `/tasks/[id]`, `/employees`, `/employees/[id]`, `/dashboard`; console: only the expected 401/403/404 from logouts and permission probes |

Note: the migration round trip was first run against the **dev** database by mistake, which
dropped the browser-verification data in the Phase 5 tables (one task with its comment,
attachment row and history, one HR record, the `TASK` notifications). Audit entries and all
Phase 0–4 data were unaffected; the attachment object remains orphaned in MinIO
(`tasks/fb07d098-…`). RUNBOOK §5 now shows how to run round trips on the test database.

### Phase 5 acceptance criteria
| Criterion | Status |
| --- | --- |
| Employees see their permitted tasks; managers manage authorized team tasks | ✅ visibility matrix + capability tests, browser (manager vs employee vs HR) |
| Task changes persist; permission boundaries enforced | ✅ API tests (status, assignees, comments, attachments, delete), browser |
| Employee information protected | ✅ HR record endpoint tests (403/audit/no values), directory field tests, browser probes |
| Tests cover task and employee permissions | ✅ 28 new backend API tests, 15 new frontend tests |

### Phase 4 verification — 2026-11-11
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (84 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **163 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/api/test_documents.py` | ✅ 26: 401/403, upload of all four types + extraction, spoofed/unsupported/empty/oversized/zip-bomb files, storage cleanup on DB failure, list visibility per role and ACL, search/filter/sort, 404 for inaccessible documents, capabilities, edit/visibility rules, new version, re-process rules, download + audit, text preview, ACL replace validation + notifications + escalation, history permissions, soft delete, directory lookup |
| — `tests/unit/test_document_files.py` | ✅ sniffing, filename sanitising, text decoding, zip checks |
| `alembic upgrade head` / `alembic check` / `downgrade 0003` + `upgrade` | ✅ `0004 (head)`, no drift, round trip ok |
| Frontend `vitest` | ✅ **45 passed** (new: documents list/filters, upload validation, detail capabilities, sharing editor, DOCUMENT notifications on the dashboard) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ (`/documents` prerendered, `/documents/[id]` partial prerender) |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker stack with the real worker) | ✅ employee uploads a Thai TXT → title filled from the filename → PENDING → READY → text preview; download keeps the Thai filename; shared VIEW with a manager via directory search → manager notified; history lists upload/share/download; corrupt PDF → FAILED with a Thai message + notification; `.exe` → 415; 15 MB upload → 201 and READY (text capped at 2 000 000 characters); 36 MB → 413; 375 px: no horizontal overflow on list, detail and dashboard |

### Phase 4 acceptance criteria
| Criterion | Status |
| --- | --- |
| Users can upload, list, search, filter and download documents they may access | ✅ API tests + browser |
| Files are validated (type sniffing, size) and stored in MinIO | ✅ unit + API tests, integration storage round trip, browser 415/413 |
| Text is extracted asynchronously with a visible processing status | ✅ worker in browser run, status polling, FAILED path with notification |
| Versions, metadata and categories work | ✅ tests + browser |
| ACL can be managed from the UI and is enforced on every read | ✅ ACL tests (404 for inaccessible), sharing editor in browser |
| Document actions are audited and visible in history | ✅ tests + browser |

### Phase 3 verification — 2026-11-11
Backend checks ran inside the backend container (Python 3.13), as in Phase 2.

| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (75 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **113 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/api/test_dashboard.py` | ✅ 15: 401 unauthenticated, section matrix for all 5 roles + a user with no roles, active sessions + previous sign-in + logout, own-activity isolation, changes by others on my account, ACL-scoped document count (department/private/admin override), organisation counts (inactive users, soft-deleted department), security counts (failed sign-ins), Bangkok-day grouping, period boundaries |
| — `tests/api/test_notifications.py` | ✅ 16: 401 on all endpoints, newest-first + unread filter + pagination, isolation (admin cannot read/mark another user's notification), mark one/all (idempotent), CSRF required, password-change and admin-change producers (actor not notified), DB rejects external links, service rejects non-relative links |
| `alembic upgrade head` / `alembic check` / `downgrade 0002` + `upgrade` | ✅ `0003 (head)`, no drift, round trip ok |
| Frontend `vitest` | ✅ **34 passed** (new: dashboard sections/errors/retry, chart tooltip/legend/table/gridlines, notifications list/filter/mark-all with CSRF/empty/unsafe links, bell badge) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ (`/dashboard`, `/notifications`, `/system-status`, `/account` prerendered) |
| `bash scripts/smoke-test.sh` | ✅ passed (follows `/` → `/dashboard`) |
| Browser (Docker stack, in-app browser) | ✅ admin: all three optional sections with real counts (5 users, 5 departments, sign-ins/failures from the audit log); admin edit of the employee created a real notification; logout → `/login?next=%2Fdashboard` → employee sign-in → dashboard without organisation/security sections, notification preview shows the change, bell badge 1 → "อ่านทั้งหมด" → `POST /notifications/read-all` 200, badge gone, unread card 0; employee nav has no "ตั้งค่า"; 375 px: no horizontal overflow on `/dashboard` and `/notifications`; console clean after the `instant` fix |

### Phase 3 acceptance criteria
| Criterion | Status |
| --- | --- |
| Authenticated users can access the dashboard | ✅ browser (admin + employee); `/` and login land on it |
| Dashboard metrics are returned by the backend | ✅ `GET /dashboard/summary`, real DB aggregates (tests) |
| Users see only authorized information | ✅ section matrix per role, ACL-scoped documents, own-only activity and notifications (tests + browser) |
| Navigation works; responsive layouts work | ✅ nav tests, mobile drawer, 375 px checks, 2-column cards on phones |

### Phase 2 verification — 2026-11-11
Backend checks ran **inside the backend container** (Python 3.13) because Windows Application
Control now blocks the host venv's compiled wheels (see Known Issues).

| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 ORBIT_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
| ruff check + format, mypy strict (66 files) | ✅ clean |
| `pytest` (container, incl. integration + DB tests) | ✅ **82 passed**, 1 skipped (Windows-only event-loop test) |
| — `tests/api/test_auth.py` | ✅ 16: cookies/flags, generic errors, inactive users, 401 on all protected endpoints, Bearer, tampered JWT, CSRF, refresh rotation, reuse detection, parallel-tab grace, logout revocation, rate limit 429, change password, reset flow |
| — `tests/api/test_authorization.py` | ✅ 22: role × endpoint matrix for all 5 roles, HR vs privileged roles, grant-only-what-you-hold, locked ADMIN, last-admin protection, instant role revocation, deactivation sign-out, custom roles, audit trail, DB append-only trigger, conflicts, pagination |
| — `tests/api/test_document_access.py` | ✅ 7: every ACL rule evaluated by PostgreSQL |
| `alembic upgrade head` / `alembic check` / offline SQL | ✅ `0002 (head)`, no drift; `downgrade 0001` + `upgrade` round trip |
| Frontend `vitest` | ✅ **22 passed** (CSRF header, refresh-and-retry, no refresh without session, open-redirect guard, login form validation/errors/redirect, permission-filtered nav) |
| Frontend lint, typecheck, Prettier, `next build` | ✅ (`/login`, `/forgot-password`, `/reset-password`, `/account` prerendered) |
| `docker compose up -d` + `migrate` (`alembic` + `sync-rbac`) | ✅ 38 permissions, 5 roles; second run: no changes |
| `docker compose exec backend python -m app.cli seed-dev` | ✅ 5 accounts; re-run creates 0; refused when `ENVIRONMENT` ≠ development |
| `bash scripts/smoke-test.sh` | ✅ passed |
| Browser (Docker frontend → backend) | ✅ `/account` → `/login?next=%2Faccount` → sign-in as employee → back to `/account`; logout → 204, next visit redirected to login; employee sidebar has no "ตั้งค่า", admin sidebar does |

### Phase 2 acceptance criteria
| Criterion | Status |
| --- | --- |
| A user can log in and log out | ✅ API tests + browser |
| Unauthenticated users cannot access protected APIs | ✅ 401 on every protected endpoint (test) |
| Role permissions are enforced by the backend; unauthorized requests rejected | ✅ 403 matrix for all roles, escalation guards |
| Frontend navigation reflects permissions | ✅ unit test + browser (employee vs admin) |
| Authentication and authorization tests pass | ✅ 82 backend / 22 frontend |

### Phase 1 verification in Docker — 2026-11-11
Environment: Windows 11, Docker Desktop (engine 29.9.3, Compose v5.7.0, WSL2, 12 CPU, ~8 GB),
host Python 3.15.2 / Node 26.13; containers Python 3.13.18 / Node 22.

| # | Check (command) | Result |
| --- | --- | --- |
| 1 | `docker compose config --quiet` | ✅ valid; 8 services (nginx behind `proxy` profile) |
| 2 | `docker compose build` (dev) + `docker build --target prod` (both) | ✅ dev backend 546 MB, dev frontend 216 MB, prod backend 397 MB, prod frontend 308 MB |
| 3 | `docker compose down` → `docker compose up -d` (clean start) | ✅ all services up in 17 s in dependency order; `migrate` exits 0; postgres/redis/minio/backend healthy |
| 4 | PostgreSQL + pgvector (`psql`) | ✅ PostgreSQL 17.11; extensions `vector 0.8.7`, `pg_trgm 1.6` installed by migration |
| 5 | Redis (`redis-cli ping`, integration test) | ✅ Redis 7.4.12 `PONG`; set/get/delete round trip |
| 6 | MinIO / S3 (`mc ls`, integration test) | ✅ `pgsty/minio` RELEASE.2026-08-04 healthy; bucket `orbit-documents` auto-created; S3 put/get/delete round trip via boto3 |
| 7 | Celery worker | ✅ ready on `default` + `documents`; `system.ping` round trip API→Redis→worker→result |
| 8 | Alembic | ✅ `upgrade head` → `0001 (head)`; `downgrade base` + `upgrade head` round trip |
| 9 | Integration tests | ✅ container `pytest`: 31 passed, 1 skipped (Windows-only test); host `ORBIT_RUN_INTEGRATION=1 pytest`: 32 passed |
| 10 | `bash scripts/smoke-test.sh` | ✅ liveness, readiness **200**, frontend page, frontend→backend proxy |
| 11 | Frontend + backend via Docker | ✅ backend container healthy; frontend container serves Thai UI with real readiness data; `/api` proxied to the `backend` service |
| — | Nginx (`--profile proxy`) on :8080 | ✅ page 200, `/api/v1/health` 200, `nginx -t` ok, one copy of each security header |
| — | Prod images run | ✅ non-root `orbit`, healthcheck healthy, 4 uvicorn workers, standalone frontend proxy 200 |
| — | Native Windows backend (RUNBOOK option B) | ✅ with `--loop app.core.event_loop:selector_event_loop` readiness 200; without it the `windows_proactor_event_loop` warning is logged |
| — | `scripts/check.sh` | ✅ ruff, mypy (36 files), pytest 27 passed / 5 skipped (integration), alembic SQL, ESLint, tsc, Vitest 12 passed, Prettier |
| — | `npm run build` | ✅ compiled |

### Problems found during verification and fixed
1. `minio/minio` image no longer exists on Docker Hub (quay.io: 401) → digest-pinned `pgsty/minio` (ADR-013).
2. Native Windows backend could not reach PostgreSQL (`InterfaceError`, async psycopg on the Proactor loop) → selector loop factory + startup warning (ADR-014).
3. Host connections via `localhost` stalled on IPv6 (integration run 150 s) → `127.0.0.1` defaults (ADR-015); run now ~1.5 s.
4. Nginx duplicated `X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy` → upstream copies hidden.
5. Verification commands in docs used `&&`, which Windows PowerShell 5.1 rejects → one command per line.

### Phase 1 acceptance criteria (actual)
| Criterion | Status |
| --- | --- |
| Development environment starts with Docker Compose | ✅ |
| Frontend can load | ✅ (`next dev`, Docker dev, prod standalone, behind Nginx) |
| Backend can start | ✅ (Docker dev + prod, native Windows) |
| Database connection works | ✅ |
| Redis connection works | ✅ |
| MinIO can start | ✅ |
| Health endpoints work | ✅ live 200, readiness 200 with all required components ok |
| Environment variables documented | ✅ `.env.example` |
| Basic test suite runs | ✅ backend 32 (host, with integration), frontend 12 |
| README contains setup instructions | ✅ |

**Phase 1 is accepted. Phase 2 may start.**

### Earlier runs (2026-11-10, before Docker was available)
Commands actually executed (Windows 11, Python 3.15.2, Node 26.13):

| Command | Result |
| --- | --- |
| `scripts/check.sh` | ✅ all passed |
| `backend: ruff check . && ruff format --check .` | ✅ passed |
| `backend: mypy app` (strict) | ✅ no issues (35 files) |
| `backend: pytest` | ✅ 24 passed, 2 skipped (integration tests need running services) |
| `backend: alembic upgrade head --sql` | ✅ renders migration 0001 |
| `frontend: npm run lint` | ✅ passed |
| `frontend: npm run typecheck` | ✅ passed |
| `frontend: npm run test` (Vitest) | ✅ 12 passed (3 files) |
| `frontend: npm run format:check` | ✅ passed |
| `frontend: npm run build` | ✅ compiled; `/` and `/_not-found` prerendered |
| `npm audit --omit=dev` | ✅ 0 vulnerabilities (dev-only: shadcn CLI transitive advisories) |
| Manual: backend `uvicorn` + frontend `next dev` locally | ✅ `/health/live` 200 with security headers; `/api/v1/health` via Next proxy → 503 report (no infra running, as expected); UI renders status in Thai on desktop and mobile; mobile drawer works |
| Compose YAML parse (PyYAML) | ✅ 8 services, container hostnames resolved |
| `docker compose up` | ⚠️ **not executed** — Docker not installed on this machine |
| `pytest -m integration` with `ORBIT_RUN_INTEGRATION=1` | ⚠️ **not executed** — needs PostgreSQL/Redis/MinIO |

## Known Issues
1. **Host Python venv blocked by Windows Application Control** (since the 2026-11-11 restart):
   `DLL load failed ... An Application Control policy has blocked this file` for compiled wheels
   (SQLAlchemy). Not bypassed. Backend commands run in the container
   (`CHECK_BACKEND_IN_DOCKER=1 scripts/check.sh`, `docker compose exec backend …`).
2. Password-reset e-mails go through SMTP when configured (Mailpit in Docker); with
   `SMTP_HOST` empty the link is logged in development only. Choose a production SMTP
   provider at go-live (`docs/DEPLOYMENT.md`).
3. Rate limiting fails open only in development/test; production fails closed (ADR-049).
4. Object storage uses a third-party MinIO build (`pgsty/minio`, digest-pinned) — ADR-013.
5. Public readiness shows only the overall status in production (details: token or admin).
6. Users and departments are managed in the Employee Center, roles on `/settings`; other system
   settings (AI provider, SMTP) are configured through `.env` only.
7. The session gate is client-side (pages render after `/auth/me`); every API call is still
   authorised by the backend. Server-side gating can be added with `proxy.ts` later (ADR-021).
8. Next.js dev server writes `frontend/AGENTS.md`; ignored by the global git excludes.
9. The `worker` container lists `8000/tcp` (inherited `EXPOSE`); cosmetic.
10. The Docker frontend dev server (Turbopack) did not pick up host edits despite
    `WATCHPACK_POLLING`; `docker compose restart frontend` applies them (RUNBOOK §6).
11. Dashboard aggregates are computed per request without caching (fine at current scale;
    revisit with analytics in Phase 8). Dark mode is not wired (no theme provider), so only
    the light chart palette is in use.
12. E-mail is plain text and per type only (no digest, no quiet hours); failed sends are not
    retried automatically (status `FAILED`).
13. No OCR: scanned (image-only) PDFs finish `READY` with 0 characters; the UI says so.
14. Soft-deleted documents and their files are purged after 30 days (daily job, ADR-051).
15. Uploads are not scanned by an antivirus engine (type sniffing and zip checks only).
16. The Celery worker does not auto-reload; restart it after backend changes
    (`docker compose restart worker`).
17. Document search is `ILIKE` on title/description; content search arrives with RAG (Phase 7).
18. Task attachments accept the document formats only (PDF, DOCX, XLSX, TXT) — no images yet.
19. Files left behind by failed uploads or storage errors are removed by the daily orphan
    sweep after 24 hours.
20. There are no due-date reminders for tasks yet.
21. Ticket image attachments are previewed but not resized or stripped of metadata (EXIF).
22. The assistant has not been run against a live model here (no Ollama or API key on this
    machine); adapters are tested against their wire formats and the full stack against a
    scripted stub. The Anthropic refusal-fallback beta is untested against the live API.
23. Deleted chats and chats idle longer than `AI_CHAT_RETENTION_DAYS` are purged daily.
24. Analytics are computed per request (no caching or materialised views); fine at current
    scale. The AI summary has only been tested with a scripted model.
25. Small local models may call tools poorly; choose a model with tool-calling support.
26. Retrieval quality has only been checked with deterministic test embeddings and a stub; real
    relevance depends on the embedding model (recommended `bge-m3`, 1024 dimensions) and is
    unmeasured. Changing to a model with another dimension needs a migration (ADR-042).
27. No OCR: scanned PDFs are `SKIPPED` for search. Documents uploaded before Phase 7 need
    `reindex-documents` (done for the dev database).
28. `read_document` gives the model the first 12,000 characters; summaries of longer documents
    cover only the beginning (the model is told to say so).
29. The embedding provider receives document text during indexing; use a local provider if
    documents must not leave your servers.
30. The backend image now includes Pango and Thai fonts for PDF reports (larger image); rebuild
    after pulling (`docker compose up -d --build backend worker`).
31. Department analytics count tickets by the requester's current department; moving a person
    moves their past tickets in the figures.
32. The page CSP allows inline scripts (Next.js without nonces, ADR-050).
33. Not deployed to a real server yet; single-host design without high availability; production
    risks in `docs/DEPLOYMENT.md` §8.
34. No browser-driven UI tests (Playwright); UI flows were verified manually in the built-in
    browser and the API workflows by `scripts/e2e-test.sh`.
35. `e2e-test.sh` leaves closed "E2E …" tickets in the development database (tasks and
    documents are deleted).

## Next Phase
None — all planned phases are complete. Next step is go-live on a real server
(`docs/DEPLOYMENT.md`), or new features from the "Remaining" list.

## Next Command
Start the stack (one command per line in PowerShell; the smoke test via Git Bash):

```powershell
docker compose up -d
bash scripts/smoke-test.sh
```

Deploy to a server (see `docs/DEPLOYMENT.md`):

```bash
cp .env.production.example .env.production   # fill in every CHANGE_ME
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python -m app.cli create-admin you@company.com ชื่อ นามสกุล
```

## Report format (end of every phase, in Thai)
1. Completed · 2. Files Created or Modified · 3. Database Changes · 4. API Changes · 5. Tests ·
6. How to Run · 7. Known Issues · 8. Project Status · 9. Next Phase · 10. Next Command
