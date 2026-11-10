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
