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

## Phase 1 — System foundation & project scaffold 🟡

Frontend and backend scaffolds, PostgreSQL + pgvector, Redis, MinIO, Docker
Compose, environment configuration, DB connection, Alembic, health endpoints,
application shell, logging, initial tests.

Acceptance criteria
- [ ] Development environment starts with Docker Compose — *written, not yet run (no Docker on the build machine)*
- [x] Frontend loads
- [x] Backend starts
- [ ] Database connection works — *implemented + integration test written; needs a running PostgreSQL*
- [ ] Redis connection works — *implemented + checked by readiness; needs a running Redis*
- [ ] MinIO starts — *Compose service written; needs Docker*
- [x] Health endpoints work
- [x] Environment variables documented (`.env.example`)
- [x] Basic test suite runs
- [x] README contains setup instructions

## Phase 2 — Authentication & authorization ⬜

Login, logout, current user, session lifecycle (access JWT + rotating refresh
token in HttpOnly cookies, CSRF double-submit), Argon2id hashing, user
management APIs, departments, roles, permissions, role assignment, backend
authorization dependencies, document ACL foundation (`document_acl` table +
access predicate), audit logs, secure development seed data, login UI,
permission-aware navigation.

Acceptance criteria
- A user can log in and log out.
- Unauthenticated users cannot access protected APIs.
- Role permissions are enforced by the backend; unauthorized requests are rejected.
- Frontend navigation reflects permissions.
- Authentication and authorization tests pass.

## Phase 3 — Dashboard & application UI ⬜

Main layout, sidebar, header, user profile menu, dashboard with summary cards,
charts, recent activity, notification preview; responsive navigation; loading,
error and empty states; role-aware menus. Dashboard metrics from real APIs,
scoped to the user's permissions.

Acceptance criteria
- Authenticated users can access the dashboard.
- Dashboard metrics are returned by the backend.
- Users see only authorized information.
- Navigation works; responsive layouts work.

## Phase 4 — Document Center ⬜

Upload, download, listing, search, filtering, categories, metadata, versions,
ACL management UI, MinIO storage, file validation (type sniffing, size),
asynchronous text extraction (PDF, DOCX, XLSX, TXT), processing status,
document audit history.

Acceptance criteria
- Users can upload supported documents; files are stored in MinIO; metadata in PostgreSQL.
- Unauthorized users cannot download protected documents.
- Document processing status is visible.
- Tests cover upload, access control and processing errors.

## Phase 5 — Task management & Employee Center ⬜

Tasks (create, assign, status, due dates, priority, comments, attachments,
history, search/filter); employee directory, department views, profiles,
role-aware access to sensitive HR data.

Acceptance criteria
- Employees see their permitted tasks; managers manage authorized team tasks.
- Task changes persist; permission boundaries enforced.
- Employee information protected.
- Tests cover task and employee permissions.

## Phase 6 — AI assistant & tool calling ⬜

AI provider abstraction (OpenAI-compatible + Anthropic adapters), backend AI
service, chat API (streaming where supported), chat sessions/history, chat UI,
error handling, tool registry, controlled tool calling, proposed-action and
user-confirmation workflow. Initial tools: `get_my_tasks`, `get_task_details`,
`create_task`, `update_task_status`, `get_my_tickets`, `create_ticket` (ticket
tools only once Phase 8 ticket services exist, or ship a minimal ticket service
here — decide and record in `DECISIONS.md`).

Acceptance criteria
- Chat requests reach the backend; backend talks to the configured provider.
- Chat history persisted.
- AI can call permitted tools; tool permissions enforced; mutating actions need confirmation.
- Provider errors handled safely; AI tests pass.

## Phase 7 — RAG knowledge base ⬜

Ingestion pipeline (extraction → cleaning → chunking → embeddings → pgvector),
semantic retrieval with metadata and **permission filtering in SQL**, grounded
answers with citations, insufficient-evidence handling, document summarization.

Acceptance criteria
- Uploaded documents can be indexed.
- Semantic search returns relevant authorized documents.
- Answers include source references; insufficient evidence reported.
- Unauthorized chunks are never passed to the LLM; tests verify cross-permission isolation.

## Phase 8 — Helpdesk, notifications & analytics ⬜

IT tickets (create, assign, status, public/internal comments, history),
notification system with read status, analytics APIs, reports, PDF and Excel
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
