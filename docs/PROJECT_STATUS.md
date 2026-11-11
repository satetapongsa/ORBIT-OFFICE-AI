# AURA OFFICE AI — PROJECT STATUS

**Current Phase:** Phase 5 — Task Management & Employee Center — ✅ **COMPLETE** (verified 2026-11-11). Next: Phase 6.
**Last Updated:** 2026-11-11

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
  one account per role (`*@aura.example.com`, password `SEED_DEV_PASSWORD`).
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

## In Progress
- Nothing. Phase 5 is complete.

## Remaining
- Phases 6–9 per `docs/DEVELOPMENT_PHASES.md`.
- Role/permission editing UI and system settings (`/settings`) — Phase 8 (APIs exist).
- E-mail delivery for password-reset links (needs a mail provider/SMTP decision).

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
business-day due dates (ADR-036).

## Tests
### Phase 5 verification — 2026-11-11
| Check (command) | Result |
| --- | --- |
| `CHECK_BACKEND_IN_DOCKER=1 AURA_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
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
| `CHECK_BACKEND_IN_DOCKER=1 AURA_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
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
| `CHECK_BACKEND_IN_DOCKER=1 AURA_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
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
| `CHECK_BACKEND_IN_DOCKER=1 AURA_RUN_INTEGRATION=1 bash scripts/check.sh` | ✅ all passed |
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
| 6 | MinIO / S3 (`mc ls`, integration test) | ✅ `pgsty/minio` RELEASE.2026-08-04 healthy; bucket `aura-documents` auto-created; S3 put/get/delete round trip via boto3 |
| 7 | Celery worker | ✅ ready on `default` + `documents`; `system.ping` round trip API→Redis→worker→result |
| 8 | Alembic | ✅ `upgrade head` → `0001 (head)`; `downgrade base` + `upgrade head` round trip |
| 9 | Integration tests | ✅ container `pytest`: 31 passed, 1 skipped (Windows-only test); host `AURA_RUN_INTEGRATION=1 pytest`: 32 passed |
| 10 | `bash scripts/smoke-test.sh` | ✅ liveness, readiness **200**, frontend page, frontend→backend proxy |
| 11 | Frontend + backend via Docker | ✅ backend container healthy; frontend container serves Thai UI with real readiness data; `/api` proxied to the `backend` service |
| — | Nginx (`--profile proxy`) on :8080 | ✅ page 200, `/api/v1/health` 200, `nginx -t` ok, one copy of each security header |
| — | Prod images run | ✅ non-root `aura`, healthcheck healthy, 4 uvicorn workers, standalone frontend proxy 200 |
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
| `pytest -m integration` with `AURA_RUN_INTEGRATION=1` | ⚠️ **not executed** — needs PostgreSQL/Redis/MinIO |

## Known Issues
1. **Host Python venv blocked by Windows Application Control** (since the 2026-11-11 restart):
   `DLL load failed ... An Application Control policy has blocked this file` for compiled wheels
   (SQLAlchemy). Not bypassed. Backend commands run in the container
   (`CHECK_BACKEND_IN_DOCKER=1 scripts/check.sh`, `docker compose exec backend …`).
2. Password-reset e-mails are not delivered yet (no mail provider). In development the link is
   written to the backend log; elsewhere a warning is logged. Needs an SMTP/provider decision.
3. Login rate limiter fails open if Redis is unavailable (logged); review in Phase 9.
4. Object storage uses a third-party MinIO build (`pgsty/minio`, digest-pinned) — ADR-013.
5. Readiness endpoint is unauthenticated and lists component status; review in Phase 9.
6. User/role/department management has APIs but no admin UI yet ("ตั้งค่า" shows "เร็วๆ นี้"
   for admins); planned with Phase 5.
7. The session gate is client-side (pages render after `/auth/me`); every API call is still
   authorised by the backend. Server-side gating can be added with `proxy.ts` later (ADR-021).
8. Next.js dev server writes `frontend/AGENTS.md`; ignored by the global git excludes.
9. The `worker` container lists `8000/tcp` (inherited `EXPOSE`); cosmetic.
10. The Docker frontend dev server (Turbopack) did not pick up host edits despite
    `WATCHPACK_POLLING`; `docker compose restart frontend` applies them (RUNBOOK §6).
11. Dashboard aggregates are computed per request without caching (fine at current scale;
    revisit with analytics in Phase 8). Dark mode is not wired (no theme provider), so only
    the light chart palette is in use.
12. Notifications are in-app only (no e-mail) and have no per-user preferences yet (Phase 8).
13. No OCR: scanned (image-only) PDFs finish `READY` with 0 characters; the UI says so.
14. Objects of soft-deleted documents stay in storage; a purge job is planned for Phase 9.
15. Uploads are not scanned by an antivirus engine (type sniffing and zip checks only).
16. The Celery worker does not auto-reload; restart it after backend changes
    (`docker compose restart worker`).
17. Document search is `ILIKE` on title/description; content search arrives with RAG (Phase 7).
18. Task attachments accept the document formats only (PDF, DOCX, XLSX, TXT) — no images yet.
19. Objects of removed task attachments are deleted after the DB commit; a storage failure at
    that moment leaves an orphaned object (logged). Purge job: Phase 9.
20. Notifications for tasks are in-app only; there are no due-date reminders yet (Phase 8).
21. Role/permission editing and `/settings` are not built yet (Phase 8); roles are assigned
    from the Employee Center.

## Next Phase
**Phase 6 — AI Assistant & Tool Calling**: see `docs/DEVELOPMENT_PHASES.md`.

## Next Command
Start the stack (one command per line in PowerShell; the smoke test via Git Bash):

```powershell
docker compose up -d
bash scripts/smoke-test.sh
```

Then start the next session with:

```
Continue AURA OFFICE AI: read docs/PROJECT_STATUS.md and docs/DEVELOPMENT_PHASES.md, then execute PHASE 6 — AI ASSISTANT & TOOL CALLING as defined in docs/DEVELOPMENT_PHASES.md.
```

## Report format (end of every phase, in Thai)
1. Completed · 2. Files Created or Modified · 3. Database Changes · 4. API Changes · 5. Tests ·
6. How to Run · 7. Known Issues · 8. Project Status · 9. Next Phase · 10. Next Command
