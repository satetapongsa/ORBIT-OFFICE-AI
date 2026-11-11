# AURA OFFICE AI — Development Phases

Phases are executed **in order**. A phase starts only when the previous phase's
acceptance criteria are met, or the unmet criteria are explicitly recorded in
`PROJECT_STATUS.md`. Each phase ends by updating `PROJECT_STATUS.md` and the
docs affected by the change.

Status legend: ✅ done · 🟡 done with open items · ⬜ not started

---

## Phase 0 — Project initialization & architecture ✅

Define architecture, database design, API conventions, security principles and
the continuity documentation.

Acceptance criteria
- [x] Architecture documented (`ARCHITECTURE.md`)
- [x] All phases documented (this file)
- [x] Project structure defined
- [x] Future development instructions preserved (`PROJECT_STATUS.md`, `RUNBOOK.md`, `DECISIONS.md`)

## Phase 1 — System foundation & project scaffold ✅

Frontend and backend scaffolds, PostgreSQL + pgvector, Redis, MinIO, Docker
Compose, environment configuration, DB connection, Alembic, health endpoints,
application shell, logging, initial tests.

Acceptance criteria (verified in Docker on 2026-11-11 — see `PROJECT_STATUS.md`)
- [x] Development environment starts with Docker Compose
- [x] Frontend loads
- [x] Backend starts
- [x] Database connection works
- [x] Redis connection works
- [x] MinIO starts
- [x] Health endpoints work
- [x] Environment variables documented (`.env.example`)
- [x] Basic test suite runs
- [x] README contains setup instructions

## Phase 2 — Authentication & authorization ✅

Login, logout, current user, session lifecycle (access JWT + rotating refresh
token in HttpOnly cookies, CSRF double-submit), Argon2id hashing, user
management APIs, departments, roles, permissions, role assignment, backend
authorization dependencies, document ACL foundation (`document_acl` table +
access predicate), audit logs, secure development seed data, login UI,
permission-aware navigation.

Acceptance criteria (verified 2026-11-11 — see `PROJECT_STATUS.md`)
- [x] A user can log in and log out.
- [x] Unauthenticated users cannot access protected APIs.
- [x] Role permissions are enforced by the backend; unauthorized requests are rejected.
- [x] Frontend navigation reflects permissions.
- [x] Authentication and authorization tests pass.

Deferred by design: the user/role administration **UI** ships with the Employee Center
(Phase 5); the APIs exist now. E-mail delivery of reset links needs a mail provider.

## Phase 3 — Dashboard & application UI ✅

Main layout, sidebar, header, user profile menu, dashboard with summary cards,
charts, recent activity, notification preview; responsive navigation; loading,
error and empty states; role-aware menus. Dashboard metrics from real APIs,
scoped to the user's permissions.

Delivered: `GET /dashboard/summary` (permission-gated sections), the `notifications` table +
inbox API fed by real account/security events (ADR-023), dashboard page, header notification
bell, `/notifications` page, `/` → `/dashboard`, system status moved to `/system-status`.

Acceptance criteria (verified 2026-11-11 — see `PROJECT_STATUS.md`)
- [x] Authenticated users can access the dashboard.
- [x] Dashboard metrics are returned by the backend.
- [x] Users see only authorized information.
- [x] Navigation works; responsive layouts work.

## Phase 4 — Document Center ✅

Upload, download, listing, search, filtering, categories, metadata, versions,
ACL management UI, MinIO storage, file validation (type sniffing, size),
asynchronous text extraction (PDF, DOCX, XLSX, TXT), processing status,
document audit history.

Delivered: migration `0004`, `/documents` API (+ `/directory/users` for sharing pickers),
Celery `documents.extract_text`, `/documents` and `/documents/[id]` pages, dashboard
"recent documents" card (ADR-028…032).

Acceptance criteria (verified 2026-11-11 — see `PROJECT_STATUS.md`)
- [x] Users can upload supported documents; files are stored in MinIO; metadata in PostgreSQL.
- [x] Unauthorized users cannot download protected documents.
- [x] Document processing status is visible.
- [x] Tests cover upload, access control and processing errors.

## Phase 5 — Task management & Employee Center ✅

Tasks (create, assign, status, due dates, priority, comments, attachments,
history, search/filter); employee directory, department views, profiles,
role-aware access to sensitive HR data.

Delivered: migration `0005`, `/tasks` API (visibility predicate + capabilities, ADR-033),
`/employees` API with a separate audited HR record (ADR-034), `/tasks`, `/tasks/[id]`,
`/employees`, `/employees/[id]` pages, account administration (create/edit/roles/suspend)
and department management from the Employee Center (ADR-035), dashboard "งานของฉัน" card,
`TASK` notifications.

Acceptance criteria (verified 2026-11-11 — see `PROJECT_STATUS.md`)
- [x] Employees see their permitted tasks; managers manage authorized team tasks.
- [x] Task changes persist; permission boundaries enforced.
- [x] Employee information protected.
- [x] Tests cover task and employee permissions.

Deferred: role/permission editing UI and system settings (`/settings`) → Phase 8.

## Phase 6 — AI assistant & tool calling ✅

AI provider abstraction (OpenAI-compatible + Anthropic adapters), backend AI
service, chat API (streaming where supported), chat sessions/history, chat UI,
error handling, tool registry, controlled tool calling, proposed-action and
user-confirmation workflow. Initial tools: `get_my_tasks`, `get_task_details`,
`create_task`, `update_task_status`, `get_my_tickets`, `create_ticket` (ticket
tools only once Phase 8 ticket services exist, or ship a minimal ticket service
here — decide and record in `DECISIONS.md`).

Delivered: migration `0006`, provider adapters (official `anthropic` SDK; OpenAI-compatible
over HTTP), `/ai` API with server-sent-event streaming, tool registry + confirmation flow,
`/assistant` page (ADR-037…040). Ticket tools move to Phase 8 with the ticket service
(ADR-039).

Acceptance criteria (verified 2026-11-12 — see `PROJECT_STATUS.md`)
- [x] Chat requests reach the backend; backend talks to the configured provider.
- [x] Chat history persisted.
- [x] AI can call permitted tools; tool permissions enforced; mutating actions need confirmation.
- [x] Provider errors handled safely; AI tests pass.

## Phase 7 — RAG knowledge base ✅

Ingestion pipeline (extraction → cleaning → chunking → embeddings → pgvector),
semantic retrieval with metadata and **permission filtering in SQL**, grounded
answers with citations, insufficient-evidence handling, document summarization.

Delivered: migration `0007` (`document_chunks` with `vector(1024)`, version index status,
chat citations), chunking + embedding pipeline in the worker (keyword index without an
embedding provider), hybrid retrieval with the ACL in SQL, `GET /documents/search`,
assistant tools `search_documents` / `read_document` with `[n]` citations, content search in
the Document Center, "สรุปด้วยผู้ช่วย AI", `reindex-documents` CLI (ADR-041…043).

Acceptance criteria (verified 2026-11-12 — see `PROJECT_STATUS.md`)
- [x] Uploaded documents can be indexed.
- [x] Semantic search returns relevant authorized documents.
- [x] Answers include source references; insufficient evidence reported.
- [x] Unauthorized chunks are never passed to the LLM; tests verify cross-permission isolation.

## Phase 8 — Helpdesk, notifications & analytics ⬜

IT tickets (create, assign, status, public/internal comments, history),
task/ticket/document notifications on top of the Phase 3 inbox (preferences, e-mail), analytics APIs, reports, PDF and Excel
export, AI report summaries.

Acceptance criteria
- Employees submit tickets; IT Support manages authorized tickets.
- Notifications persisted.
- Reports use real data and respect permissions; export works.
- Tests cover the complete workflows.

## Phase 9 — Security, testing & deployment ⬜

Backend, frontend, integration and end-to-end tests; authentication,
authorization, ACL and RAG-isolation reviews; upload security review; input
validation; rate limiting; CSRF/CORS review; error-handling and logging review;
secret management; database backups; production deployment configuration;
HTTPS; production documentation and known-risk disclosure.

Acceptance criteria
- Critical workflows pass tests.
- No known cross-permission data leakage in the test suite.
- Deployment, environment configuration, backup and recovery documented.
- Known limitations disclosed.
