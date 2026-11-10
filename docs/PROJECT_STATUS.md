# AURA OFFICE AI — PROJECT STATUS

**Current Phase:** Phase 1 — System Foundation & Project Scaffold (code complete; Docker-based verification pending)
**Last Updated:** 2026-11-10

## Completed

### Phase 0 — Project initialization & architecture
- Workspace inspected (was empty); git repository initialised (`main`).
- Documentation: `PROJECT_OVERVIEW`, `ARCHITECTURE`, `DATABASE_DESIGN`, `API_CONVENTIONS`,
  `SECURITY`, `DEVELOPMENT_PHASES`, `PROJECT_STATUS`, `DECISIONS` (ADR-001…012), `RUNBOOK`,
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

## In Progress
- Phase 1 verification on a machine with Docker (see Known Issues #1).

## Remaining
- Phase 1: run `docker compose up --build`, `scripts/smoke-test.sh`,
  `AURA_RUN_INTEGRATION=1 pytest -m integration`, Celery `system.ping` round trip.
- Phases 2–9 per `docs/DEVELOPMENT_PHASES.md`.

## Technical Decisions
See `docs/DECISIONS.md`. Key ones: same-origin API via proxy (ADR-002); psycopg 3 for async and
sync (ADR-003); permission-based RBAC with roles as data (ADR-005); ACL evaluated at query time
for RAG (ADR-006); provider-independent AI with separate chat/embedding config (ADR-007);
MinIO pinned + overridable, S3-generic code (ADR-009).

## Tests
Commands actually executed on 2026-11-10 (Windows 11, Python 3.15.2, Node 26.13):

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
1. **Docker-based acceptance criteria unverified.** Docker, PostgreSQL and Redis are not installed
   on the development machine, so Compose startup, real DB/Redis/MinIO connectivity, migrations
   against PostgreSQL, the Celery worker and Dockerfile builds have not been run. Code paths are
   covered by unit tests with mocked checks and by an integration test that is ready to run.
2. MinIO image tag `RELEASE.2025-04-22T22-12-26Z` not pulled/verified; override with
   `MINIO_IMAGE` if unavailable (ADR-009).
3. Readiness endpoint is unauthenticated and lists component status; acceptable for internal dev,
   to be reviewed (restrict detail or network-limit) in Phase 9.
4. Backend startup waits up to `2 × HEALTH_CHECK_TIMEOUT_SECONDS` (6 s default) for dev bucket
   creation when object storage is unreachable.
5. Next.js dev server writes `frontend/AGENTS.md` automatically; it is ignored by the global git
   excludes and not part of the project.
6. No authentication yet — every page is public until Phase 2.

## Next Phase
**Phase 2 — Authentication & Authorization** (after closing Known Issue #1): users, departments,
roles, permissions, Argon2id, JWT access + rotating refresh tokens in HttpOnly cookies, CSRF,
authorization dependencies, document ACL foundation, audit logs, seed data, login UI,
permission-aware navigation, auth/authz tests.

## Next Command
First verify Phase 1 on a machine with Docker:

```bash
cp .env.example .env && docker compose up --build -d && scripts/smoke-test.sh
```

Then start the next session with:

```
Continue AURA OFFICE AI: read docs/PROJECT_STATUS.md and docs/DEVELOPMENT_PHASES.md, then execute PHASE 2 — AUTHENTICATION & AUTHORIZATION as defined in docs/DEVELOPMENT_PHASES.md.
```

## Report format (end of every phase, in Thai)
1. Completed · 2. Files Created or Modified · 3. Database Changes · 4. API Changes · 5. Tests ·
6. How to Run · 7. Known Issues · 8. Project Status · 9. Next Phase · 10. Next Command
