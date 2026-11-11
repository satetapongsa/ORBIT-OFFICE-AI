# AURA OFFICE AI — Architecture Decision Records

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
**Decision.** `aura_csrf` (readable, `SameSite=Lax`) must equal `X-CSRF-Token` on
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
**Decision.** Tests use a separate database (`aura_office_test`, or `AURA_TEST_DATABASE_URL`)
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
**Decision.** Development seed accounts use `@aura.example.com`, tests use `@example.com`
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
