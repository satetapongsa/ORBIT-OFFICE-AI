# ORBIT OFFICE AI — Architecture Decision Records

Format: context → decision → consequences. Newest at the bottom. Superseded
decisions are kept and marked.

---

## ADR-001 — Monorepo with separate frontend and backend (2026-11-10)
**Context.** One team, one product, tightly coupled API contracts.
**Decision.** Single repository: `frontend/` (Next.js), `backend/` (FastAPI),
`infra/`, `docs/`, `scripts/`, one `docker-compose.yml`.
**Consequences.** Contract changes land in one commit; each app keeps its own
tooling (npm / pip).

## ADR-002 — Same-origin API through a proxy (2026-11-10)
**Context.** Auth uses HttpOnly cookies; cross-origin cookies complicate
`SameSite`, CSRF and CORS.
**Decision.** The browser calls `/api/v1/*` on its own origin. Dev: Next.js
`rewrites` → backend. Prod: Nginx routes `/api/` → backend, `/` → Next.js.
**Consequences.** No CORS needed for the main app (`CORS_ORIGINS` empty by
default). `BACKEND_INTERNAL_URL` is baked in at `next build` for standalone
output; production relies on Nginx routing instead.

## ADR-003 — psycopg 3 for both async and sync database access (2026-11-10)
**Context.** FastAPI is async; Alembic and Celery are sync.
**Decision.** One driver, `postgresql+psycopg://`, with SQLAlchemy 2.x
`create_async_engine` for the API and `create_engine` for Alembic/Celery.
**Consequences.** One DSN, one dependency, no asyncpg/psycopg2 split.

## ADR-004 — Enums as VARCHAR + CHECK constraints (2026-11-10)
**Context.** Native PostgreSQL enums are painful to alter in migrations.
**Decision.** Store enum values as `VARCHAR` with `CHECK` constraints; Python
`StrEnum` on the application side.
**Consequences.** Adding a value = one migration altering the constraint.

## ADR-005 — Permission-based RBAC with roles as data (2026-11-10)
**Context.** New roles must be addable without code changes.
**Decision.** Permissions (`domain:action`) are a code-defined catalogue synced
to the DB; roles are DB rows mapping to permissions; backend guards check
permissions, never role names. Permissions are loaded per request, not embedded
in JWTs.
**Consequences.** Revocation is immediate; one extra cached query per request.

## ADR-006 — Document ACL evaluated at query time, not copied into chunks (2026-11-10)
**Context.** RAG must never pass unauthorized chunks to the LLM, and permission
changes must take effect immediately.
**Decision.** `document_chunks` holds `document_id` only; retrieval joins
`documents` + `document_acl` using the single shared access predicate.
**Consequences.** Slightly heavier vector queries (mitigated with indexes and
pre-filtered candidate sets); no stale-permission window.

## ADR-007 — Provider-independent AI layer; chat and embeddings configured separately (2026-11-10)
**Context.** The company may use local models (no paid service required for
development) or a commercial provider later. Anthropic offers chat models but no
embeddings endpoint.
**Decision.** `AI_CHAT_*` and `AI_EMBEDDING_*` settings are independent.
Providers: `disabled` (default), `openai_compatible` (Ollama, vLLM, OpenAI,
gateways), `anthropic` (chat only; default model `claude-opus-5-5`, via the
official Anthropic SDK in Phase 6). Recommended local default: Ollama with a
multilingual embedding model (`bge-m3`, 1024 dimensions) for Thai text.
**Consequences.** The embedding dimension is fixed by the Phase 7 migration;
changing the embedding model requires a re-index migration.

## ADR-008 — Health endpoints: liveness vs readiness (2026-11-10)
**Decision.** `/api/v1/health/live` (no dependencies) for container liveness;
`/api/v1/health` checks PostgreSQL (+ `vector` extension), Redis and object
storage in parallel with a timeout, returns `503` if a required component fails,
and reports AI configuration as optional (`configured` / `not_configured`)
**without contacting the provider**. Error details are logged, not returned.
**Consequences.** Readiness is safe to poll from the UI; AI connectivity checks
arrive with the Phase 6 adapters.

## ADR-009 — MinIO pinned and overridable; storage code is S3-generic (2026-11-10)
**Context.** MinIO changed how its community edition is distributed in 2025;
future image tags may not be published.
**Decision.** Compose pins a known community release and allows
`MINIO_IMAGE` override. The backend uses plain S3 APIs via `boto3`
(path-style addressing), so any S3-compatible store works.
**Consequences.** Swapping MinIO for another S3-compatible server or a cloud
bucket is configuration only.
**Update 2026-11-11.** The pinned `minio/minio` tag (and the whole Docker Hub
repository) is no longer available — see ADR-013.

## ADR-010 — Frontend stack details (2026-11-10)
**Decision.** Next.js 16 (App Router, Turbopack, `cacheComponents` enabled as
generated), React 19, Tailwind CSS 4, shadcn/ui on Radix (`radix-nova` style),
TanStack Query for client server-state, Zod 4 for response validation,
Vitest + Testing Library for tests, IBM Plex Sans Thai as the UI font.
**Consequences.** Next.js 16 differs from older versions; consult
`frontend/node_modules/next/dist/docs/` before using unfamiliar APIs.

## ADR-011 — Python versions (2026-11-10)
**Decision.** Code targets Python ≥ 3.12. Container images use Python 3.13
for wheel availability; local development has been verified on Python 3.15.
**Consequences.** Avoid syntax newer than 3.12.

## ADR-012 — Starlette TestClient uses httpx2 (2026-11-10)
**Context.** Starlette 1.x deprecates `httpx` for its test client.
**Decision.** Dev dependency `httpx2` instead of `httpx`.

## ADR-013 — Object storage image: digest-pinned `pgsty/minio` (2026-11-11)
**Context.** `docker pull minio/minio:…` fails ("repository does not exist");
`quay.io/minio/minio` requires authentication. Upstream no longer publishes
community images. The specification requires MinIO.
**Decision.** Use the community MinIO build maintained by the Pigsty project,
`pgsty/minio` (`RELEASE.2026-08-04T00-00-00Z`, source github.com/pgsty/minio,
Red Hat UBI 9 micro base), **pinned by digest**
`sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372`.
Chosen by the project owner over building from source or SeaweedFS.
**Consequences.** Same MinIO server, console, `mc` and configuration; the
healthcheck (`mc ready local`) is unchanged. It is a third-party build: review
upstream changes before bumping the digest; for production prefer a managed S3
service or an image built in-house from official source (Phase 9).

## ADR-014 — Selector event loop for native Windows development (2026-11-11)
**Context.** psycopg 3 cannot run in async mode on Windows' default
`ProactorEventLoop` (`InterfaceError`). Containers (Linux) are unaffected.
**Decision.** `app.core.event_loop.selector_event_loop` is a loop factory for
`uvicorn --loop` and anyio's `loop_factory` (used by the integration tests).
The app logs `windows_proactor_event_loop` at startup when the unsupported loop
is detected.
**Consequences.** Native Windows runs need the extra `--loop` argument; Docker
images keep uvicorn's default loop (uvloop).

## ADR-015 — `127.0.0.1` instead of `localhost` for host-side defaults (2026-11-11)
**Context.** On Windows, `localhost` resolves to `::1` first; Compose publishes
ports on `127.0.0.1` only, so host processes stalled on IPv6 attempts
(integration run: 150 s vs 1.6 s).
**Decision.** `.env.example`, settings defaults, the smoke test and the Next.js
proxy default use `127.0.0.1`. Container-to-container URLs keep service names.
The Next.js dev server must then trust that origin: `allowedDevOrigins: ["127.0.0.1"]`
(otherwise it blocks its own JS/HMR resources and the app never hydrates).

## ADR-016 — Session model: short JWT + rotating opaque refresh token per "family" (2026-11-11)
**Context.** Browser sessions must be revocable immediately (logout, deactivation,
password change, stolen refresh token) without putting long-lived tokens in JavaScript.
**Decision.** 15-minute HS256 access JWT whose `sid` is the login's *family id*; refresh
tokens are opaque, stored hashed, one `user_sessions` row per issued token, rotated on
every use. Every request checks that the family is still active and that the token was
issued after the last password change. Re-use of a rotated token revokes the family,
except within a 10-second grace window (parallel tabs) where it is only rejected.
**Consequences.** One indexed `EXISTS` query per request; logout and revocation are
instant; two tabs refreshing together do not log the user out.

## ADR-017 — CSRF: double-submit cookie, Bearer exempt (2026-11-11)
**Decision.** `orbit_csrf` (readable, `SameSite=Lax`) must equal `X-CSRF-Token` on
cookie-authenticated unsafe requests, including refresh/logout. Requests authenticated
with `Authorization: Bearer` carry no ambient credentials and are exempt. Login and
password-reset endpoints are unauthenticated and exempt.
**Consequences.** The frontend API client echoes the cookie automatically; non-browser
clients use Bearer tokens.

## ADR-018 — Privilege escalation rule: you can only grant what you hold (2026-11-11)
**Decision.** Creating/editing roles and assigning/removing roles both require the
actor to hold every affected permission. `ADMIN`'s permission set is locked to the code
catalogue; the last active admin cannot be demoted or deactivated.
**Consequences.** Delegated administrators (e.g. HR with `users:create`) cannot create
or promote accounts above their own privileges.

## ADR-019 — Document ACL foundation lands in Phase 2 (2026-11-11)
**Context.** The ACL predicate must exist before any document feature uses it.
**Decision.** Migration `0002` creates the core `documents` row and `document_acl`;
`repositories/document_access.accessible_documents_condition` is the single SQL
predicate, tested against PostgreSQL. Phase 4 adds versions, storage and categories.
**Consequences.** Phase 4/7 code must import this predicate instead of re-implementing rules.

## ADR-020 — Test database and test isolation (2026-11-11)
**Decision.** Tests use a separate database (`orbit_office_test`, or `ORBIT_TEST_DATABASE_URL`)
created and migrated automatically by `tests/conftest.py`; tables are truncated and RBAC
re-synced before every DB test. The fixture refuses database names without `test`.
`DATABASE_USE_NULL_POOL=true` avoids sharing pooled connections between the event loops of
separate TestClients. DB tests are skipped (with a reason) only when PostgreSQL is unreachable.
**Consequences.** Running the suite never touches development data; `scripts/check.sh`
can run the backend part inside the container (`CHECK_BACKEND_IN_DOCKER=1`).

## ADR-021 — Client-side session gate (2026-11-11)
**Decision.** Pages under `app/(app)` render only after `GET /auth/me` succeeds
(`AuthGate`); unauthenticated users are redirected to `/login?next=…` (internal paths
only). The API client refreshes once on 401 (single-flight) and retries; if that fails the
gate redirects. `export const instant = false` on `(app)/layout.tsx` opts the gated segment
out of Next.js instant-navigation validation. Hiding UI is cosmetic — the backend enforces
every permission.
**Consequences.** No server-side session reads in Next.js; a server-rendered gate can be
added later (Next.js `proxy.ts`) if needed.

## ADR-022 — Test/dev e-mail domains (2026-11-11)
**Context.** `email-validator` rejects special-use domains such as `.local` and `.test`.
**Decision.** Development seed accounts use `@orbit.example.com`, tests use `@example.com`
(RFC 2606 documentation domains, accepted by the validator, never deliverable).

## ADR-023 — Notification inbox ships in Phase 3 (2026-11-11)
**Context.** The Phase 3 dashboard needs a notification preview from real data; the plan put
notifications in Phase 8.
**Decision.** Migration `0003` creates `notifications`; `app/services/notifications.py` adds
entries in the same transaction as the event (welcome on account creation, password
changed/reset, suspicious refresh-token reuse, roles changed, account updated by someone
else, account re-activated). The API (`/notifications`) is owner-only — no permission code,
every query filters by the caller, other users' rows answer `404`. `link_url` must be a
relative in-app path (DB `CHECK` + service + client `safeRedirectPath`). Reading a
notification is not audited (noise); the events that create them already are.
**Consequences.** Phase 8 adds module notification types (a migration extends the `type`
CHECK), preferences and e-mail delivery on top of this table.

## ADR-024 — One permission-gated dashboard summary endpoint (2026-11-11)
**Decision.** `GET /dashboard/summary` returns personal sections for every user and optional
sections (`documents`, `organization`, `security`) only when the caller holds the permission
guarding the same detail data (`documents:read` via `accessible_documents_condition`,
`users:read`, `audit:read`); otherwise they are `null`. Activity items are reduced to
action/time/actor/entity type. One request keeps the page fast and the rules in one service
(`app/services/dashboard.py`).
**Consequences.** Later phases add `tasks`/`tickets` sections the same way (permission →
section). No caching yet; every aggregate is an indexed count.

## ADR-025 — Business time zone for daily statistics (2026-11-11)
**Decision.** `APP_TIMEZONE` (IANA, default `Asia/Bangkok`, validated at startup) defines the
calendar day for dashboard series; PostgreSQL groups with `timezone(APP_TIMEZONE, occurred_at)`
and Python fills missing days with zero. `tzdata` is a dependency so `zoneinfo` works on
Windows and slim images. Timestamps stay UTC in the database and API.

## ADR-026 — Charts without a chart library (2026-11-11)
**Decision.** Dashboard charts are small HTML/CSS components (`components/charts/column-chart.tsx`):
columns ≤ 24 px with 4 px rounded data ends, recessive gridlines at whole-number ticks, a
hover/focus tooltip per column, a legend for ≥ 2 series, an accessible label per column and a
"ดูเป็นตาราง" table view. Series colours (`--chart-1` blue `#2a78d6`, `--chart-2` orange
`#eb6834`) passed a colour-vision-deficiency palette check (adjacent ΔE 24.7, protan).
**Consequences.** No extra dependency and testable in jsdom; richer analytics (Phase 8) may
revisit this.

## ADR-027 — Dashboard is the home page (2026-11-11)
**Decision.** `/` redirects (307, `next.config.ts`) to `/dashboard`; login falls back to
`HOME_PATH`; system status moved to `/system-status`. Every page under `app/(app)` also exports
`instant = false` (the layout-level flag alone did not silence Next.js instant-navigation
validation for new page segments).

## ADR-028 — Document capabilities = ACL level + permission (2026-11-11)
**Decision.** The effective access level (VIEW/EDIT/MANAGE) comes only from the single
predicate; permission codes add capabilities on top (table in `SECURITY.md` §3). Deletion
needs MANAGE **and** `documents:delete` (only ADMIN by default), so owners archive instead of
deleting. `documents:manage_access` lets a records officer manage sharing on any document
they can see. Unknown and inaccessible documents both answer `404`.
**Consequences.** The UI shows only actions in `capabilities`; the backend re-checks each one.

## ADR-029 — Upload pipeline (2026-11-11)
**Decision.** Size is limited at Nginx, the Next.js dev/standalone proxy
(`proxyClientMaxBodySize`), an ASGI `Content-Length` guard and the service (measured while
hashing). Type is decided by content sniffing that must agree with the extension. The object
is written to storage under a server-generated key first, then the DB rows and audit entry
are committed; a failed commit deletes the object. Extraction is enqueued after commit; if
the broker is down the version stays `PENDING` and can be reprocessed. Downloads stream
through the API after the ACL check (the bucket stays private; no presigned URLs).
**Consequences.** Objects of soft-deleted documents remain until a purge job (Phase 9).

## ADR-030 — Text extraction in the worker (2026-11-11)
**Decision.** `documents.extract_text` (queue `documents`, 180 s soft limit) uses pypdf,
python-docx and openpyxl (+ defusedxml) with page/cell/character limits; TXT accepts UTF-8,
UTF-16 (BOM) and Windows-874/TIS-620. Text is cleaned and stored in `document_version_texts`.
Expected failures become `FAILED` with a Thai reason and a `DOCUMENT` notification to the
uploader; the task is idempotent (READY is skipped unless forced). Scanned PDFs finish READY
with 0 characters — no OCR yet.
**Consequences.** Phase 7 chunks/embeds `document_version_texts` of current READY versions.

## ADR-031 — Directory lookup for sharing (2026-11-11)
**Decision.** `GET /directory/users` (`employees:read_directory`, every employee) returns only
id, display name, job title and department of active users, so employees can share documents
without `users:read`. The Employee Center (Phase 5) builds on it. Role grants are offered only
to users with `roles:read`.

## ADR-032 — Dynamic document route (2026-11-11)
**Decision.** `/documents/[id]/page.tsx` awaits `params` on the server and passes the id to
the client view; `loading.tsx` provides the static shell (partial prerender `◐`). Calling
`useParams` in a client component without that shell failed `next build` with a
"client rendering outside a Suspense boundary" error under Cache Components.

## ADR-033 — Task visibility predicate and capabilities (2026-11-11)
**Decision.** Like documents (ADR-006/028), task visibility is one SQL predicate
(`repositories/task_access.visible_tasks_condition`): `tasks:manage_all`, or own/assigned
(`tasks:read_own`), or same department (`tasks:read_department`/`manage_department`). A task
belongs to a department (default: the creator's), which is what department managers manage.
Capabilities (edit, status, cancel, assign, delete, attach) are computed per task and returned
to the UI; the API enforces them. Invisible tasks answer `404`. Assignees must be in the
task's department unless the actor holds `tasks:manage_all`, and without `tasks:assign` a user
can only assign themself (an empty assignee list means "me").
**Why.** One rule for lists, details, the dashboard and later RAG/AI tools; a manager cannot
reach into other teams, and employees can still track personal work.

## ADR-034 — HR data in its own table and endpoint (2026-11-11)
**Decision.** Sensitive HR fields live in `employee_hr_profiles` and are served only by
`GET/PUT /employees/{id}/hr`; directory/profile responses never contain them. The employee
can read their own record; others need `employees:read_sensitive`, and each such read is
audit-logged. Writes need `employees:manage` + `employees:read_sensitive`; the audit log
keeps changed field names only. Only the last 4 digits of the national ID are stored. The UI
fetches someone else's record only after an explicit click.
**Why.** Makes accidental exposure (e.g. a new list query) structurally impossible and keeps
every access to personal data traceable.

## ADR-035 — Account administration inside the Employee Center (2026-11-11)
**Decision.** Creating people, editing account fields, assigning roles and suspending
accounts happen on the Employee Center pages, calling the existing `/users` API (with its
escalation and last-admin guards); department create/edit (incl. choosing the manager from
department members) is on the "แผนก" tab. Role/permission editing and system settings stay
for Phase 8 (`/settings` remains "เร็วๆ นี้").
**Why.** HR works with people, not raw user records; reusing `/users` avoids a second set of
rules for the same data.

## ADR-036 — Shared upload helpers and business-day due dates (2026-11-11)
**Decision.** Upload handling (size while hashing, sniffing, store-then-commit, cleanup) moved
to `app/services/uploads.py` and is shared by documents and task attachments; the size
middleware now covers `/documents` and `/tasks`. Due dates are chosen as a calendar day in the
UI and sent as the end of that day in Bangkok (`23:59+07:00`); the API rejects timestamps
without a time zone.
**Why.** One audited pipeline for every file; "due 30 Nov" means the whole business day,
independent of the browser's time zone.

## ADR-037 — Provider adapters (2026-11-12)
**Decision.** `app/services/ai/providers` exposes one neutral streaming interface. The
Anthropic adapter uses the official `anthropic` SDK (async `messages.stream`), sends no sampling
parameters (current Claude models reject them) and leaves thinking at the model default; on
models that support it, `AI_CHAT_REFUSAL_FALLBACK` enables server-side refusal fallbacks
(beta `server-side-fallback-2026-07-01`, `fallbacks: "default"`). Tools stream their input
eagerly and are validated by the chat service. The provider's own assistant content is stored
(`provider_payload`) and replayed unchanged to the same model, never edited. The
OpenAI-compatible adapter (Ollama, vLLM, LM Studio, OpenAI, gateways) speaks plain HTTP via
`httpx2` and assembles streamed tool-call fragments. Errors become Thai `ProviderError`s
without provider bodies.
**Why.** Local/free models and Claude behind one interface; replaying exactly what the
provider returned keeps multi-turn tool use valid.

## ADR-038 — Tools run as the user; changes need confirmation (2026-11-12)
**Decision.** A fixed registry of tools calls the existing services with the signed-in user,
so visibility and capabilities are the API's own. Read-only tools return data; mutating tools
only create `ai_action_requests` (`PENDING`, 15-minute TTL) with a Thai summary. Confirming
re-checks permissions, marks the action `EXECUTED` in the same transaction as the change and
appends a `system` note to the chat; rejecting appends a note too. History is append-only.
**Why.** The model can never act beyond the user, nothing changes without an explicit click,
and the model learns outcomes without rewriting earlier turns.

## ADR-039 — Ticket tools wait for the ticket service (2026-11-12)
**Decision.** `get_my_tickets` / `create_ticket` are not shipped in Phase 6; they are added in
Phase 8 together with the helpdesk tables and services.
**Why.** A minimal ticket service now would be replaced in Phase 8 and would need its own
permissions, UI and tests twice.

## ADR-040 — Streaming with server-sent events over POST (2026-11-12)
**Decision.** `POST /ai/sessions/{id}/messages` returns `text/event-stream` (`start`, `delta`,
`tool`, `action`, `done`, `error`); the browser reads it with `fetch` (CSRF header and
refresh-retry via `apiStream`). Checks that can fail (provider, ownership, rate limit) run
before the stream starts and return the normal JSON error envelope. The stream uses its own
database session. Responses carry `Cache-Control: no-store, no-transform` and
`X-Accel-Buffering: no` — without `no-transform` the Next.js proxy gzip-compressed the stream
and delivered it in one piece.
**Why.** `EventSource` cannot POST or send CSRF headers; SSE is simple and proxy-friendly.

## ADR-041 — Retrieval: ACL in SQL, current version only, hybrid ranking (2026-11-12)
**Decision.** Chunks carry no ACL copy. Every retrieval query joins `documents` with
`accessible_documents_condition` and `chunk.version = documents.current_version_id` in the
same statement that ranks passages. Ranking is hybrid: pgvector cosine similarity (HNSW with
`iterative_scan = relaxed_order`, results below 0.25 dropped) fused with pg_trgm word
similarity by reciprocal rank (k = 60). Without an embedding provider, or when the query
cannot be embedded, keyword search alone answers (`mode: keyword`, `degraded` flag). Older
versions' chunks are deleted when a newer version is indexed.
**Why.** Permission changes apply instantly and unauthorised text is never even selected;
keyword search keeps the feature useful (and Thai-friendly) on machines without an embedding
model.

## ADR-042 — Fixed embedding dimension and re-indexing (2026-11-12)
**Decision.** The vector column is `vector(1024)` (e.g. `bge-m3`); settings refuse another
`AI_EMBEDDING_DIMENSIONS`. Each chunk stores `embedding_model` and queries only use vectors of
the configured model. `python -m app.cli reindex-documents [--all]` queues re-indexing (after
enabling or changing the embedding provider). Indexing runs in the worker right after text
extraction; an embedding failure keeps the chunks (keyword search) and marks the version
`FAILED`.
**Why.** pgvector indexes need a fixed dimension; mixing models in one space would rank
nonsense.

## ADR-043 — RAG through tools, with citations (2026-11-12)
**Decision.** The assistant reaches documents only through `search_documents` and
`read_document` (12,000 characters). Passages get turn-scoped source numbers; the final answer
must cite them as `[n]`, and only cited sources are stored and shown under the answer. An
empty search returns an explicit "no evidence" instruction.
**Why.** The model decides when knowledge is needed, while every passage still comes through
the permission-filtered path and stays attributable.

## ADR-044 — Helpdesk tickets: visibility, statuses and internal notes (2026-11-12)
**Decision.** Tickets get a readable number from a database sequence (`IT-<year>-<000001>`).
One predicate (`visible_tickets_condition`) decides visibility: `tickets:read_all` sees every
ticket, `tickets:read_own` only tickets the user reported; invisible tickets answer 404. IT
staff (`tickets:manage`) may set any status; requesters may only cancel an open ticket, or
close/reopen a resolved one (`allowed_statuses` is returned as a capability). Assigning needs
`tickets:assign` and the assignee must hold `tickets:manage`; assigning an `OPEN` ticket starts
work. Comments and history events carry `is_internal`; internal ones are filtered out in SQL for
people without `tickets:comment_internal` and never notify the requester. A requester reply
while `WAITING_FOR_USER` moves the ticket back to `IN_PROGRESS`.
**Why.** Same pattern as documents and tasks (one predicate, capabilities from the server),
and the requester only ever sees actions that make sense to them.

## ADR-045 — Notification e-mail after commit, with per-type preferences (2026-11-12)
**Decision.** `notify()` stays inside the business transaction; the notification id is queued
on the session and handed to the Celery task `notifications.send_emails` only in
`after_commit` (dropped on rollback). The worker mails each notification at most once
(`email_status` PENDING → SENT/SKIPPED/FAILED) to the account address when SMTP is configured
and the user wants that type (`notification_preferences`, defaults: everything except
`DOCUMENT`). Mail goes through the standard library (`smtplib`, STARTTLS/SSL/login). Password
reset links are e-mailed the same way when SMTP is set. Development uses Mailpit
(http://127.0.0.1:8025); tests run with `SMTP_HOST` empty.
**Why.** No e-mail for changes that did not happen, no SMTP latency in requests, and no extra
mail SDK.

## ADR-046 — Analytics scopes follow permissions (2026-11-12)
**Decision.** `GET /analytics/overview?scope=own|department|all` needs
`analytics:read_own|read_department|read_all` (department scope also needs a department).
Own = tasks assigned to me, tickets I reported, my documents; department = the department's
tasks and documents and tickets reported by its people; all = the organisation. Aggregates
are computed in SQL per request over Bangkok calendar days (default 30, max 366). Exported row
lists are additionally filtered by the normal task/ticket visibility predicates, so a report
never lists a row its reader could not open (counts may cover more, e.g. a department's
tickets). The AI summary sends only the aggregated numbers (no titles or names) to the model.
**Why.** Managers need department figures without gaining access to every record behind them.

## ADR-047 — Report exports: openpyxl and WeasyPrint (2026-11-12)
**Decision.** `GET /reports/overview.xlsx|pdf` (`reports:export` + the scope permission,
audited as `report.exported`). Excel via openpyxl; text cells that start with `=` are stored
as strings (no formula injection). PDF via WeasyPrint from escaped HTML, with Pango/HarfBuzz and
the TLWG Thai fonts installed in the backend image; rendering runs in a thread. Lists are capped
(2,000 rows in Excel, 100 per list in the PDF).
**Why.** Correct Thai shaping needs a real text layout engine; HTML keeps the layout simple.

## ADR-048 — Role and permission editor on `/settings` (2026-11-12)
**Decision.** `/settings` (`roles:read`) lists roles with their permissions grouped by domain;
`roles:manage` can create custom roles, rename them, edit permissions and delete unused custom
roles. The UI disables permissions the editor does not hold (the backend still enforces
ADR-018); `ADMIN` is locked; system role names come from `sync-rbac` and are not editable.
**Why.** Roles are data (ADR-005); administrators need to manage them without the API docs.

## ADR-049 — Rate limiting fails closed in production (2026-11-12)
**Decision.** When Redis is unreachable the limiter allows requests in development/test and
refuses them with 503 `rate_limiter_unavailable` in staging/production (`RATE_LIMIT_FAIL_OPEN`
overrides). Besides login/reset (per account and per IP) and AI chat, uploads, report exports
and AI summaries are limited per user (`UPLOAD_RATE_LIMIT`, `EXPORT_RATE_LIMIT`). Production
Nginx adds an IP limit on the credential endpoints and overwrites `X-Forwarded-For` with the
connecting address, so clients cannot spoof the IP the backend sees.
**Why.** A cache outage must not silently switch brute-force protection off; expensive
endpoints need a ceiling per account.

## ADR-050 — Content-Security-Policy without nonces (2026-11-12)
**Decision.** Pages get `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'
'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self';
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none';
upgrade-insecure-requests` from `next.config.ts` (`'unsafe-eval'`/websockets only in
development). API responses get `default-src 'none'; frame-ancestors 'none'`. Both send
`Permissions-Policy` (camera, microphone, geolocation, payment off).
**Why.** Nonce-based CSP needs fully dynamic rendering, which Cache Components / partial
prerendering do not allow (Next.js 16 docs). Inline scripts are therefore allowed; the code
never renders raw HTML (no `dangerouslySetInnerHTML`), model output and documents are shown as
plain text, and everything else is locked to the same origin.

## ADR-051 — Retention clean-up with Celery beat (2026-11-12)
**Decision.** A `beat` service schedules `maintenance.purge` daily at 03:15 Asia/Bangkok
(`python -m app.cli purge [--dry-run]` by hand). It removes documents soft-deleted more than
30 days ago (files first; the row stays for a retry if a file cannot be deleted), stored files
that nothing references after 24 hours, deleted or idle chats (`AI_CHAT_RETENTION_DAYS`),
expired sign-in sessions and reset tokens, and read notifications after a year. Audit logs are
never purged.
**Why.** Soft deletes and removed attachments otherwise keep personal data and files forever;
every step is idempotent so a missed or repeated run is harmless.

## ADR-052 — Backups: pg_dump plus a tar of stored files (2026-11-12)
**Decision.** `scripts/backup.sh` writes `database.dump` (`pg_dump -Fc`) and `files.tar`
(`python -m app.cli storage-export`, every object under its key) with SHA-256 checksums.
`scripts/restore.sh` verifies checksums and either restores into a separate database and
bucket (verification, live data untouched) or, with `--yes`, replaces the live data. Import
refuses archive entries that are not plain files or whose names are absolute or contain empty,
`.` or `..` segments.
**Why.** Two portable files per backup, no extra tools in the images, and a restore that can be
tested routinely without risk.

## ADR-053 — Single-host production stack (2026-11-12)
**Decision.** `docker-compose.prod.yml`: production images (non-root), only Nginx publishes
ports, Redis requires a password, MinIO's console is off, logs rotate, `migrate` also creates
the bucket. Configuration comes from `.env.production` (template with `CHANGE_ME`
placeholders); the backend refuses unsafe production values. Public readiness shows only the
overall status (`X-Health-Token` or `GET /health/details` with `system:configure` for details).
The first administrator is created with `python -m app.cli create-admin` (password from stdin).
**Why.** One `docker compose up` deploys a hardened system on a single server; the same
images can later move to an orchestrator.

## ADR-054 — Ticket attachments with screenshots and internal files (2026-11-12)
**Decision.** `ticket_attachments` (migration `0009`) reuses the upload pipeline of documents and
task attachments (size checks, content sniffing, store-then-commit, objects under
`tickets/{ticket}/{attachment}`). Besides PDF/DOCX/XLSX/TXT, tickets accept PNG and JPEG
identified by their signature (`inspect_attachment`); images are never parsed. Anyone who sees
the ticket may attach while it is not closed or cancelled (`tickets:manage` always);
`is_internal` files need `tickets:comment_internal` and are invisible (404) to everyone else,
like internal notes. Uploaders remove their own files while the ticket is open; IT removes any.
Downloads are always `Content-Disposition: attachment` with `nosniff`; the UI previews images
only through a `blob:` URL inside an `<img>`. Additions, removals and downloads are audited;
public files notify the other party; the orphan sweep and backups include ticket files.
**Why.** A screenshot of the error is the most useful thing a requester can give IT; documents
keep their four formats because their text is extracted and indexed.

## ADR-055 — Front end on Vercel with the API hosted separately (2026-11-12)
**Decision.** Besides the single-host stack (ADR-053), the front end may run on Vercel while
the API, worker, beat, PostgreSQL, Redis and storage run on a container host (documented with
Railway and Cloudflare R2, `docs/DEPLOYMENT.md` section 9). Vercel keeps proxying `/api/*` to
the API (`BACKEND_INTERNAL_URL`), so pages and API share one origin and cookies, CSRF and the
CSP stay as they are. Because the API then has a public address of its own,
`PROXY_SHARED_SECRET` closes it to direct calls: `frontend/vercel.json` sets
`X-Orbit-Proxy-Secret` on every proxied request, the API answers `403 proxy_required` without
it (only the liveness probe is exempt), drops the header before handlers, and takes the
visitor IP from `X-Vercel-Forwarded-For`, which Vercel sets itself. API responses default to
`Cache-Control: no-store` so no CDN keeps per-user data; `postgres://` URLs from hosted
databases are switched to the psycopg driver.
**Why.** The user already deploys the front end from GitHub to Vercel, which cannot run the
API's long-lived processes. Without the secret anyone could call the API directly with a
forged `X-Forwarded-For` and spread login attempts over fake IPs.

